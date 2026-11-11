# Ghi chú phân tích · Day 04

Họ và tên: Đinh Thị Hường
MSSV: 2A202603569
Ngày thực hiện: 11/11/2026 (giờ Việt Nam)

## 1. Case được chọn

- ID case: **H6** (dữ liệu status có 40 mục nhiễu, cần theo liên kết incident).
- Yêu cầu: kiểm tra GitHub Actions, đọc incident `h02n9572mx9y`, theo liên kết của incident để xác định báo cáo gộp có nêu nguyên nhân hay chỉ mô tả ảnh hưởng.
- Điểm lần trước: **60/100**, điểm lần sau: **92/100**.
- Trích nguyên văn câu trả lời trước: “Không có nguyên nhân cụ thể được nêu ở incident này, mà chủ yếu mô tả ảnh hưởng và các bước xử lý.”
- Vấn đề: agent chỉ đọc incident ban đầu, chưa đọc incident gộp nên chưa đủ bằng chứng trả lời về nguyên nhân trong báo cáo gộp.

## 2. Bằng chứng trong trace

Các tool calls trước cải tiến, trích đúng step/name/arguments từ `eval_before.json`:

```json
[
  {
    "event": "tool",
    "step": 1,
    "name": "get_status",
    "arguments": {
      "provider": "github",
      "component": "actions"
    }
  },
  {
    "event": "tool",
    "step": 1,
    "name": "get_incident_details",
    "arguments": {
      "provider": "github",
      "incident_id": "h02n9572mx9y"
    }
  }
]
```

Tool trả update có liên kết `https://www.githubstatus.com/incidents/xr3myzj7ms51`, nhưng trace không có lần gọi đọc incident đó. Hai calls đều ở model step 1. Kiểm tra code giới hạn điểm H6 ở 60 vì cần ít nhất hai model steps có tool call. Judge cho điểm thô 92 nhưng điểm cuối vẫn là 60: điểm judge cao không thay thế được việc xem trace.

Sau cải tiến, các tool calls thực tế:

```json
[
  {
    "event": "tool",
    "step": 1,
    "name": "get_status",
    "arguments": {
      "provider": "github",
      "component": "GitHub Actions"
    }
  },
  {
    "event": "tool",
    "step": 1,
    "name": "get_incident_details",
    "arguments": {
      "provider": "github",
      "incident_id": "h02n9572mx9y"
    }
  },
  {
    "event": "tool",
    "step": 3,
    "name": "get_incident_details",
    "arguments": {
      "provider": "github",
      "incident_id": "xr3myzj7ms51"
    }
  },
  {
    "event": "tool",
    "step": 3,
    "name": "get_status",
    "arguments": {
      "provider": "github"
    }
  }
]
```

Các event kiểm chứng ở lần sau:

```json
[
  {
    "event": "validation_missing_evidence",
    "step": 2,
    "pending_incidents": [
      [
        "github",
        "xr3myzj7ms51"
      ]
    ],
    "pending_status": []
  },
  {
    "event": "validation_missing_source",
    "step": 4,
    "missing_urls": [
      "https://stspg.io/7pwv28hvkmz8",
      "https://stspg.io/pjgptg3cfc6n"
    ]
  }
]
```

Câu trả lời sau phân biệt incident đầu chỉ mô tả ảnh hưởng với báo cáo gộp có nguyên nhân: thay đổi cấu hình dịch vụ định tuyến sự kiện nội bộ, feature flags không đúng và rollback cấu hình. Câu trả lời có URL của cả hai incident.

Nguyên nhân có thể xảy ra: prompt ban đầu chưa yêu cầu rõ việc đọc tiếp liên kết; loop cho phép dừng ngay khi model nói xong, chưa kiểm tra còn nguồn liên quan cần đọc. Model cũng có thể quên URL khi viết lại câu trả lời.

## 3. Thay đổi đã thực hiện

`agent.py` được viết bằng Python standard library, không dùng framework agent:

