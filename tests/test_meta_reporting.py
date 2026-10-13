"""Isolated Meta reader tests; no real Meta credentials or network calls."""
import unittest

from kdh.meta_reporting import MetaReportingReader, validate_range
from kdh.core import Problem


class FakeMeta:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def info(self):
        return {'connected': True}

    def read(self):
        return {'access_token': 'test-user-token'}

    def call(self, method, path, *, token, params):
        self.calls.append((method, path, token, dict(params)))
        assert method == 'GET'
        assert 'access_token' not in params
        key = (path, params.get('level'), params.get('after'))
        return self.responses[key]


class MetaReportingTests(unittest.TestCase):
    def test_discovery_never_returns_page_token(self):
        fake = FakeMeta({
            ('me/adaccounts', None, None): {'data': [{'id': 'act_1234', 'name': 'Ads 1', 'currency': 'VND'}]},
            ('me/accounts', None, None): {'data': [
                {'id': '9876', 'name': 'Test Page', 'access_token': 'PAGE-SECRET', 'tasks': ['ANALYZE']}]},
        })
        result = MetaReportingReader(fake).discover()
        self.assertEqual(result['facebook_ads'][0]['id'], 'act_1234')
        self.assertEqual(result['facebook_content'][0]['id'], '9876')
        self.assertNotIn('PAGE-SECRET', str(result))

    def test_cursor_paging_without_following_next_url(self):
        fake = FakeMeta({
            ('me/adaccounts', None, None): {'data': [{'id': 'act_10'}],
                'paging': {'next': 'https://evil.invalid/?access_token=leak', 'cursors': {'after': 'cursor1'}}},
            ('me/adaccounts', None, 'cursor1'): {'data': [{'id': 'act_20'}]},
            ('me/accounts', None, None): {'data': []},
        })
        data = MetaReportingReader(fake).discover()
        self.assertEqual(len(data['facebook_ads']), 2)
        self.assertEqual(fake.calls[1][3]['after'], 'cursor1')

    def test_ads_totals_do_not_sum_unique_reach(self):
        fake = FakeMeta({
            ('act_123/insights', 'account', None): {'data': [
                {'date_start': '2026-09-01', 'spend': '100.75', 'impressions': '123',
                    'clicks': '11', 'reach': '90', 'actions': [{'action_type': 'lead', 'value': '2'}]},
                {'date_start': '2026-09-02', 'spend': '20.25', 'impressions': '50',
                    'clicks': '4', 'reach': '30', 'actions': [{'action_type': 'lead', 'value': '1'}]}]},
            ('act_123/insights', 'campaign', None): {'data': [
                {'campaign_id': '321', 'campaign_name': 'Campaign A', 'date_start': '2026-09-01',
                 'spend': '100.75', 'impressions': '123', 'clicks': '11'}]},
        })
        result = MetaReportingReader(fake).ads('act_123', '2026-09-01', '2026-09-02')
        self.assertEqual(result['totals']['spend'], 121.0)
        self.assertEqual(result['totals']['leads'], 3.0)
        self.assertIsNone(result['totals']['reach'])
        self.assertEqual(len(result['daily']), 2)
        self.assertEqual(len(result['entries']), 1)
        self.assertNotIn('test-user-token', str(result))

    def test_content_lifetime_engagement_is_not_a_daily_metric(self):
        fake = FakeMeta({
            ('me/accounts', None, None): {'data': [
                {'id': '1234', 'access_token': 'page-secret'}]},
            ('1234/posts', None, None): {'data': [
                {'id': '1234_1', 'created_time': '2026-09-01T03:00:00+0000',
                 'reactions': {'summary': {'total_count': 4}},
                 'comments': {'summary': {'total_count': 2}}, 'shares': {'count': 3}}]},
        })
        result = MetaReportingReader(fake).content('1234', '2026-09-01', '2026-09-02')
        self.assertEqual(result['totals']['posts_published'], 1.0)
        self.assertIsNone(result['daily'][0]['engagements'])
        self.assertEqual(result['entries'][0]['reactions_lifetime'], 4)
        self.assertEqual(result['entries'][0]['comments_lifetime'], 2)
        self.assertEqual(result['entries'][0]['shares_lifetime'], 3)
        self.assertIsNone(result['totals']['engagements'])
        self.assertEqual(result['daily'][1]['posts_published'], 0)
        self.assertNotIn('page-secret', str(result))

    def test_empty_ads_are_no_data_not_fake_performance(self):
        fake = FakeMeta({
            ('act_123/insights', 'account', None): {'data': []},
            ('act_123/insights', 'campaign', None): {'data': []},
        })
        result = MetaReportingReader(fake).ads('act_123', '2026-09-01', '2026-09-02')
        self.assertEqual(result['status'], 'no_data')
        self.assertIsNone(result['latest_available_date'])
        self.assertIsNone(result['totals']['spend'])

    def test_missing_page_token_blocks_content(self):
        fake = FakeMeta({('me/accounts', None, None): {'data': [{'id': '1234'}]}})
        with self.assertRaises(Problem):
            MetaReportingReader(fake).content('1234', '2026-09-01', '2026-09-02')

    def test_broken_meta_pagination_fails_closed(self):
        fake = FakeMeta({
            ('me/adaccounts', None, None): {'data': [], 'paging': {'next': 'https://host/next'}},
        })
        with self.assertRaises(Problem):
            MetaReportingReader(fake).discover()

    def test_range_validation(self):
        with self.assertRaises(Problem):
            validate_range('2026-09-02', '2026-09-01')
        with self.assertRaises(Problem):
            validate_range('2025-01-01', '2026-09-01')


if __name__ == '__main__':
    unittest.main()
