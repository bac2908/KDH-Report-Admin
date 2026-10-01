"""Run against a disposable Postgres: TEST_DATABASE_URL=postgresql://... ."""
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from unittest.mock import patch

from cryptography.fernet import Fernet

from kdh.app import create_app
from kdh.core import filters
from kdh.jobs import enqueue
from test_app import fixture


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to an isolated Postgres test database')
class PostgresTest(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        self.url = os.environ['TEST_DATABASE_URL']
        self.schema = 'kdh_test_' + uuid4().hex
        with psycopg.connect(self.url, autocommit=True) as db:
            db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        def drop_schema():
            with psycopg.connect(self.url, autocommit=True) as db:
                db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
        self.addCleanup(drop_schema)
        parts = urlsplit(self.url)
        query = dict(parse_qsl(parts.query))
        query['options'] = '-csearch_path=' + self.schema
        database = urlunsplit(parts._replace(query=urlencode(query)))
        self.folders = [tempfile.TemporaryDirectory() for _ in range(2)]
        for folder in self.folders:
            self.addCleanup(folder.cleanup)
        config = {'DATABASE_URL': database, 'ENCRYPTION_KEY': Fernet.generate_key().decode(),
                  'APP_URL': 'https://cloud.example.test', 'VERCEL': True, 'JOB_MODE': 'request',
                  'COOKIE_SECURE': True, 'TESTING': True, 'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': '',
                  'GOOGLE_REDIRECT_URI': 'https://cloud.example.test/api/google/callback',
                  'INITIAL_ADMIN_EMAIL': 'cloud@example.test', 'INITIAL_ADMIN_PASSWORD': 'Cloud-test-password-123'}
        # Two simultaneous cold starts with separate, empty local disks.
        with ThreadPoolExecutor(2) as pool:
            self.apps = list(pool.map(lambda folder: create_app({**config, 'DATA_DIR': folder.name}), self.folders))
        self.store = self.apps[0].extensions['store']
        self.clients = [app.test_client() for app in self.apps]
        auth = self.clients[0].post('/api/auth/login', json={'email': config['INITIAL_ADMIN_EMAIL'],
                                  'password': config['INITIAL_ADMIN_PASSWORD']}, headers={'X-KDH-Request': '1'})
        self.assertEqual(auth.status_code, 200, auth.json)
        self.actor = auth.json['user']['id']
        self.headers = {'X-KDH-Request': '1', 'X-CSRF-Token': auth.json['csrf']}
        self.clients[1].set_cookie('kdh_session', self.clients[0].get_cookie('kdh_session').value)

    def post(self, index, path, data=None):
        return self.clients[index].post(path, json=data or {}, headers=self.headers)

    def test_auth_encryption_reports_and_export_persist_across_instances(self):
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM users')['n'], 1)
        self.assertEqual(self.clients[1].get('/api/auth/me').json['user']['id'], self.actor)
        google1, google2 = [app.extensions['google'] for app in self.apps]
        google1.save({'access_token': 'fake-test-token', 'email': 'fake@example.test'})
        self.assertEqual(google2.read()['access_token'], 'fake-test-token')
        self.assertNotIn(b'fake-test-token', bytes(self.store.one('SELECT value FROM secrets')['value']))
        seed = self.post(0, '/api/demo/seed')
        self.assertEqual(seed.status_code, 200, seed.json)
        self.assertEqual(self.post(1, '/api/demo/seed').json, seed.json)
        self.assertEqual(len(self.clients[1].get('/api/reports').json), 6)
        download = self.clients[1].get('/api/jobs/' + seed.json['export_job_id'] + '/download')
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.data.startswith(b'PK'))
        report = self.clients[1].get('/api/reports').json[0]
        self.assertEqual(self.clients[1].get('/api/reports/' + report['id'] + '/html').status_code, 200)
        self.assertEqual(len(self.clients[1].get('/api/uploads').json), 2)
        self.assertTrue(all(not (self.store.folder / f).exists() for f in ('encryption.key', 'kdh.sqlite3', 'exports')))

    def test_atomic_enqueue_and_processing_claim(self):
        params = filters({'report_type': 'seo', 'start': '2026-01-01', 'end': '2026-01-28', 'compare': False})
        stores = [app.extensions['store'] for app in self.apps]
        with ThreadPoolExecutor(2) as pool:
            queued = list(pool.map(lambda store: enqueue(store, self.actor, 'analysis', params), stores))
        self.assertEqual(queued[0][0], queued[1][0])
        self.assertEqual(sum(created for _, created in queued), 1)
        job_id = queued[0][0]
        entered, release = threading.Event(), threading.Event()
        def slow_fetch(source, p):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('Test timed out')
            return fixture(source, p)
        with patch.object(self.apps[0].extensions['google'], 'fetch', side_effect=slow_fetch) as fetch:
            with ThreadPoolExecutor(1) as pool:
                running = pool.submit(self.post, 0, '/api/jobs/' + job_id + '/process')
                try:
                    self.assertTrue(entered.wait(10))
                    second = self.post(1, '/api/jobs/' + job_id + '/process')
                    self.assertEqual(second.json['status'], 'running', second.json)
                finally:
                    release.set()
                completed = running.result(timeout=15)
            self.assertEqual(completed.json['status'], 'succeeded', completed.json)
            self.assertEqual(fetch.call_count, 3)
        dataset_id = completed.json['dataset_id']
        saved = self.post(1, '/api/datasets/' + dataset_id + '/save')
        self.assertEqual(saved.status_code, 201, saved.json)
        self.assertEqual(self.post(0, '/api/reports/' + saved.json['report_id'] + '/publish').status_code, 200)
        export_id = self.post(1, '/api/datasets/' + dataset_id + '/export').json['job_id']
        self.assertEqual(self.post(0, '/api/jobs/' + export_id + '/process').json['status'], 'succeeded')
        self.assertEqual(self.clients[1].get('/api/jobs/' + export_id + '/download').status_code, 200)

    def test_integrity_error_returns_normal_user_validation(self):
        fields = {'name': 'Duplicate', 'email': 'cloud@example.test', 'password': 'Test-password-123',
                  'role': 'viewer', 'allowed': ['ga4']}
        response = self.post(1, '/api/users', fields)
        self.assertEqual(response.status_code, 409, response.json)

    def test_oauth_callback_can_land_on_a_different_instance(self):
        for app in self.apps:
            app.config.update(GOOGLE_CLIENT_ID='fake-client', GOOGLE_CLIENT_SECRET='fake-secret')
        authorization = self.post(0, '/api/google/connect')
        self.assertEqual(authorization.status_code, 200, authorization.json)
        state = dict(parse_qsl(urlsplit(authorization.json['url']).query))['state']
        responses = [{'access_token': 'fake-access', 'refresh_token': 'fake-refresh', 'expires_in': 3600},
                     {'email': 'data@example.test', 'email_verified': True}]
        with patch('kdh.google.call', side_effect=responses):
            callback = self.clients[1].get('/api/google/callback', query_string={'state': state, 'code': 'fake-code'})
        self.assertEqual(callback.status_code, 302)
        self.assertIn('oauth=success', callback.location)
        job_id = dict(parse_qsl(callback.location.split('?', 1)[1]))['job']
        self.assertEqual(self.apps[0].extensions['google'].read()['email'], 'data@example.test')
        with patch.object(self.apps[0].extensions['google'], 'fetch', side_effect=fixture):
            self.assertEqual(self.post(0, '/api/jobs/' + job_id + '/process').json['status'], 'succeeded')
        again = self.clients[0].get('/api/google/callback', query_string={'state': state, 'code': 'fake-code'})
        self.assertIn('oauth=failed', again.location)

    def test_refresh_cannot_overwrite_a_new_connection_from_another_instance(self):
        first, second = [app.extensions['google'] for app in self.apps]
        first.save({'access_token': 'expired', 'refresh_token': 'old-refresh',
                    'expires_at': '2020-01-01T00:00:00+00:00'})
        def provider(*args, **kwargs):
            second.save({'access_token': 'new-account-token', 'refresh_token': 'new-refresh',
                         'expires_at': '2099-01-01T00:00:00+00:00'})
            return {'access_token': 'old-account-refreshed', 'expires_in': 3600}
        with patch('kdh.google.call', side_effect=provider):
            self.assertEqual(first.access_token(), 'new-account-token')
        self.assertEqual(second.read()['refresh_token'], 'new-refresh')