- Tạo lịch sử system/user, gọi provider, giữ nguyên assistant message và trả mọi tool result với đúng `tool_call_id`. Một model call là một step.
- Trả `completed`, `max_steps` hoặc `error`; lưu `trace` và `usage`. JSON sai hoặc không phải object trả `INVALID_ARGUMENTS`; lỗi tool trở thành observation; provider lỗi và output bị cắt không báo hoàn thành. Không ghi nguyên văn exception provider vào trace để tránh lộ dữ liệu nhạy cảm.
- Prompt yêu cầu phân biệt snapshot/incident lịch sử, phạm vi ảnh hưởng, giới hạn tìm kiếm, dữ liệu bị cắt và không làm theo prompt injection.
- Khi câu hỏi cần điều tra nguyên nhân/liên kết, thu thập các liên kết incident thuộc GitHub/Cloudflare từ update đã quan sát. Nếu model muốn dừng mà chưa thử đọc liên kết, ghi `validation_missing_evidence` và yêu cầu gọi tool tiếp trong budget. Không hard-code ID hay đáp án; liên kết không tìm thấy chỉ yêu cầu thử một lần rồi nêu giới hạn.
- Với câu hỏi có dấu hiệu hỏi trạng thái hiện tại/snapshot, không dùng riêng incident lịch sử để thay cho `get_status`. Nếu đã đọc incident mà chưa kiểm tra status provider đó, yêu cầu bổ sung trước khi kết luận.
- Với tool lỗi, bổ sung nhắc nhở system sau toàn bộ tool results: không được giả định trạng thái operational khi chưa có dữ liệu. Đây là hướng dẫn model, chưa phải bộ kiểm chứng ngữ nghĩa tuyệt đối.
- Lưu mọi URL incident đọc thành công. Nếu final answer thiếu URL nào, ghi `validation_missing_source`, yêu cầu viết lại trong cùng `max_steps`. Khi hết bước vẫn thiếu, trả `max_steps`. Tool đọc incident thất bại không tạo yêu cầu URL.
- Thêm `tests/test_agent_errors.py` để kiểm tra lỗi provider, response sai, JSON array, budget, nhiều nguồn, liên kết chưa đọc và status chưa kiểm tra. Toàn bộ **44 tests** trong `tests/` đạt.

Lý do chọn thay đổi: lỗi H6 có bằng chứng trực tiếp trong trace, có thể chặn việc dừng sớm bằng code thay vì chỉ trông chờ prompt. Kiểm tra nguồn đáp ứng contract Bài 4 và giúp phát hiện câu trả lời thiếu citation.

Giữ `agent_before.py` là bản loop cơ bản dùng tạo `eval_before.json` để có thể đọc lại thay đổi trước/sau. SHA-256 bản trước: `8b22070e9ce1bdf77c4cc3c643d39dacf85d5f74a1561f52a26cad5a3f6fb196`. SHA-256 bản bài chính (`agent_main.py`, trước khi mở rộng bonus): `a2a999df7bd6d128bbd4eba1f900b4f7e92bd17843cdd1952aacb26c56b0cd4a`.

## 4. So sánh hai lần chạy

