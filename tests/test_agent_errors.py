"""Các nhánh lỗi và giới hạn nguồn mà model thật có thể gặp."""
import unittest

from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, final, tool_call


class AgentErrorTests(unittest.TestCase):
    def test_provider_exception_is_redacted(self):
        class BrokenProvider:
            def complete(self, messages, schemas):
                raise RuntimeError('secret-key-in-upstream-error')
        result = run_agent('x', BrokenProvider(), StatusTools())
        self.assertEqual(result['status'], 'error')
        self.assertNotIn('secret-key', str(result))
        self.assertEqual(result['trace'][0]['event'], 'provider_error')

    def test_non_object_json_returns_invalid_arguments(self):
        provider = FakeProvider([tool_call('a', 'get_status', '[]'), final()])
        result = run_agent('x', provider, StatusTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['trace'][1]['result']['error'], 'INVALID_ARGUMENTS')

    def test_every_successful_incident_requires_its_source(self):
        tools = StatusTools()
        first = tools.get_incident_details('github', 'xr3myzj7ms51')['url']
        second = tools.get_incident_details('cloudflare', 'wp49bp8bqo6c')['url']
        provider = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            tool_call('b', 'get_incident_details', '{"provider":"cloudflare","incident_id":"wp49bp8bqo6c"}'),
            final(first), final(first + ' ' + second)])
        result = run_agent('So sánh', provider, tools, max_steps=4)
        self.assertEqual(result['status'], 'completed')
        validation = next(t for t in result['trace'] if t['event'] == 'validation_missing_source')
        self.assertEqual(validation['missing_urls'], [second])

    def test_malformed_provider_response_is_error(self):
        result = run_agent('x', FakeProvider([{'message': None, 'calls': [], 'finish': 'stop'}]), StatusTools())
        self.assertEqual(result['status'], 'error')

    def test_invalid_budget_makes_no_model_call(self):
        provider = FakeProvider([])
        for budget in (0, -1, True):
            self.assertEqual(run_agent('x', provider, StatusTools(), budget)['status'], 'error')
        self.assertEqual(provider.histories, [])

    def test_linked_incident_must_be_read_before_investigation_finishes(self):
        tools = StatusTools()
        first = tools.get_incident_details('github', 'h02n9572mx9y')['url']
        second = tools.get_incident_details('github', 'xr3myzj7ms51')['url']
        provider = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"h02n9572mx9y"}'),
            final(first),
            tool_call('b', 'get_incident_details', '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final(first + ' ' + second)])
        result = run_agent('Điều tra nguyên nhân theo liên kết', provider, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(any(t['event'] == 'validation_missing_evidence' for t in result['trace']))

    def test_historical_incident_does_not_replace_status_check(self):
        tools = StatusTools()
        url = tools.get_incident_details('github', 't89g2q1800fr')['url']
        provider = FakeProvider([
            tool_call('a', 'get_incident_details', '{"provider":"github","incident_id":"t89g2q1800fr"}'),
            final(url), tool_call('b', 'get_status', '{"provider":"github","component":"Actions"}'), final(url)])
        result = run_agent('Actions đang outage vì incident này?', provider, tools)
        self.assertEqual(result['status'], 'completed')
        validation = next(t for t in result['trace'] if t['event'] == 'validation_missing_evidence')
        self.assertEqual(validation['pending_status'], ['github'])
