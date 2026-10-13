"""One-use handoff against disposable DBs, never runtime publications/grants."""
import base64
import hashlib
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit
import test_marketing_verification as fixtures
from test_marketing_publication import PublicationCases
from kdh.core import digest


class HandoffCases:
    release = PublicationCases.release
    bundle = PublicationCases.bundle
    publish = PublicationCases.publish

    def prepare(self):
        self.store, self.app = self.fixture.store, self.fixture.app
        self.app.config.update(APP_URL='http://localhost', REPORT_SERVICE_TOKEN='isolated-service', REPORT_NEW_BASE_URL='https://new.example.test')
        self.service = {'Authorization': 'Bearer isolated-service'}
        self.release(); self.report_id = self.bundle()
        self.assertEqual(self.publish(self.report_id, 'final').status_code, 200)

    def transaction(self, **changes):
        self.verifier, self.state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        self.data = {'state': self.state, 'challenge': base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).decode().rstrip('='),
            'client_id': 'client_kinderhealth', 'target_id': self.report_id, 'revision': 1, 'mode': 'published',
            'audience': 'https://new.example.test', 'callback': 'https://new.example.test/auth/handoff/callback', **changes}
        result = self.app.test_client().post('/api/internal/v1/handoffs', json=self.data, headers=self.service)
        self.assertEqual(result.status_code, 200, result.json)
        self.tx = result.json['transaction']
        return result.json

    def code(self, browser=None):
        result = (browser or self.fixture.client).get('/viewer/authorize?transaction=' + self.tx)
        self.assertEqual(result.status_code, 303, result.json)
        parsed = urlsplit(result.location)
        self.assertEqual(parsed.query, '')
        values = {k: v[0] for k, v in parse_qs(parsed.fragment).items()}
        self.redeem_data = {**values, 'verifier': self.verifier, 'audience': self.data['audience'], 'callback': self.data['callback']}
        self.assertEqual(values['state'], self.state)
        row = self.store.one('SELECT * FROM viewer_handoffs WHERE id=?', (self.tx,))
        self.assertEqual(row['code_hash'], digest(values['code']))
        self.assertNotIn(values['code'], str(row))

    def redeem(self, **changes):
        return self.app.test_client().post('/api/internal/v1/handoffs/redeem', json={**self.redeem_data, **changes}, headers=self.service)

    def read(self, session, revision=1):
        return self.app.test_client().get(f'/api/internal/v1/viewer/report-bundles/{self.report_id}?revision={revision}',
            headers={**self.service, 'X-KDH-Viewer-Session': session})

    def test_exact_scope_new_token_replay_and_no_admin_session(self):
        self.transaction(); self.code(); result = self.redeem()
        self.assertEqual(result.status_code, 200, result.json)
        session = result.json['session']
        self.assertNotEqual(session, self.fixture.client.get_cookie('kdh_session').value)
        self.assertEqual(self.read(session).status_code, 200)
        self.assertEqual(self.read(session, revision=2).status_code, 404)
        browser = self.app.test_client(); browser.set_cookie('kdh_session', session)
        self.assertIsNone(browser.get('/api/auth/me').json['user'])
        self.assertEqual(self.redeem().status_code, 400)

    def test_binding_and_scope_tampering_rejected(self):
        self.transaction(); self.code()
        for change in ({'verifier': secrets.token_urlsafe(48)}, {'state': secrets.token_urlsafe(32)},
                {'code': secrets.token_urlsafe(48)}, {'audience': 'https://evil.example.test'},
                {'callback': 'https://evil.example.test/callback'}, {'revision': 2}, {'mode': 'preview'},
                {'client_id': 'other'}, {'target_id': 'rpt_' + 'b' * 32}):
            with self.subTest(change=list(change)):
                self.assertEqual(self.redeem(**change).status_code, 400)
        self.assertEqual(self.redeem().status_code, 200)

    def test_expiry(self):
        self.transaction(); self.code()
        self.store.execute("UPDATE viewer_handoffs SET code_expires_at='2000-01-01' WHERE id=?", (self.tx,))
        self.assertEqual(self.redeem().status_code, 400)

    def test_concurrent_redemption_exactly_one_wins(self):
        self.transaction(); self.code()
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(lambda _: self.redeem().status_code, range(2)))
        self.assertEqual(sorted(codes), [200, 400])

    def test_parent_revocation_immediate(self):
        self.transaction(); self.code(); session = self.redeem().json['session']
        self.store.execute('DELETE FROM sessions WHERE id=?', (digest(self.fixture.client.get_cookie('kdh_session').value),))
        self.assertEqual(self.read(session).status_code, 401)

    def test_active_and_role_rechecked(self):
        self.transaction(); self.code(); session = self.redeem().json['session']
        self.store.execute("UPDATE users SET role='viewer' WHERE id=?", (self.fixture.actor,))
        self.assertEqual(self.read(session).status_code, 404)
        self.store.execute('UPDATE users SET active=0 WHERE id=?', (self.fixture.actor,))
        self.assertEqual(self.read(session).status_code, 401)

    def test_revocation_before_redeem(self):
        self.transaction(); self.code()
        self.store.execute('DELETE FROM sessions WHERE id=?', (digest(self.fixture.client.get_cookie('kdh_session').value),))
        self.assertEqual(self.redeem().status_code, 401)

    def test_preview_is_separate(self):
        self.transaction(mode='preview', target_id=self.candidate_id, revision=0); self.code()
        session = self.redeem().json['session']
        self.assertEqual(self.read(session).status_code, 404)
        browser = self.app.test_client(); headers = {**self.service, 'X-KDH-Viewer-Session': session}
        self.assertEqual(browser.get('/api/internal/v1/marketing-preview/' + self.candidate_id, headers=headers).status_code, 200)
        self.assertEqual(browser.get('/api/internal/v1/marketing-preview/' + 'b' * 32, headers=headers).status_code, 403)

    def test_login_resumes_same_report(self):
        self.transaction(); browser = self.app.test_client()
        result = browser.get('/viewer/authorize?transaction=' + self.tx)
        self.assertEqual(result.status_code, 200)
        self.assertIn('data-transaction="' + self.tx, result.text)
        browser.post('/api/auth/login', json={'email': self.app.config['INITIAL_ADMIN_EMAIL'], 'password': self.app.config['INITIAL_ADMIN_PASSWORD']}, headers={'X-KDH-Request': '1'})
        self.code(browser)
        self.assertEqual(self.redeem().json['target_id'], self.report_id)

    def test_identity_conflict_preserves_existing_session(self):
        self.transaction(); self.code()
        self.fixture.client.post('/api/users', json={'email': 'other@example.test', 'name': 'Other', 'password': 'Other-Password-12345', 'role': 'viewer', 'allowed': []}, headers=self.fixture.headers)
        browser = self.app.test_client()
        browser.post('/api/auth/login', json={'email': 'other@example.test', 'password': 'Other-Password-12345'}, headers={'X-KDH-Request': '1'})
        result = browser.post('/api/internal/v1/handoffs/redeem', json=self.redeem_data,
            headers={**self.service, 'X-KDH-Viewer-Session': browser.get_cookie('kdh_session').value})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.redeem().status_code, 200)

    def test_draft_allowlist_and_service_auth(self):
        self.transaction()
        for change in ({'callback': 'https://evil.example.test/'}, {'client_id': 'other'}, {'audience': 'wrong'}):
            self.assertEqual(self.app.test_client().post('/api/internal/v1/handoffs', json={**self.data, **change}, headers=self.service).status_code, 400)
        self.assertEqual(self.app.test_client().post('/api/internal/v1/handoffs', json=self.data).status_code, 401)
        self.transaction(target_id=self.bundle(self.candidate_id))
        self.assertEqual(self.fixture.client.get('/viewer/authorize?transaction=' + self.tx).status_code, 404)


class SQLiteHandoffTests(HandoffCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.VerificationTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups); self.prepare()


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PostgresHandoffTests(HandoffCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PostgresVerificationTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups); self.prepare()
