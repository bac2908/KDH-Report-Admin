"""Report/revision ACL and Admin console tests against isolated stores."""
import json
import os
import unittest

import test_marketing_publication as publication
import test_marketing_verification as fixtures
from kdh.core import digest, pack


class ViewerCases:
    release = publication.PublicationCases.release
    bundle = publication.PublicationCases.bundle
    publish = publication.PublicationCases.publish

    def prepare_viewer(self):
        self.fixture.app.config['REPORT_SERVICE_TOKEN'] = 'test-viewer-service-only'
        response = self.fixture.client.post('/api/users', json={'email': 'viewer@example.test', 'name': 'Isolated viewer',
            'password': 'Viewer-test-password-123', 'role': 'viewer', 'allowed': ['gsc']}, headers=self.fixture.headers)
        self.assertEqual(response.status_code, 201, response.json)
        self.viewer_id = self.store.one('SELECT id FROM users WHERE email=?', ('viewer@example.test',))['id']
        self.browser = self.fixture.app.test_client()
        login = self.browser.post('/api/auth/login', json={'email': 'viewer@example.test', 'password': 'Viewer-test-password-123'}, headers={'X-KDH-Request': '1'})
        self.assertEqual(login.status_code, 200)
        self.viewer_token = self.browser.get_cookie('kdh_session').value
        self.internal_headers = {'Authorization': 'Bearer test-viewer-service-only', 'X-KDH-Viewer-Session': self.viewer_token}

    def grant(self, report_id, minimum=1, maximum=1, active=True):
        return self.fixture.client.post('/api/report-bundles/' + report_id + '/access', headers=self.fixture.headers,
            json={'user_id': self.viewer_id, 'min_revision': minimum, 'max_revision': maximum, 'active': active})

    def read(self, report_id, revision=1):
        return self.browser.get(f'/api/internal/v1/viewer/report-bundles/{report_id}?revision={revision}', headers=self.internal_headers)

    def test_report_grant_required_and_revocation_immediate(self):
        self.release(); report = self.bundle(); self.publish(report, 'final')
        self.assertEqual(self.read(report).status_code, 404)
        self.assertEqual(self.grant(report).status_code, 200)
        self.assertEqual(self.read(report).status_code, 200)
        self.assertEqual(self.grant(report, active=False).status_code, 200)
        self.assertEqual(self.read(report).status_code, 404)
        event = self.store.one("SELECT detail FROM events WHERE action='update_report_viewer_access' ORDER BY at DESC LIMIT 1")
        self.assertIn('before', json.loads(event['detail']))

    def test_revision_range_and_draft_remain_private(self):
        self.release(); report = self.bundle(); self.grant(report)
        self.assertEqual(self.read(report).status_code, 404)
        self.publish(report)
        created = self.fixture.client.post(f'/api/report-bundles/{report}/revisions', json={}, headers=self.fixture.headers)
        self.assertEqual(created.status_code, 201, created.json)
        self.assertEqual(self.read(report, 2).status_code, 404)
        published = self.fixture.client.post(f'/api/report-bundles/{report}/revisions/2/publish', json={'status': 'final'}, headers=self.fixture.headers)
        self.assertEqual(published.status_code, 200, published.json)
        self.assertEqual(self.read(report, 2).status_code, 404)
        listed = self.browser.get('/api/internal/v1/viewer/report-bundles', headers=self.internal_headers)
        self.assertEqual(listed.json['reports'][0]['revision'], 1)
        self.grant(report, maximum=2)
        self.assertEqual(self.read(report, 2).status_code, 200)

    def test_active_session_and_service_identity_both_required(self):
        self.release(); report = self.bundle(); self.publish(report); self.grant(report)
        path = f'/api/internal/v1/viewer/report-bundles/{report}'
        self.assertEqual(self.browser.get(path, headers={'Authorization': 'Bearer test-viewer-service-only'}).status_code, 401)
        self.assertEqual(self.browser.get(path, headers={'X-KDH-Viewer-Session': self.viewer_token}).status_code, 401)
        self.store.execute('DELETE FROM sessions WHERE id=?', (digest(self.viewer_token),))
        self.assertEqual(self.read(report).status_code, 401)

    def test_disabled_user_and_report_type_scope(self):
        self.release(); report = self.bundle(); self.publish(report); self.grant(report)
        self.store.execute('UPDATE users SET allowed=? WHERE id=?', (pack(['ga4']), self.viewer_id))
        self.assertEqual(self.read(report).status_code, 404)
        self.store.execute('UPDATE users SET active=0 WHERE id=?', (self.viewer_id,))
        self.assertEqual(self.read(report).status_code, 401)

    def test_acl_customer_scope_and_snapshot_customer_must_match(self):
        self.release(); report = self.bundle(); self.publish(report); self.grant(report)
        # A grant for a different existing client does not authorize this bundle.
        self.store.execute("INSERT INTO clients (id,name,slug,created_at,updated_at) VALUES ('other-client','Other','other','2026-01-01','2026-01-01')")
        self.store.execute("UPDATE report_viewer_grants SET client_id='other-client' WHERE report_id=?", (report,))
        self.assertEqual(self.read(report).status_code, 404)

    def test_internal_preview_console_and_acl_admin_only(self):
        candidate = self.fixture.candidate()
        path = '/api/internal/v1/marketing-preview/' + candidate
        self.assertEqual(self.browser.get(path, headers=self.internal_headers).status_code, 403)
        admin_headers = {**self.internal_headers, 'X-KDH-Viewer-Session': self.fixture.client.get_cookie('kdh_session').value}
        result = self.fixture.client.get(path, headers=admin_headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertFalse(result.json['publishable'])
        self.assertEqual(self.browser.get('/marketing').status_code, 403)
        self.assertEqual(self.browser.get('/api/marketing/workflow').status_code, 403)
        self.assertEqual(self.fixture.client.get('/marketing').status_code, 200)
        result = self.fixture.client.get('/api/marketing/workflow')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json['snapshots']), 2)
        self.assertNotIn('test-only-access', result.get_data(as_text=True))
        report = self.bundle(candidate)
        self.assertEqual(self.fixture.client.post(f'/api/report-bundles/{report}/access', json={}).status_code, 403)
        self.assertEqual(self.browser.get(f'/api/report-bundles/{report}/access').status_code, 403)

    def test_logout_revoke_only_current_session(self):
        self.assertEqual(self.browser.delete('/api/internal/v1/viewer-session', headers=self.internal_headers).status_code, 200)
        self.assertEqual(self.browser.get('/api/internal/v1/viewer-session', headers=self.internal_headers).status_code, 401)
        self.assertIsNotNone(self.fixture.client.get('/api/auth/me').json['user'])


class SQLiteViewerTests(ViewerCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.VerificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.prepare_viewer()


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PostgresViewerTests(ViewerCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PostgresVerificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.prepare_viewer()
