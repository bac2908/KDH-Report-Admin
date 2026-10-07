"""Meta OAuth contract/security tests. All provider traffic is mocked."""
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import requests

import test_app
import test_postgres
from kdh.core import Problem, digest, load_config, pack
from kdh.meta import Meta


class MetaCases:
    def prepare(self):
        self.meta = self.app.extensions['meta']
        self.app.config.update(META_APP_ID='123456', META_APP_SECRET='test-meta-secret',
                               META_CONFIG_ID='654321', META_GRAPH_VERSION='v26.0',
                               META_REDIRECT_URI=self.app.config['APP_URL'] + '/api/meta/callback')
        self.expiry = int((datetime.now(timezone.utc) + timedelta(days=60)).timestamp())
        self.metadata = {'is_valid': True, 'type': 'USER', 'app_id': '123456', 'user_id': 'test-user',
                         'expires_at': self.expiry, 'data_access_expires_at': self.expiry,
                         'scopes': ['public_profile', 'pages_show_list', 'pages_read_engagement', 'ads_read']}

    def post(self, path, data=None):
        return self.client.post(path, json=data or {}, headers=self.headers)

    def start(self):
        response = self.post('/api/meta/connect')
        self.assertEqual(response.status_code, 200, response.json)
        url = urlsplit(response.json['url'])
        self.assertEqual((url.scheme, url.netloc, url.path), ('https', 'www.facebook.com', '/v26.0/dialog/oauth'))
        params = parse_qs(url.query)
        self.assertNotIn('scope', params)
        self.assertEqual(params['config_id'], ['654321'])
        self.assertEqual(params['override_default_response_type'], ['true'])
        self.assertEqual(params['response_type'], ['code'])
        self.assertNotIn('client_secret', params)
        return params['state'][0]

    def callback(self, state, **query):
        return self.client.get('/api/meta/callback', query_string={'state': state, 'code': 'test-code', **query})

    def provider(self, method, url, **kwargs):
        self.assertEqual(kwargs['allow_redirects'], False)
        self.assertEqual(kwargs['timeout'], (3, 5))
        path = urlsplit(url).path
        # Check the actual prepared URL too: secrets may travel only in the
        # backend POST body / Authorization header, never in its query string.
        prepared = requests.Request(method, url, params=kwargs.get('params'),
                                    data=kwargs.get('data'), headers=kwargs['headers']).prepare()
        for secret in ('test-short-token', 'test-long-token', 'test-meta-secret', 'test-code'):
            self.assertNotIn(secret, prepared.url)
        params = kwargs.get('data', kwargs.get('params'))
        if path == '/v26.0/oauth/access_token':
            self.assertEqual(method, 'POST')
            self.assertEqual(params['method'], 'GET')
            self.assertIsNone(kwargs.get('params'))
            self.assertEqual(params['client_secret'], 'test-meta-secret')
            result = {'access_token': 'test-long-token' if params.get('grant_type') else 'test-short-token'}
        elif path == '/v26.0/debug_token':
            self.assertEqual(method, 'POST')
            self.assertIsNone(kwargs.get('params'))
            self.assertEqual(params, {'input_token': 'test-long-token', 'method': 'GET'})
            self.assertEqual(kwargs['headers'], {'Authorization': 'Bearer 123456|test-meta-secret'})
            result = {'data': self.metadata}
        elif path == '/v26.0/me':
            self.assertEqual(params['fields'], 'id,name')
            self.assertEqual(params['appsecret_proof'], self.meta.proof('test-long-token'))
            self.assertEqual(kwargs['headers'], {'Authorization': 'Bearer test-long-token'})
            result = {'id': 'test-user', 'name': 'OAuth Test User'}
        elif path == '/v26.0/me/permissions':
            self.assertEqual(method, 'DELETE')
            result = {'success': True}
        else:
            self.fail('Unexpected Meta endpoint: ' + path)
        return SimpleNamespace(status_code=200, json=lambda: result)

    def connect(self):
        state = self.start()
        with patch('kdh.meta.requests.request', side_effect=self.provider) as provider:
            response = self.callback(state)
        self.assertEqual(response.location, '/#connections/facebook?oauth=success')
        self.assertEqual(provider.call_count, 4)
        return state

    def test_not_configured_never_starts_oauth_or_exposes_credentials(self):
        for field in ('META_APP_ID', 'META_APP_SECRET', 'META_CONFIG_ID'):
            with self.subTest(field=field), patch.dict(self.app.config, {field: ''}), \
                    patch('kdh.meta.requests.request', side_effect=AssertionError('Not configured')):
                status = self.client.get('/api/meta')
                self.assertFalse(status.json['configured'])
                self.assertFalse(status.json['connected'])
                self.assertEqual(self.post('/api/meta/connect').status_code, 503)
                self.assertIsNone(self.store.one('SELECT * FROM meta_oauth_states'))
                self.assertNotIn('test-meta-secret', status.get_data(as_text=True))

    def test_configuration_supports_localhost_and_preserves_explicit_redirect(self):
        for origin in ('http://localhost:8090', 'http://127.0.0.1:8090'):
            with patch.dict(os.environ, {'APP_URL': origin, 'META_REDIRECT_URI': '',
                                        'META_APP_ID': '123456', 'META_APP_SECRET': 'test-meta-secret',
                                        'META_CONFIG_ID': '654321'}):
                config = load_config()
            self.assertEqual(config['META_REDIRECT_URI'], origin + '/api/meta/callback')
            with patch.dict(self.app.config, {key: config[key] for key in
                            ('APP_URL', 'META_REDIRECT_URI', 'META_APP_ID', 'META_APP_SECRET', 'META_CONFIG_ID')}):
                url = self.post('/api/meta/connect').json['url']
                self.assertEqual(parse_qs(urlsplit(url).query)['redirect_uri'], [origin + '/api/meta/callback'])
        with patch.dict(os.environ, {'APP_URL': 'http://localhost:8090',
                                    'META_REDIRECT_URI': 'https://configured.example/api/meta/callback'}):
            self.assertEqual(load_config()['META_REDIRECT_URI'], 'https://configured.example/api/meta/callback')

    def test_connect_encrypts_and_status_is_local_allowlist_without_jobs_or_assets(self):
        before = {table: self.store.all('SELECT * FROM ' + table) for table in
                  ('jobs', 'datasets', 'source_assets', 'sync_runs', 'daily_metrics', 'report_bundles')}
        self.connect()
        raw = self.store.one('SELECT value FROM secrets WHERE name=?', (self.meta.secret_name,))['value']
        self.assertNotIn(b'test-long-token', bytes(raw))
        # Another service instance uses the same persisted key and database.
        second = Meta(self.store, self.app.config, self.app.extensions['google'].cipher)
        self.assertEqual(second.read()['access_token'], 'test-long-token')
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Status cannot call provider')):
            status = self.client.get('/api/meta')
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json['connected'])
        self.assertEqual(status.json['account_name'], 'OAuth Test User')
        self.assertEqual(status.json['client_id'], 'client_kinderhealth')
        self.assertEqual(status.json['scopes'], self.metadata['scopes'])
        self.assertEqual(status.headers['Cache-Control'], 'no-store')
        public = status.get_data(as_text=True) + pack(self.store.all('SELECT * FROM events'))
        for secret in ('test-long-token', 'test-short-token', 'test-meta-secret', 'test-code', 'access_token', 'appsecret_proof'):
            self.assertNotIn(secret, public)
        connection = self.store.one("SELECT * FROM connections WHERE provider='meta' AND status='connected'")
        self.assertEqual(connection['secret_name'], self.meta.secret_name)
        self.assertEqual(connection['client_id'], 'client_kinderhealth')
        for table, rows in before.items():
            self.assertEqual(self.store.all('SELECT * FROM ' + table), rows)

    def test_reconnect_is_atomic_and_reuses_connection(self):
        self.connect()
        original = self.meta.read()
        connection = self.store.one("SELECT * FROM connections WHERE provider='meta'")
        state = self.start()
        with patch('kdh.meta.requests.request', side_effect=self.provider), \
                patch.object(self.meta.platform, 'upsert_connection', side_effect=Problem('Storage unavailable', 503)):
            self.assertIn('oauth=failed', self.callback(state).location)
        self.assertEqual(self.meta.read(), original)
        self.assertEqual(self.store.one("SELECT * FROM connections WHERE provider='meta'"), connection)
        self.connect()
        connections = self.store.all("SELECT * FROM connections WHERE provider='meta'")
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]['id'], connection['id'])

    def test_state_is_hashed_expires_single_use_and_separate_from_google(self):
        self.app.config.update(GOOGLE_CLIENT_ID='google-test', GOOGLE_CLIENT_SECRET='google-test-secret')
        session_id = digest(self.client.get_cookie('kdh_session').value)
        google_url = self.app.extensions['google'].authorization_url(session_id)
        google_state = parse_qs(urlsplit(google_url).query)['state'][0]
        state = self.start()
        row = self.store.one('SELECT * FROM meta_oauth_states')
        self.assertEqual(row['state'], digest(state))
        self.assertEqual(row['session_id'], session_id)
        self.assertNotIn('test-meta-secret', pack(row))
        self.assertIsNotNone(self.store.one('SELECT * FROM oauth_states'))
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Invalid states cannot call Meta')):
            for invalid in ('', 'wrong', google_state):
                self.assertIn('oauth=failed', self.callback(invalid).location)
            self.store.execute('UPDATE meta_oauth_states SET expires_at=?', ('2000-01-01T00:00:00+00:00',))
            self.assertIn('oauth=failed', self.callback(state).location)
        used = self.connect()
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Replay cannot call Meta')):
            self.assertIn('oauth=failed', self.callback(used).location)

    def test_state_is_bound_to_original_session_and_configuration(self):
        state = self.start()
        other = self.app.test_client()
        self.store.execute('UPDATE meta_oauth_states SET session_id=?', ('different-session',))
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Invalid state')):
            self.assertIn('oauth=failed', self.callback(state).location)
            self.assertEqual(other.get('/api/meta/callback?state=' + state).status_code, 401)
            for field, changed in [('META_APP_SECRET', 'changed-secret'), ('META_CONFIG_ID', '999999')]:
                state = self.start()
                with patch.dict(self.app.config, {field: changed}):
                    self.assertIn('oauth=failed', self.callback(state).location)

    def test_denied_and_missing_code_consume_state_without_reflecting_errors(self):
        for query, result in [({'error': 'access_denied', 'error_description': 'test-secret'}, 'denied'),
                              ({'error': 'test-secret'}, 'failed'), ({'code': ''}, 'failed')]:
            state = self.start()
            with patch('kdh.meta.requests.request', side_effect=AssertionError('No code exchange')):
                response = self.callback(state, **query)
                self.assertEqual(response.location, '/#connections/facebook?oauth=' + result)
                self.assertIn('oauth=failed', self.callback(state).location)
            self.assertIsNone(self.store.one('SELECT * FROM meta_oauth_states'))

    def test_provider_errors_are_sanitized_and_keep_previous_connection(self):
        self.connect()
        original = self.meta.read()
        responses = [SimpleNamespace(status_code=400, json=lambda: {'error': {'message': 'test-meta-secret'}}),
                     SimpleNamespace(status_code=302, json=lambda: {}),
                     SimpleNamespace(status_code=200, json=lambda: []),
                     SimpleNamespace(status_code=200, json=lambda: {'error': 'test-long-token'}),
                     SimpleNamespace(status_code=200, json=lambda: {}),
                     SimpleNamespace(status_code=200, json=lambda: (_ for _ in ()).throw(ValueError('private')))]
        for response in responses:
            state = self.start()
            with patch('kdh.meta.requests.request', return_value=response):
                self.assertEqual(self.callback(state).location, '/#connections/facebook?oauth=failed')
            self.assertEqual(self.meta.read(), original)
        state = self.start()
        with patch('kdh.meta.requests.request', side_effect=requests.Timeout('private-token')):
            self.assertEqual(self.callback(state).location, '/#connections/facebook?oauth=failed')
        self.assertEqual(self.meta.read(), original)

    def test_wrong_app_invalid_expired_and_wrong_token_type_are_rejected(self):
        valid = dict(self.metadata)
        for invalid in ({'app_id': 'other'}, {'is_valid': False}, {'type': 'PAGE'}, {'user_id': 'wrong-user'},
                        {'expires_at': 0}, {'expires_at': 'private'}, {'data_access_expires_at': 1},
                        {'scopes': []}, {'scopes': [None]}, {'scopes': ['public_profile']},
                        *({'scopes': [scope for scope in valid['scopes'] if scope != missing]}
                          for missing in ('pages_show_list', 'pages_read_engagement', 'ads_read'))):
            with self.subTest(invalid=invalid):
                self.metadata = {**valid, **invalid}
                state = self.start()
                with patch('kdh.meta.requests.request', side_effect=self.provider):
                    self.assertIn('oauth=failed', self.callback(state).location)
                self.assertIsNone(self.meta.read())
                self.assertIsNone(self.store.one("SELECT * FROM connections WHERE provider='meta'"))

    def test_status_requires_reauthorization_after_business_config_or_permissions_change(self):
        self.connect()
        with patch.dict(self.app.config, {'META_CONFIG_ID': '999999'}):
            self.assertEqual(self.client.get('/api/meta').json['status'], 'reconnect_required')
        with patch.dict(self.app.config, {'META_CONFIG_ID': 'not-a-config-id'}):
            self.assertFalse(self.client.get('/api/meta').json['configured'])
            self.assertEqual(self.post('/api/meta/connect').status_code, 503)
        token = self.meta.read()
        token['scopes'] = ['public_profile']
        self.store.execute('UPDATE secrets SET value=? WHERE name=?',
                           (self.meta.cipher.encrypt(pack(token).encode()), self.meta.secret_name))
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Status must stay local')):
            status = self.client.get('/api/meta').json
        self.assertFalse(status['connected'])
        self.assertTrue(status['has_connection'])
        self.assertEqual(status['status'], 'reconnect_required')

    def test_expiry_app_change_and_unreadable_credentials_are_honest_statuses(self):
        self.connect()
        token = self.meta.read()
        token['expires_at'] = '2000-01-01T00:00:00+00:00'
        self.store.execute('UPDATE secrets SET value=? WHERE name=?',
                           (self.meta.cipher.encrypt(pack(token).encode()), self.meta.secret_name))
        self.assertEqual(self.client.get('/api/meta').json['status'], 'expired')
        self.assertFalse(self.client.get('/api/meta').json['connected'])
        self.app.config['META_APP_ID'] = '987654'
        self.assertEqual(self.client.get('/api/meta').json['status'], 'reconnect_required')
        self.store.execute('UPDATE secrets SET value=? WHERE name=?', (b'corrupt', self.meta.secret_name))
        self.assertEqual(self.client.get('/api/meta').json['status'], 'error')
        self.assertEqual(self.client.delete('/api/meta', headers=self.headers).json['revoked_at_provider'], False)
        self.assertIsNone(self.meta.read())

    def test_disconnect_revokes_and_cancels_pending_callbacks_but_preserves_google(self):
        self.app.extensions['google'].save({'access_token': 'google-test-token'})
        self.connect()
        state = self.start()
        with patch('kdh.meta.requests.request', side_effect=self.provider) as provider:
            response = self.client.delete('/api/meta', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['revoked_at_provider'])
        self.assertEqual(provider.call_count, 1)
        self.assertFalse(self.client.get('/api/meta').json['has_connection'])
        self.assertIsNone(self.store.one('SELECT * FROM meta_oauth_states'))
        self.assertIsNone(self.meta.read())
        connection = self.store.one("SELECT * FROM connections WHERE provider='meta'")
        self.assertEqual(connection['status'], 'disconnected')
        self.assertIsNone(connection['secret_name'])
        self.assertEqual(self.app.extensions['google'].read()['access_token'], 'google-test-token')
        with patch('kdh.meta.requests.request', side_effect=AssertionError('Cancelled state')):
            self.assertIn('oauth=failed', self.callback(state).location)
            self.assertTrue(self.client.delete('/api/meta', headers=self.headers).json['revoked_at_provider'])

    def test_failed_revocation_still_removes_local_credentials(self):
        self.connect()
        with patch('kdh.meta.requests.request', side_effect=requests.Timeout('test-long-token')):
            response = self.client.delete('/api/meta', headers=self.headers)
        self.assertFalse(response.json['revoked_at_provider'])
        self.assertIn('Meta chưa xác nhận', response.json['message'])
        self.assertNotIn('test-long-token', response.get_data(as_text=True))
        self.assertIsNone(self.meta.read())

    def test_cancelled_inflight_callback_cannot_restore_credentials(self):
        state = self.start()
        def provider(method, url, **kwargs):
            if url.endswith('/me'):
                self.meta.disconnect()
            return self.provider(method, url, **kwargs)
        with patch('kdh.meta.requests.request', side_effect=provider):
            self.assertIn('oauth=failed', self.callback(state).location)
        self.assertIsNone(self.meta.read())

    def test_new_connect_supersedes_inflight_callback(self):
        state = self.start()
        replacement = []
        def provider(method, url, **kwargs):
            if url.endswith('/me'):
                replacement.append(self.start())
            return self.provider(method, url, **kwargs)
        with patch('kdh.meta.requests.request', side_effect=provider):
            self.assertIn('oauth=failed', self.callback(state).location)
        self.assertIsNone(self.meta.read())
        self.assertEqual(self.store.one('SELECT state FROM meta_oauth_states')['state'], digest(replacement[0]))

    def test_session_revocation_while_callback_inflight_prevents_storage(self):
        state = self.start()
        def provider(method, url, **kwargs):
            if url.endswith('/me'):
                self.store.execute('DELETE FROM sessions')
            return self.provider(method, url, **kwargs)
        with patch('kdh.meta.requests.request', side_effect=provider):
            self.assertIn('oauth=failed', self.callback(state).location)
        self.assertIsNone(self.meta.read())

    def test_admin_only_csrf_origin_and_config_validation(self):
        with patch('kdh.meta.requests.request', side_effect=AssertionError('No external calls')):
            anon = self.app.test_client()
            for path, method in [('/api/meta', 'GET'), ('/api/meta', 'DELETE'),
                                 ('/api/meta/connect', 'POST'), ('/api/meta/callback', 'GET')]:
                self.assertEqual(anon.open(path, method=method, headers={'X-KDH-Request': '1'}).status_code, 401)
            self.assertEqual(self.client.post('/api/meta/connect', headers={'X-KDH-Request': '1'}).status_code, 403)
            self.assertEqual(self.client.delete('/api/meta', headers={**self.headers, 'Origin': 'https://evil.invalid'}).status_code, 403)
            self.app.config['META_REDIRECT_URI'] = 'https://evil.invalid/api/meta/callback'
            self.assertEqual(self.post('/api/meta/connect').status_code, 503)
            self.assertFalse(self.client.get('/api/meta').json['configured'])
            self.app.config['META_REDIRECT_URI'] = 'http://['
            self.assertFalse(self.client.get('/api/meta').json['configured'])
            self.store.execute("UPDATE users SET role='viewer'")
            for path, method in [('/api/meta', 'GET'), ('/api/meta', 'DELETE'),
                                 ('/api/meta/connect', 'POST'), ('/api/meta/callback', 'GET')]:
                self.assertEqual(self.client.open(path, method=method, headers=self.headers).status_code, 403)


class SQLiteMetaTest(MetaCases, unittest.TestCase):
    def setUp(self):
        test_app.AppTest.setUp(self)
        self.prepare()

    tearDown = test_app.AppTest.tearDown


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to an isolated PostgreSQL test database')
class PostgresMetaTest(MetaCases, unittest.TestCase):
    def setUp(self):
        test_postgres.PostgresTest.setUp(self)
        self.app, self.client = self.apps[0], self.clients[0]
        self.prepare()
