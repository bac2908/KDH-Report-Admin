
"""Step 8.8.4B: safe internal Marketing release staging."""

import json
import unittest

import test_marketing_review as review_fixture

from kdh.core import pack
from kdh.report_bundles import _guard_marketing_snapshot
from kdh.core import Problem


class MarketingReleaseTests(unittest.TestCase):

    def setUp(self):
        self.fixture = review_fixture.MarketingReviewTests(
            "test_no_data_is_not_approvable"
        )

        self.fixture.setUp()

        self.app = self.fixture.app
        self.store = self.fixture.store
        self.client = self.fixture.client
        self.actor = self.fixture.actor
        self.headers = self.fixture.headers

    def tearDown(self):
        self.fixture.tearDown()

    def path(self, dataset_id):
        return (
            "/api/marketing/datasets/"
            + dataset_id
        )

    def readiness(self, dataset_id):
        return self.client.get(
            self.path(dataset_id) + "/release-readiness"
        )

    def stage(
        self,
        dataset_id,
        *,
        expected_hash=None,
        review_id=None,
    ):
        ready = self.readiness(
            dataset_id
        ).get_json()

        if expected_hash is None:
            expected_hash = ready["dataset_sha256"]

        if review_id is None:
            latest = ready.get("latest_review")
            review_id = (
                latest["id"]
                if latest else "0" * 32
            )

        return self.client.post(
            self.path(dataset_id) + "/release-candidates",
            json={
                "expected_sha256": expected_hash,
                "expected_review_id": review_id,
            },
            headers=self.headers,
        )

    def approve(self, dataset_id):
        result = self.fixture.submit(
            dataset_id,
            "approved_internal",
        )

        self.assertEqual(
            result.status_code,
            201,
            result.get_json(),
        )

    def test_without_approval_not_ready(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        result = self.readiness(
            dataset_id
        )

        self.assertEqual(result.status_code, 200)

        ready = result.get_json()

        self.assertFalse(ready["ready_to_stage"])
        self.assertFalse(ready["publishable"])
        self.assertIn("review_missing", ready["issues"])

        response = self.stage(dataset_id)

        self.assertEqual(response.status_code, 409)

    def test_approved_snapshot_creates_separate_candidate(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        original_before = self.store.one(
            "SELECT * FROM datasets WHERE id=?",
            (dataset_id,),
        )

        ready = self.readiness(
            dataset_id
        ).get_json()

        self.assertTrue(ready["ready_to_stage"])

        response = self.stage(dataset_id)

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        result = response.get_json()
        release_id = result["release_dataset_id"]

        self.assertNotEqual(release_id, dataset_id)
        self.assertFalse(result["valid"])
        self.assertFalse(result["publishable"])
        self.assertFalse(result["provider_verified"])

        row = self.store.one(
            "SELECT * FROM datasets WHERE id=?",
            (release_id,),
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["valid"], 0)

        candidate = json.loads(row["data"])

        self.assertEqual(
            candidate["dataset_kind"],
            "marketing_release_candidate_v1",
        )

        self.assertEqual(
            candidate["release_candidate"][
                "origin_dataset_id"
            ],
            dataset_id,
        )

        self.assertEqual(
            candidate["release_candidate"]["review_id"],
            ready["latest_review"]["id"],
        )

        self.assertEqual(
            candidate["marketing"]["review_status"],
            "approved_internal",
        )

        self.assertFalse(
            candidate["marketing"]["publishable"]
        )

        self.assertEqual(
            self.store.one(
                "SELECT * FROM datasets WHERE id=?",
                (dataset_id,),
            ),
            original_before,
        )

        # Even after staging, it must remain blocked.
        with self.assertRaises(Problem) as raised:
            _guard_marketing_snapshot({
                "sections": {
                    "gsc": {"data": candidate}
                }
            })

        self.assertEqual(
            raised.exception.code,
            "marketing_review_required",
        )

    def test_no_evidence_cannot_be_staged(self):
        dataset_id = self.fixture.add_dataset()

        ready = self.readiness(
            dataset_id
        ).get_json()

        self.assertFalse(ready["ready_to_stage"])
        self.assertIn(
            "internal_evidence_not_ready",
            ready["issues"],
        )

        self.assertEqual(
            self.stage(dataset_id).status_code,
            409,
        )

    def test_latest_needs_changes_blocks_staging(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        revised = self.fixture.submit(
            dataset_id,
            "needs_changes",
        )

        self.assertEqual(revised.status_code, 201)

        ready = self.readiness(
            dataset_id
        ).get_json()

        self.assertFalse(ready["ready_to_stage"])
        self.assertIn(
            "review_not_approved",
            ready["issues"],
        )

        self.assertEqual(
            self.stage(dataset_id).status_code,
            409,
        )

    def test_changed_dataset_invalidates_approval(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        row = self.store.one(
            "SELECT data FROM datasets WHERE id=?",
            (dataset_id,),
        )

        modified = json.loads(row["data"])
        modified["internal_revision_note"] = "changed"

        self.store.execute(
            "UPDATE datasets SET data=? WHERE id=?",
            (pack(modified), dataset_id),
        )

        ready = self.readiness(
            dataset_id
        ).get_json()

        self.assertFalse(ready["ready_to_stage"])

        self.assertIn(
            "review_snapshot_mismatch",
            ready["issues"],
        )

        self.assertEqual(
            self.stage(dataset_id).status_code,
            409,
        )

    def test_wrong_review_id_rejected(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        response = self.stage(
            dataset_id,
            review_id="0" * 32,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["code"],
            "stale_release_review",
        )

    def test_csrf_and_anonymous_are_rejected(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        ready = self.readiness(
            dataset_id
        ).get_json()

        payload = {
            "expected_sha256": ready["dataset_sha256"],
            "expected_review_id": (
                ready["latest_review"]["id"]
            ),
        }

        path = (
            self.path(dataset_id)
            + "/release-candidates"
        )

        no_csrf = self.client.post(
            path,
            json=payload,
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(no_csrf.status_code, 403)

        anonymous = self.app.test_client()

        response = anonymous.post(
            path,
            json=payload,
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(response.status_code, 401)

    def test_draft_can_be_created_but_not_published(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        staged = self.stage(dataset_id)

        self.assertEqual(staged.status_code, 201)

        release_id = staged.get_json()[
            "release_dataset_id"
        ]

        draft = self.client.post(
            "/api/report-bundles",
            json={
                "client_id": "client_kinderhealth",
                "name": "Internal Release Candidate Test",
                "start_date": "2026-09-10",
                "end_date": "2026-09-12",
                "compare_start_date": "2026-09-07",
                "compare_end_date": "2026-09-09",
                "default_section": "gsc",
                "sections": [{
                    "key": "gsc",
                    "dataset_id": release_id,
                }],
            },
            headers=self.headers,
        )

        self.assertEqual(
            draft.status_code,
            201,
            draft.get_json(),
        )

        report_id = draft.get_json()["report_id"]

        for status in ("provisional", "final"):
            with self.subTest(status=status):
                response = self.client.post(
                    (
                        "/api/report-bundles/"
                        + report_id
                        + "/revisions/1/publish"
                    ),
                    json={"status": status},
                    headers=self.headers,
                )

                self.assertEqual(
                    response.status_code,
                    409,
                    response.get_json(),
                )

                self.assertEqual(
                    response.get_json()["code"],
                    "marketing_review_required",
                )

        saved = self.client.get(
            "/api/report-bundles/" + report_id
        )

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            saved.get_json()["report"]["status"],
            "draft",
        )

    def test_viewer_cannot_read_candidate_by_legacy_api(self):
        dataset_id = self.fixture.add_dataset(
            with_evidence=True
        )

        self.approve(dataset_id)

        staged = self.stage(dataset_id)

        self.assertEqual(staged.status_code, 201)

        release_id = staged.get_json()[
            "release_dataset_id"
        ]

        self.store.execute(
            "UPDATE users SET role='viewer' WHERE id=?",
            (self.actor,),
        )

        response = self.client.get(
            "/api/datasets/" + release_id
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
