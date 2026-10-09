"""Publishing policy on independently constructed fixture provenance only."""
import json
import os
import unittest

import test_marketing_verification as fixtures
from kdh.core import pack


class PublicationCases:
    def release(self):
        candidate = self.fixture.candidate()
        approved = self.fixture.approve(candidate)
        self.assertEqual(approved.status_code, 201, approved.json)
        checks = self.fixture.check(candidate)
        result = self.fixture.client.post(f'/api/marketing/release-candidates/{candidate}/release-snapshots',
            json={'expected_approval_id': approved.json['approval_id'],
                  'expected_candidate_sha256': checks['candidate_sha256']}, headers=self.fixture.headers)
        self.assertEqual(result.status_code, 201, result.json)
        self.candidate_id = candidate
        self.release_id = result.json['dataset_id']
        return result.json

    def bundle(self, dataset_id=None):
        p = self.fixture.params
        result = self.fixture.client.post('/api/report-bundles', json={
            'client_id': 'client_kinderhealth', 'name': 'Isolated fixture report',
            'start_date': p['start'], 'end_date': p['end'], 'compare_start_date': p['previous_start'],
            'compare_end_date': p['previous_end'], 'default_section': 'seo',
            'sections': [{'key': 'seo', 'dataset_id': dataset_id or self.release_id}]}, headers=self.fixture.headers)
        self.assertEqual(result.status_code, 201, result.json)
        return result.json['report_id']

    def publish(self, report_id, status='provisional'):
        return self.fixture.client.post(f'/api/report-bundles/{report_id}/revisions/1/publish',
                                       json={'status': status}, headers=self.fixture.headers)

    def test_separate_release_and_final_publication_keep_original_immutable(self):
        result = self.release()
        original = self.store.one('SELECT * FROM datasets WHERE id=?', (self.fixture.origin_id,))
        candidate = self.store.one('SELECT * FROM datasets WHERE id=?', (self.candidate_id,))
        report_id = self.bundle()
        self.assertEqual(self.publish(report_id, 'final').status_code, 200)
        self.fixture.app.config['REPORT_SERVICE_TOKEN'] = 'fixture-backend-only'
        response = self.fixture.client.get('/api/internal/v1/report-bundles/' + report_id,
            headers={'Authorization': 'Bearer fixture-backend-only'})
        self.assertEqual(response.status_code, 200, response.json)
        data = response.json['sections']['seo']['data']
        self.assertEqual(data['sources']['gsc']['totals']['clicks'], 60)
        self.assertEqual(data['evidence'][0]['verification'], 'provider_origin_confirmed')
        self.assertEqual(data['opportunities'], [])
        self.assertNotIn('test-only-access', response.get_data(as_text=True))
        self.assertEqual(original, self.store.one('SELECT * FROM datasets WHERE id=?', (self.fixture.origin_id,)))
        self.assertEqual(candidate, self.store.one('SELECT * FROM datasets WHERE id=?', (self.candidate_id,)))
        self.assertEqual(result['version'], 1)
        before = response.json
        self.fixture.sync()  # New live data must not rewrite a published revision.
        after = self.fixture.client.get('/api/internal/v1/report-bundles/' + report_id,
            headers={'Authorization': 'Bearer fixture-backend-only'}).json
        self.assertEqual(before, after)

    def test_internal_candidate_stays_blocked_for_both_publication_modes(self):
        candidate = self.fixture.candidate()
        report_id = self.bundle(candidate)
        for mode in ('provisional', 'final'):
            with self.subTest(mode=mode):
                self.assertEqual(self.publish(report_id, mode).status_code, 409)
        self.assertEqual(self.store.one('SELECT status FROM report_bundles WHERE bundle_key=?', (report_id,))['status'], 'draft')

    def test_release_tampering_and_fake_verified_flags_do_not_bypass_guard(self):
        self.release()
        row = self.store.one('SELECT * FROM datasets WHERE id=?', (self.release_id,))
        data = json.loads(row['data'])
        data['sources']['gsc']['totals']['clicks'] = 9999
        data['release']['provider_origin_confirmed'] = True
        self.store.execute('UPDATE datasets SET data=? WHERE id=?', (pack(data), self.release_id))
        report_id = self.bundle()
        self.assertEqual(self.publish(report_id).status_code, 409)

    def test_superseded_approval_blocks_existing_release_before_publication(self):
        self.release()
        report_id = self.bundle()
        blocked = self.fixture.approve(self.candidate_id, 'release_blocked')
        self.assertEqual(blocked.status_code, 201)
        self.assertEqual(self.publish(report_id).status_code, 409)

    def test_revoked_reviewer_and_stale_provider_block_publication(self):
        self.release()
        report_id = self.bundle()
        self.fixture.sync()
        self.assertEqual(self.publish(report_id).status_code, 409)

    def test_draft_not_readable_with_service_or_viewer(self):
        self.release()
        report_id = self.bundle()
        self.fixture.app.config['REPORT_SERVICE_TOKEN'] = 'fixture-backend-only'
        endpoint = '/api/internal/v1/report-bundles/' + report_id
        self.assertEqual(self.fixture.client.get(endpoint).status_code, 401)
        self.assertEqual(self.fixture.client.get(endpoint, headers={'Authorization': 'Bearer fixture-backend-only'}).status_code, 404)
        self.store.execute("UPDATE users SET role='viewer' WHERE id=?", (self.fixture.actor,))
        self.assertEqual(self.fixture.client.get('/api/report-bundles/' + report_id).status_code, 403)


class SQLitePublicationTests(PublicationCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.VerificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires disposable PostgreSQL')
class PostgresPublicationTests(PublicationCases, unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PostgresVerificationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