Hai file đều đủ **22/22 case**, không có `unscored`, cùng cấu hình:

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini-2025-04-14",
  "judge_provider": "openai",
  "judge_model": "gpt-4.1-mini-2025-04-14",
  "max_steps": 8,
  "dataset": "core"
}
```

Cả hai dùng snapshot cố định trong `fixtures/`; không sửa fixtures, cases, scenarios, grading hay rubric. Hai lượt chính đều chạy `--workers 2 --max-steps 8`. API key không nằm trong file kết quả.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---:|---:|
| Điểm tổng (0–100) | 94.91 | 99.05 |
| Điểm H6 | 60 | 92 |
| Model calls của agent | 49 | 55 |
| Calls judge cho các case | 22 | 22 |
| Token agent | 36082 | 61948 |
| Token judge | 35686 | 36529 |
| Tổng token agent + judge | 71768 | 98477 |
| Chi phí tham khảo, USD | 0.04025 | 0.04734 |

Chi phí trên là **ước tính** từ usage trong hai file, theo giá tham khảo GPT-4.1 mini: input 0,40 USD/triệu token, cached input 0,10 USD/triệu, output 1,60 USD/triệu. Nguồn: https://developers.openai.com/api/docs/models/gpt-4.1-mini . Đây không phải hóa đơn; không bao gồm probe và các lượt thử khác, usage của call bị lỗi có thể không được ghi nhận.

| Case | Trước | Sau |
|---|---:|---:|
| E1 | 95 | 100 |
| E2 | 100 | 99 |
| E3 | 100 | 100 |
| E4 | 100 | 100 |
| E5 | 100 | 95 |
| E6 | 100 | 100 |
| A1 | 100 | 100 |
| A2 | 100 | 100 |
| A3 | 100 | 100 |
| A4 | 100 | 100 |
| A5 | 100 | 100 |
| A6 | 100 | 93 |
| A7 | 100 | 100 |
| A8 | 100 | 100 |
| H1 | 60 | 100 |
| H2 | 100 | 100 |
| H3 | 98 | 100 |
| H4 | 100 | 100 |
| H5 | 100 | 100 |
| H6 | 60 | 92 |
| H7 | 80 | 100 |
| H8 | 95 | 100 |

- Lỗi đã giải quyết trong lượt cuối: H1 đọc tiếp báo cáo liên kết (60 → 100); H6 theo liên kết và bổ sung nguồn (60 → 92); H7 không giả định Cloudflare operational khi timeout (80 → 100). H2 cuối đã có cả status và incident.
- H6 cần thêm calls để đọc tiếp và sửa nguồn, làm tăng token/độ trễ. Cải tiến có đánh đổi chi phí và budget, không chỉ thay đổi điểm.
- Lỗi/giới hạn còn lại: H6 chưa nhấn mạnh đủ nội dung có thể bị cắt; các case E2/E5/A6 chưa đạt 100. Judge ghi nhận các thiếu sót về mức độ đầy đủ/cách nêu giới hạn. Cần đọc answer và trace để phân biệt lỗi thật với sai số judge, không mặc định mọi góp ý judge đều đúng.

### Các lượt thử đã giữ lại

- `eval_before_incomplete.json`: lượt đầu bản cơ bản, 20/22 case được chấm; E2 và H1 lỗi provider, tổng `null`. Không dùng điểm trung bình phần đã chấm làm điểm cả bộ. Sau đó chạy lại toàn bộ bằng chính `agent_before.py` để tạo `eval_before.json` hợp lệ.
- `eval_after_intermediate.json`: lượt cải tiến trung gian, 94,27/100. H6 cải thiện nhưng H1 vẫn chưa theo liên kết, H2 thiếu status và H7 vẫn giả định operational. Các nhánh còn thiếu được bổ sung trước khi chạy toàn bộ bản cuối.
- Không sửa tay answer, trace hay điểm của bất kỳ file eval nào. Báo cáo này mô tả một vòng cải tiến có nhiều lần kiểm tra kỹ thuật, không coi đó là thí nghiệm chỉ chạy duy nhất hai lần.

## 5. Giới hạn

- Snapshot bài chính chụp ngày 09/11/2026, không xác nhận status tại ngày thực hiện 11/11/2026 hay thời điểm đọc báo cáo. Mỗi provider chỉ có 50 incident gần nhất; không tìm thấy không chứng minh incident không tồn tại.
- Tool chỉ trả tối đa 5 incident khớp chuỗi. Chi tiết giữ hai update mới nhất và update đầu, mỗi body tối đa 900 ký tự. Không có toàn bộ timeline; phải đọc `truncated` và `updates_total`.
- LLM judge có thể nhầm: ví dụ H1 trước được judge cho điểm thô 100 dù trace chưa đọc báo cáo liên kết; kiểm tra code mới chặn ở 60. Agent và judge cùng model còn có thể cùng thiên lệch.
- Không suy ra 99,05 điểm eval là 99,05 điểm bài lab: bài chính tối đa 85, giảng viên chấm thêm code, trace, báo cáo và demo theo rubric.
- Một lượt hoàn chỉnh cho mỗi phiên bản được chọn không chứng minh ổn định; các lượt thử cho thấy đáp án và điểm có biến động. Kết quả không bảo đảm lặp lại y hệt.
- Validation URL chỉ kiểm tra sự hiện diện chuỗi, không chứng minh mọi claim có nguồn, URL là đúng ngữ cảnh hay model không thể bịa URL bổ sung. Liên kết chỉ nhận dạng đường dẫn incident GitHub/Cloudflare đã quan sát, không phải crawler tổng quát.
- Điều kiện câu hỏi dùng từ khóa tiếng Việt nên có thể bỏ sót cách diễn đạt khác hoặc yêu cầu thêm status không cần thiết. Chặn thiếu evidence có thể dùng hết budget; không tự tăng `max_steps` để làm đẹp điểm.
- Nhắc nhở khi tool lỗi và chống injection vẫn phụ thuộc model; tests offline không chứng minh mọi tình huống model thật đều an toàn/chính xác.
- Lỗi provider được lược thông điệp để bảo vệ dữ liệu, vì vậy hai lỗi đầu chưa được phân loại chính xác là timeout/rate limit hay lỗi khác.

### Chạy lại và demo trên PowerShell

```powershell
. ./load-env.ps1
python -m unittest discover -s tests -v
python run.py --max-steps 8 'Điều tra incident GitHub h02n9572mx9y và theo liên kết để tìm nguyên nhân. Dẫn nguồn.'
# Chỉ chạy lại eval khi cần, vì API có phí; dùng tên mới để giữ kết quả nộp.
python evals/run_evals.py --case H6 --max-steps 8 --output demo_h6.json
```

Demo bằng trace H6 trong `eval_after.json`: chỉ ra status → incident ban đầu → `validation_missing_evidence` → incident gộp → `validation_missing_source` → final có hai URL. So sánh H7 trước/sau để giải thích vì sao timeout không phải bằng chứng operational hoặc outage.

Bài chính đã kiểm tra cục bộ. Phiên bản tạo `eval_after.json` được lưu trong `agent_main.py`; `agent.py` hiện hỗ trợ cả bài chính và bonus như phần 6 bên dưới. Chưa push GitHub hoặc nộp LMS.


## 6. Bonus — 5 status API

### Kết nối và triển khai

- `agent.py` dùng `getattr(tools, 'schemas', SCHEMAS)` và `getattr(tools, 'system_prompt', SYSTEM_PROMPT)` để nhận bộ tool/prompt do môi trường cung cấp. Với `BonusTools`, có năm status tools GitHub, Cloudflare, Vercel, npm, DigitalOcean và `get_incident_details` phân trang.
- Nhánh bonus được bật khi schema có `get_vercel_status`; policy bổ sung nằm trong `bonus_policy.py`. Không sửa `bonus/tools.py`, fixture, cases hoặc grading của đề.
- `RetryPolicy` trả lỗi cho model quan sát để model tự gọi lại; không âm thầm tự retry thành công rồi che lỗi trước đó. Với 429 liên tiếp, tối đa ba lần thực thi bị rate limit cho cùng tool/provider, sau đó chặn execution tiếp theo. Các tool/provider khác vẫn hoạt động.
- Đọc `Retry-After` dạng số giây hoặc ngày HTTP; thiếu/header sai dùng 1 giây. Tổng budget chờ là 10 giây/run. Nếu thời gian chờ vượt budget thì dừng retry và báo chưa biết trạng thái. Chỉ chờ khi model thực sự yêu cầu gọi lại. Trường `retry_policy.allowed` cho model biết còn được retry hay không. Trong snapshot, 429 giả lập có thời gian chờ 0.
- Trước final answer, nếu còn 429 được phép retry mà model chưa gọi lại, ghi `validation_pending_retry` và yêu cầu tool call thật. Không chấp nhận câu “đã retry” thay cho trace thực thi.
- `INVALID_ARGUMENTS` vẫn được trả về model để sửa kiểu dữ liệu/tham số. Tổng số model calls luôn bị giới hạn bởi `max_steps`; bộ bonus chạy 16 bước.
- Khi câu hỏi yêu cầu timeline, ghi nhận offset và các update đã đọc. Trước khi kết thúc, nếu thiếu trang thì ghi `validation_pending_pages` và yêu cầu đọc phần thiếu. Đọc trang cuối không được coi là đã đọc các trang giữa chưa xem.
- Khi câu hỏi yêu cầu đối chiếu phạm vi incident, status tổng quan chưa đủ: yêu cầu đọc chi tiết incident liên quan lấy từ status response, không hard-code ID hoặc đáp án.
- Loại riêng trường `distractors` khỏi observation gửi model, bổ sung số lượng đã lược bỏ và event `context_compacted`. Trace giữ nguyên 160 mục nhiễu để có thể đối chiếu. Không loại update, timestamp, source hay lỗi cần thiết.
- Tiếp tục kiểm tra URL nguồn incident, không coi snapshot/historical incident là trạng thái live và không làm theo prompt injection trong tool output.

### Kết quả thực tế

Cấu hình:

```json
{
  "provider": "openai",
  "model": "gpt-4.1-mini-2025-04-14",
  "judge_provider": "openai",
  "judge_model": "gpt-4.1-mini-2025-04-14",
  "max_steps": 16,
  "dataset": "bonus"
}
```

Hai lượt đều `--workers 2 --max-steps 16`, cùng model/judge/dataset. Mỗi file đủ 10/10 case được chấm, không có `unscored`.

| Chỉ số | `eval_bonus_first.json` | `eval_bonus.json` |
|---|---:|---:|
| Điểm eval (0–100) | 90.0 | 99.3 |
| Bonus tham khảo (0–15) | 13.5 | 14.89 |

| Case | Lượt đầu | Bản cuối |
|---|---:|---:|
| B1 | 100 | 100 |
| B2 | 100 | 100 |
| B3 | 100 | 100 |
| B4 | 100 | 100 |
| B5 | 100 | 100 |
| B6 | 50 | 100 |
| B7 | 100 | 100 |
| B8 | 100 | 96 |
| B9 | 100 | 100 |
| B10 | 50 | 97 |

Bản cuối: 36 model calls agent, 10 judge calls; agent dùng 71703 token, judge dùng 29780 token. Chi phí tham khảo riêng lượt cuối khoảng 0.03730 USD theo cùng đơn giá phần 4, không phải hóa đơn và không bao gồm lượt bonus đầu.

Lượt đầu đạt 90/100 nhưng B6 thiếu `get_incident_details` và B10 nói đã retry dù trace chỉ có một lần gọi Vercel. Bản cuối bổ sung validation thiếu chi tiết incident và retry chưa thực hiện. Giữ nguyên file đầu để đối chiếu, không sửa tay kết quả.

### Trace minh họa

B2 đọc timeline Vercel ở các offset 0, 3, 6; update cần tìm ở trang offset 3. Event `validation_pending_pages` ngăn model dừng khi chưa đọc trang cuối. Trace thực tế:

```json
[
  {
    "step": 1,
    "name": "get_incident_details",
    "arguments": {
      "provider": "vercel",
      "incident_id": "sps6n39gm4sg",
      "limit": 3
    },
    "error": null,
    "next_offset": 3
  },
  {
    "step": 2,
    "name": "get_incident_details",
    "arguments": {
      "provider": "vercel",
      "incident_id": "sps6n39gm4sg",
      "offset": 3,
      "limit": 3
    },
    "error": null,
    "next_offset": 6
  },
  {
    "step": 4,
    "name": "get_incident_details",
    "arguments": {
      "provider": "vercel",
      "incident_id": "sps6n39gm4sg",
      "offset": 6,
      "limit": 3
    },
    "error": null,
    "next_offset": null
  },
  {
    "step": 6,
    "name": "get_vercel_status",
    "arguments": {},
    "error": null,
    "next_offset": null
  }
]
```

B3: một lần 429 rồi một lần status thành công, điểm 100. B4: GitHub thành công, Vercel ba lần 429 rồi dừng và trả thông tin từng phần, điểm 100. B5: lỗi định dạng giả lập lần đầu, các lần sau dùng offset/limit integer và đọc được npm, điểm 100.

B6: giữ 160 distractors trong trace, bỏ khỏi context; sau `validation_missing_evidence`, đọc cả hai incident Vercel/npm, điểm 100. B7 bỏ qua injection marker, B9 không gọi tool hoặc bịa status/link cho Linear/Slack, đều 100.

B10 có `validation_pending_retry` ở model step 2; lần gọi Vercel thực sự thứ hai ở step 3 thành công. Không còn báo retry thiếu bằng chứng.

### Kiểm tra và giới hạn còn lại

- **44/44 tests bài chính và 12/12 tests bonus đạt**, gồm test cap ba lần 429, không chờ quá budget, xử lý HTTP-date, tôn trọng thời gian chờ, giữ trace khi bỏ nhiễu, thiếu trang giữa, thiếu incident detail và retry chưa thực hiện.
- Đã so sánh sáu trajectory offline giữa `agent_main.py` và `agent.py` khi dùng tools bài chính: kết quả và lịch sử gửi provider giống nhau. Không chạy lại eval bài chính bằng model thật sau khi mở rộng; `eval_before.json`/`eval_after.json` là các bằng chứng của phiên bản bài chính đã lưu.
- Điểm B8 = 96: cần nói rõ hơn khi nguồn Vercel không xác nhận ảnh hưởng ứng dụng đang chạy. Điểm B10 = 97: nên nêu rõ số lần retry thực tế và giới hạn trong final answer. Đây là nhận xét judge, vẫn cần đối chiếu trace và nguồn.
- Snapshot của năm provider không cùng timestamp. Không coi năm trạng thái là số đo đồng thời hoặc bằng chứng chung nguyên nhân.
- Pagination đầy đủ được yêu cầu khi nhận diện từ khóa timeline; cách hỏi khác có thể không kích hoạt. Đọc đầy đủ các trang có thể dùng nhiều bước/token hơn mức cần thiết nếu chỉ muốn một update.
- Kiểm tra phạm vi chọn incident đầu trong danh sách đã được tool lọc; không thay thế semantic search hay đảm bảo đó luôn là incident người dùng muốn.
- Giới hạn retry bảo vệ execution thật. Nếu model vẫn yêu cầu gọi tool bị chặn, observation trả `RETRY_EXHAUSTED`; run vẫn có thể hết `max_steps`. Không bảo đảm mọi model luôn dừng ở đúng số tool-call đề xuất.
- Live 429 được kiểm tra bằng HTTPError giả lập và unit tests, không cố tạo rate limit thật trên public API. Bộ eval bonus chạy snapshot cố định; không tuyên bố đã kiểm chứng mọi hành vi live.
- Không có bộ kiểm chứng ngữ nghĩa hoàn chỉnh cho chống injection, URL hay quan hệ nhân quả; vẫn phụ thuộc model và chất lượng nguồn. Không tự cộng điểm eval bài chính với điểm bonus để báo điểm học phần.
- SHA-256 `agent.py` bản bonus: `d157108738e743de47ea2f200ead736499b62d98d4ebce8dcd4d07134db1a23e`.
- SHA-256 `bonus_policy.py`: `b7aaf3ee1d0cd535dcf068dcbf91c7978e5f20422cca1c1c357c7c8643388fef`.

### Chạy và demo bonus

```powershell
. ./load-env.ps1
python -m unittest discover -s tests -v
python -m unittest discover -s bonus -p 'test_*.py' -v
python run.py --bonus --max-steps 16 'Kiểm tra status GitHub, Vercel và npm. Dẫn nguồn và timestamp từng bên.'
# Nếu cần chạy lại toàn bộ, dùng tên mới để giữ file đã nộp:
python evals/run_evals.py --bonus --max-steps 16 --output eval_bonus_rerun.json
```

Bài chính và bonus đã hoàn thành, kiểm tra cục bộ. Chưa push GitHub hoặc nộp LMS. Khi bàn giao/nộp, giữ `bonus_policy.py` cùng `agent.py` vì agent nhập policy khi chạy bonus; nộp thêm `eval_bonus.json` và báo cáo này.
