"""Synthetic provider transport in isolated DBs; never KinderHealth runtime data."""
import copy
import json
import os
import unittest
from unittest.mock import patch

import test_marketing_review as auth_fixture
from kdh.core import filters, pack
from kdh.jobs import enqueue


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = auth_fixture.MarketingReviewTests('test_no_data_is_not_approvable')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.app, self.store = self.fixture.app, self.fixture.store
        self.client, self.headers = self.fixture.client, self.fixture.headers
        self.actor = self.fixture.actor
        self.prepare()

    def prepare(self):
        no_http = patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden in test'))
        no_http.start()
        self.addCleanup(no_http.stop)
        self.google = self.app.extensions['google']
        self.app.config.update(GSC_PROPERTY='https://fixture.example.test/', GA4_PROPERTY_ID='fixture-ga4')
        self.google.save({'email': 'fixture@example.test', 'access_token': 'test-only-access',
                          'expires_at': '2099-01-01T00:00:00+00:00'})
        self.params = filters({'report_type': 'gsc', 'start': '2026-09-01', 'end': '2026-09-03', 'compare': True})

    @staticmethod
    def response(method, url, **kwargs):
        query = kwargs['json']
        previous = query['startDate'] == '2026-08-29'
        dates = ('2026-08-29', '2026-08-30', '2026-08-31') if previous else ('2026-09-01', '2026-09-02', '2026-09-03')
        clicks = [5, 6, 7] if previous else [10, 20, 30]
        dims = query.get('dimensions', [])
        if dims == ['date']:
            return {'rows': [{'keys': [day], 'clicks': value, 'impressions': value * 10,
                              'ctr': 0.1, 'position': 8.4} for day, value in zip(dates, clicks)]}
        if dims == ['query']:
            return {'rows': [{'keys': ['fixture query'], 'clicks': 10, 'impressions': 100, 'ctr': 0.1, 'position': 8.4}]}
        return {'rows': [{'clicks': sum(clicks), 'impressions': sum(clicks) * 10, 'ctr': 0.1, 'position': 8.4}]}

    def sync(self):
        job_id, _ = enqueue(self.store, self.actor, 'analysis', self.params)
        with patch('kdh.google.call', side_effect=self.response):
            self.assertTrue(self.app.extensions['worker'].run_one(job_id=job_id))
        job = self.store.one('SELECT * FROM jobs WHERE id=?', (job_id,))
        self.assertEqual(job['status'], 'succeeded')
        run = self.store.one('SELECT * FROM sync_runs WHERE job_id=?', (job_id,))
        self.assertIsNotNone(self.store.one('SELECT * FROM source_attestations WHERE sync_run_id=?', (run['id'],)))
        return run

    def candidate(self):
        self.run = self.sync()
        result = self.client.post('/api/marketing/datasets', json={
            'source': 'gsc', 'start': self.params['start'], 'end': self.params['end'],
            'asset_id': self.run['asset_id']}, headers=self.headers)
        self.assertEqual(result.status_code, 201, result.json)
        self.origin_id = result.json['dataset_id']
        review = self.client.get(f'/api/marketing/datasets/{self.origin_id}/review').json
        approved = self.client.post(f'/api/marketing/datasets/{self.origin_id}/review', json={
            'decision': 'approved_internal', 'note': 'Fixture independent review for isolated tests.',
            'expected_sha256': review['dataset_sha256']}, headers=self.headers)
        self.assertEqual(approved.status_code, 201, approved.json)
        candidate = self.client.post(f'/api/marketing/datasets/{self.origin_id}/release-candidates', json={
            'expected_sha256': review['dataset_sha256'], 'expected_review_id': approved.json['review_id']}, headers=self.headers)
        self.assertEqual(candidate.status_code, 201, candidate.json)
        return candidate.json['release_dataset_id']

    def check(self, candidate):
        response = self.client.get(f'/api/marketing/release-candidates/{candidate}/source-check')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def approve(self, candidate, decision='release_approved', **extra):
        checks = self.check(candidate)
        return self.client.post(f'/api/marketing/release-candidates/{candidate}/approval', json={
            'decision': decision, 'note': 'Release reviewed using isolated fixture provenance.',
            'expected_candidate_sha256': checks['candidate_sha256'],
            'expected_dataset_sha256': checks['dataset_sha256'],
            'expected_review_id': checks['internal_review_id'], **extra}, headers=self.headers)

    def test_confirmed_source_and_comparison_then_approved_without_publication(self):
        candidate = self.candidate()
        checks = self.check(candidate)
        self.assertEqual(checks['issues'], [])
        self.assertEqual(checks['state'], 'provider_origin_confirmed')
        self.assertFalse(checks['publishable'])
        data = json.loads(self.store.one('SELECT data FROM datasets WHERE id=?', (candidate,))['data'])
        clicks = next(card for card in data['marketing']['preview']['evidence_cards'] if card['metric_id'] == 'gsc.clicks')
        self.assertEqual(clicks['value'], 60)
        self.assertEqual(clicks['comparison']['previous_value'], 18)
        self.assertEqual(clicks['comparison']['lineage']['sync_run_ids'], [self.run['id']])
        result = self.approve(candidate)
        self.assertEqual(result.status_code, 201, result.json)
        row = self.store.one('SELECT * FROM marketing_release_approvals WHERE id=?', (result.json['approval_id'],))
        self.assertEqual(row['reviewer_id'], self.actor)
        self.assertEqual(row['candidate_sha256'], checks['candidate_sha256'])
        self.assertEqual(self.store.one('SELECT COUNT(*) AS n FROM report_bundles')['n'], 0)
        self.assertEqual(self.store.one('SELECT valid FROM datasets WHERE id=?', (candidate,))['valid'], 0)

    def test_succeeded_and_human_review_without_receipt_are_not_provider_confirmation(self):
        candidate = self.candidate()
        self.store.execute('DELETE FROM source_attestations WHERE sync_run_id=?', (self.run['id'],))
        checks = self.check(candidate)
        self.assertIn('provider_origin_unconfirmed', checks['issues'])
        self.assertTrue(all(item['status'] == 'lineage_consistent' for item in checks['checks']))
        self.assertEqual(self.approve(candidate).status_code, 409)
        blocked = self.approve(candidate, 'release_blocked')
        self.assertEqual(blocked.status_code, 201)

    def test_permission_failure_snapshot_missing_and_connection_missing_block(self):
        candidate = self.candidate()
        self.store.execute("UPDATE sync_runs SET status='failed',error_code='permission_denied' WHERE id=?", (self.run['id'],))
        self.assertIn('permission_denied', self.check(candidate)['issues'])
        self.store.execute("UPDATE sync_runs SET status='succeeded',error_code=NULL WHERE id=?", (self.run['id'],))
        self.store.execute("UPDATE connections SET status='disconnected' WHERE id=?", (self.run['connection_id'],))
        self.assertIn('not_configured', self.check(candidate)['issues'])
        self.store.execute('DELETE FROM source_snapshots WHERE sync_run_id=?', (self.run['id'],))
        self.assertIn('source_snapshot_missing', self.check(candidate)['issues'])

    def test_snapshot_tampering_partial_and_demo_are_blocked(self):
        candidate = self.candidate()
        row = self.store.one('SELECT * FROM source_snapshots WHERE sync_run_id=?', (self.run['id'],))
        original = json.loads(row['payload'])
        for change, expected in (({'demo': True}, 'demo_data'), ({'daily': original['daily'][:1]}, 'partial'),
                                 ({'totals': {**original['totals'], 'clicks': 900}}, 'metric_value_mismatch')):
            with self.subTest(expected=expected):
                self.store.execute('UPDATE source_snapshots SET payload=? WHERE id=?', (pack({**original, **change}), row['id']))
                checks = self.check(candidate)
                self.assertIn(expected, checks['issues'])
                self.assertIn('provider_origin_unconfirmed', checks['issues'])
                self.assertEqual(self.approve(candidate).status_code, 409)

    def test_origin_and_candidate_changed_after_internal_review_are_blocked(self):
        candidate = self.candidate()
        row = self.store.one('SELECT data FROM datasets WHERE id=?', (candidate,))
        data = json.loads(row['data'])
        data['marketing']['preview']['widgets'][0]['value'] = 999
        self.store.execute('UPDATE datasets SET data=? WHERE id=?', (pack(data), candidate))
        self.assertIn('candidate_changed', self.check(candidate)['issues'])
        self.store.execute('UPDATE datasets SET data=? WHERE id=?', (row['data'], candidate))
        origin = json.loads(self.store.one('SELECT data FROM datasets WHERE id=?', (self.origin_id,))['data'])
        origin['created_at'] = 'changed'
        self.store.execute('UPDATE datasets SET data=? WHERE id=?', (pack(origin), self.origin_id))
        self.assertIn('origin_dataset_changed', self.check(candidate)['issues'])

    def test_review_replacement_and_new_sync_block_old_candidate(self):
        candidate = self.candidate()
        self.sync()
        self.assertIn('stale', self.check(candidate)['issues'])
        review = self.client.get(f'/api/marketing/datasets/{self.origin_id}/review').json
        response = self.client.post(f'/api/marketing/datasets/{self.origin_id}/review', json={
            'decision': 'needs_changes', 'note': 'Request changes after independent review.',
            'expected_sha256': review['dataset_sha256']}, headers=self.headers)
        self.assertEqual(response.status_code, 201)
        self.assertIn('review_superseded', self.check(candidate)['issues'])

    def test_asset_scope_and_untrusted_flags_cannot_authorize_release(self):
        candidate = self.candidate()
        self.store.execute("UPDATE source_assets SET asset_type='ga4_property' WHERE id=?", (self.run['asset_id'],))
        self.assertIn('asset_scope_mismatch', self.check(candidate)['issues'])
        for field in ('provider_verified', 'valid', 'publishable'):
            response = self.approve(candidate, **{field: True})
            self.assertEqual(response.status_code, 400)

    def test_auth_csrf_and_reviewer_role(self):
        candidate = self.candidate()
        path = f'/api/marketing/release-candidates/{candidate}/approval'
        self.assertEqual(self.client.post(path, json={}).status_code, 403)
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get(path).status_code, 401)
        for role in ('operator', 'viewer'):
            self.store.execute('UPDATE users SET role=? WHERE id=?', (role, self.actor))
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.get(f'/api/datasets/{candidate}').status_code, 403)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PostgresVerificationTests(VerificationTests):
    def setUp(self):
        import test_postgres
        self.fixture = test_postgres.PostgresTest('test_integrity_error_returns_normal_user_validation')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app = self.fixture.apps[0]
        self.store = self.fixture.store
        self.client = self.fixture.clients[0]
        self.headers, self.actor = self.fixture.headers, self.fixture.actor
        self.prepare()


if __name__ == '__main__':
    unittest.main()
