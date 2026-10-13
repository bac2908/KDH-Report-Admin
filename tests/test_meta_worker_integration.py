"""Safe Meta queue -> SQLite persistence integration tests; no network/real DB."""
import json
import tempfile
import unittest

from kdh.core import Store, now, pack, uid
from kdh.jobs import Worker
from kdh.platform_data import PlatformData
from kdh.metric_reader import read_metric_series


class FakeMeta:
    client_id = 'client_meta_sandbox'

    def __init__(self, replies):
        self.replies = replies

    def info(self):
        return {'connected': True}

    def read(self):
        return {'account_id': '999123', 'access_token': 'FAKE_USER_TOKEN'}

    def call(self, method, path, *, token=None, params=None):
        if method != 'GET':
            raise AssertionError('Test only supports GET')
        key = (path, (params or {}).get('level'))
        if key not in self.replies:
            raise AssertionError(f'Unexpected Meta endpoint: {key}')
        return self.replies[key]


class FakeGoogle:
    config = {'JOB_MODE': 'request'}


class MetaWorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kdh_meta_test_')
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name, '')  # isolated SQLite, NOT PostgreSQL
        self.platform = PlatformData(self.store)
        self.client_id = 'client_meta_sandbox'
        stamp = now()
        self.store.execute('''INSERT INTO clients
            (id,name,slug,timezone,active,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)''',
            (self.client_id, 'Meta Test Only', 'meta-test-only',
             'Asia/Ho_Chi_Minh', 1, stamp, stamp))
        self.admin_id = uid()
        self.store.execute('''INSERT INTO users
            (id,email,name,password,role,allowed,active,created_at)
            VALUES (?,?,?,?,?,?,?,?)''',
            (self.admin_id, 'meta-test@example.invalid', 'Test Admin',
             'NOT_A_REAL_PASSWORD', 'admin', '[]', 1, stamp))
        self.connection_id = self.platform.upsert_connection(
            client_id=self.client_id, provider='meta',
            external_account_id='999123', account_name='Fake OAuth')

    def run_sync(self, source, external_id, replies):
        asset_type = ('facebook_ad_account' if source == 'facebook_ads'
                      else 'facebook_page')
        asset_id = self.platform.upsert_asset(
            client_id=self.client_id, provider='meta',
            asset_type=asset_type, external_id=external_id,
            name='Fake Asset', connection_id=self.connection_id,
            currency='VND' if source == 'facebook_ads' else None)
        params = {
            'source': source, 'asset_id': asset_id,
            'report_type': ('facebook-ads' if source == 'facebook_ads'
                            else 'facebook-content'),
            'start': '2026-09-01', 'end': '2026-09-02', 'demo': False,
        }
        job_id = uid()
        self.store.execute('''INSERT INTO jobs
            (id,kind,user_id,params,status,active_key,created_at)
            VALUES (?,?,?,?,?,?,?)''',
            (job_id, 'meta_sync', self.admin_id, pack(params),
             'queued', 'fake-' + job_id, now()))
        worker = Worker(self.store, FakeGoogle(), FakeMeta(replies))
        self.assertTrue(worker.run_one(job_id))
        job = self.store.one('SELECT status,error,steps FROM jobs WHERE id=?', (job_id,))
        self.assertEqual(job['status'], 'succeeded', job)
        sync = self.store.one(
            'SELECT * FROM sync_runs WHERE job_id=?', (job_id,))
        self.assertIsNotNone(sync)
        self.assertEqual(sync['status'], 'succeeded', sync)
        snapshot = self.store.one(
            'SELECT payload FROM source_snapshots WHERE sync_run_id=?', (sync['id'],))
        self.assertIsNotNone(snapshot)
        self.assertEqual(json.loads(snapshot['payload'])['data_origin'],
                         'meta_api_unverified')
        self.assertNotIn('FAKE_USER_TOKEN', snapshot['payload'])
        self.assertNotIn('FAKE_PAGE_TOKEN', snapshot['payload'])
        return asset_id, sync, json.loads(job['steps'])

    def test_ads_worker_persists_daily_and_campaign_metrics(self):
        replies = {
            ('act_123/insights', 'account'): {'data': [
                {'date_start': '2026-09-01', 'spend': '100.75',
                 'impressions': '120', 'clicks': '10', 'reach': '90',
                 'actions': [{'action_type': 'lead', 'value': '2'}]},
                {'date_start': '2026-09-02', 'spend': '20.25',
                 'impressions': '50', 'clicks': '4', 'reach': '30',
                 'actions': [{'action_type': 'lead', 'value': '1'}]},
            ]},
            ('act_123/insights', 'campaign'): {'data': [
                {'date_start': '2026-09-01', 'campaign_id': 'campaign1',
                 'campaign_name': 'Mock', 'spend': '100.75',
                 'impressions': '120', 'clicks': '10'},
            ]},
        }
        asset_id, sync, steps = self.run_sync('facebook_ads', 'act_123', replies)
        self.assertEqual(sync['record_count'], 3)
        self.assertEqual(self.store.one(
            "SELECT COUNT(*) AS n FROM daily_metrics WHERE sync_run_id=?",
            (sync['id'],))['n'], 3)
        result = read_metric_series(self.store, metric_id='facebook_ads.spend',
            client_id=self.client_id, allowed_sources={'facebook_ads'},
            start='2026-09-01', end='2026-09-02', asset_id=asset_id)
        self.assertEqual(result['summary']['value'], 121.0)
        self.assertEqual(result['data_origin'], 'persisted_unverified')

    def test_content_worker_preserves_lifetime_counters(self):
        replies = {
            ('me/accounts', None): {'data': [
                {'id': '1234', 'name': 'Fake Page',
                 'access_token': 'FAKE_PAGE_TOKEN'}]},
            ('1234/posts', None): {'data': [
                {'id': '1234_1', 'created_time': '2026-09-01T03:00:00+0000',
                 'reactions': {'summary': {'total_count': 4}},
                 'comments': {'summary': {'total_count': 2}},
                 'shares': {'count': 3}},
            ]},
        }
        asset_id, sync, steps = self.run_sync('facebook_content', '1234', replies)
        self.assertEqual(sync['record_count'], 3)  # two daily rows + one post
        result = read_metric_series(self.store,
            metric_id='facebook_content.posts_published',
            client_id=self.client_id, allowed_sources={'facebook_content'},
            start='2026-09-01', end='2026-09-02', asset_id=asset_id)
        self.assertEqual(result['summary']['value'], 1)
        post = self.store.one("SELECT metrics FROM daily_metrics WHERE entity_type='post'")
        self.assertEqual(json.loads(post['metrics'])['reactions_lifetime'], 4)
        page = self.store.one(
            "SELECT metrics FROM daily_metrics WHERE entity_type='page' LIMIT 1")
        self.assertIsNone(json.loads(page['metrics'])['engagements'])

    def test_empty_ads_creates_no_fake_metrics(self):
        replies = {
            ('act_123/insights', 'account'): {'data': []},
            ('act_123/insights', 'campaign'): {'data': []},
        }
        _, sync, steps = self.run_sync('facebook_ads', 'act_123', replies)
        self.assertEqual(sync['record_count'], 0)
        self.assertEqual(steps[0]['status'], 'no_data')
        self.assertEqual(self.store.one(
            'SELECT COUNT(*) AS n FROM daily_metrics WHERE sync_run_id=?',
            (sync['id'],))['n'], 0)


if __name__ == '__main__':
    unittest.main()
