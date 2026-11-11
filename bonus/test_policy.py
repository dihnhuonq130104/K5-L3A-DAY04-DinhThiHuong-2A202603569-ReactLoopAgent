"""Kiểm tra giới hạn retry và phân trang ngoài các test mẫu của đề."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
import unittest
from unittest.mock import patch

from agent import run_agent
from bonus.tools import BonusTools
from bonus_policy import RetryPolicy, retry_delay
from test_agent import ScriptedProvider, call, final


class RetryTests(unittest.TestCase):
    def test_three_rate_limits_block_further_execution(self):
        tools = BonusTools(scenario='rate_limit_always')
        policy = RetryPolicy()
        responses = [policy.execute(tools, 'get_vercel_status', {}, 'vercel') for _ in range(4)]
        self.assertFalse(responses[2]['retry_policy']['allowed'])
        self.assertEqual(responses[3]['error'], 'RETRY_EXHAUSTED')
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 3)
        self.assertEqual(policy.execute(tools, 'get_github_status', {}, 'github')['provider'], 'github')

    def test_retry_after_beyond_budget_stops_without_sleep(self):
        class LimitedTools:
            def execute(self, name, arguments):
                return {'ok': False, 'error': 'RATE_LIMITED', 'retry_after': '120'}
        policy = RetryPolicy(wait_budget=10)
        with patch('bonus_policy.time.sleep') as sleep:
            first = policy.execute(LimitedTools(), 'get_npm_status', {}, 'npm')
            second = policy.execute(LimitedTools(), 'get_npm_status', {}, 'npm')
        self.assertFalse(first['retry_policy']['allowed'])
        self.assertEqual(second['error'], 'RETRY_EXHAUSTED')
        sleep.assert_not_called()

    def test_retry_after_wait_is_respected(self):
        class LimitedTools:
            count = 0
            def execute(self, name, arguments):
                self.count += 1
                return ({'ok': False, 'error': 'RATE_LIMITED', 'retry_after': '2'}
                        if self.count == 1 else {'provider': 'npm'})
        policy, tools = RetryPolicy(), LimitedTools()
        with patch('bonus_policy.time.monotonic', return_value=100), patch('bonus_policy.time.sleep') as sleep:
            policy.execute(tools, 'get_npm_status', {}, 'npm')
            response = policy.execute(tools, 'get_npm_status', {}, 'npm')
        sleep.assert_called_once_with(2.0)
        self.assertEqual(response['provider'], 'npm')

    def test_retry_after_http_date_and_invalid_values(self):
        deadline = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
        self.assertTrue(28 <= retry_delay({'retry_after': deadline}) <= 31)
        self.assertEqual(retry_delay({'retry_after_seconds': 0}), 0)
        for value in ('garbage', 'nan', 'inf'):
            self.assertEqual(retry_delay({'retry_after': value}), 1.0)


class BonusContextTests(unittest.TestCase):
    def test_noise_is_removed_from_context_but_retained_in_trace(self):
        tools = BonusTools(scenario='noisy')
        provider = ScriptedProvider([call('a', 'get_vercel_status', {}), final()])
        result = run_agent('Kiểm tra Vercel', provider, tools)
        self.assertEqual(result['status'], 'completed')
        observation = json.loads(provider.histories[1][-1]['content'])
        self.assertNotIn('distractors', observation)
        self.assertEqual(observation['omitted_distractors'], 160)
        raw = next(t['result'] for t in result['trace'] if t['event'] == 'tool')
        self.assertEqual(len(raw['distractors']), 160)

    def test_unread_timeline_page_prevents_early_completion(self):
        tools = BonusTools()
        arguments = {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'limit': 3}
        url = tools.get_incident_details(**arguments)['url']
        provider = ScriptedProvider([
            call('a', 'get_incident_details', arguments), final(url),
            call('b', 'get_incident_details', dict(arguments, offset=3)),
            call('c', 'get_incident_details', dict(arguments, offset=6)), final(url)])
        result = run_agent('Đọc toàn bộ timeline Vercel', provider, tools, max_steps=7)
        self.assertEqual(result['status'], 'completed')
        event = next(t for t in result['trace'] if t['event'] == 'validation_pending_pages')
        self.assertEqual(event['pages'][0]['offset'], 3)

    def test_claiming_retry_does_not_replace_an_actual_retry(self):
        tools = BonusTools(scenario='rate_limit_once')
        provider = ScriptedProvider([
            call('a', 'get_vercel_status', {}), final('Đã retry rồi.'),
            call('b', 'get_vercel_status', {}), final()])
        result = run_agent('Kiểm tra Vercel', provider, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any(t['event'] == 'validation_pending_retry' for t in result['trace']))
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 2)

    def test_scope_question_requires_incident_details(self):
        tools = BonusTools()
        incident = tools.status('vercel', 'Builds')['incidents'][0]
        args = {'provider': 'vercel', 'incident_id': incident['id']}
        url = tools.get_incident_details(**args)['url']
        provider = ScriptedProvider([
            call('a', 'get_vercel_status', {'component': 'Builds'}), final('Ảnh hưởng build.'),
            call('b', 'get_incident_details', args), final(url)])
        result = run_agent('Xem incident Vercel Builds và phạm vi ảnh hưởng', provider, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any(t['event'] == 'validation_missing_evidence' for t in result['trace']))

    def test_last_page_does_not_hide_a_skipped_middle_page(self):
        tools = BonusTools()
        args = {'provider': 'vercel', 'incident_id': 'sps6n39gm4sg', 'limit': 3}
        url = tools.get_incident_details(**args)['url']
        provider = ScriptedProvider([
            call('a', 'get_incident_details', args),
            call('b', 'get_incident_details', dict(args, offset=6)), final(url),
            call('c', 'get_incident_details', dict(args, offset=3)), final(url)])
        result = run_agent('Đọc timeline Vercel', provider, tools)
        self.assertEqual(result['status'], 'completed')
        event = next(t for t in result['trace'] if t['event'] == 'validation_pending_pages')
        self.assertEqual(event['pages'][0]['offset'], 3)
