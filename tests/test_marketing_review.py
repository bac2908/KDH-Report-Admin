
"""Step 8.8.4: internal review tests using temporary SQLite."""

import hashlib
import json
import tempfile
import unittest

from kdh.app import create_app
from kdh.core import Problem, now, pack, uid
from kdh.report_bundles import _guard_marketing_snapshot


class MarketingReviewTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        self.app = create_app({
            "TESTING": True,
            "DATA_DIR": self.tmp.name,
            "DATABASE_URL": "",
            "JOB_MODE": "request",
            "ENCRYPTION_KEY": "",
            "COOKIE_SECURE": False,
            "APP_URL": "http://localhost",
            "INITIAL_ADMIN_EMAIL": "review-admin@example.test",
            "INITIAL_ADMIN_PASSWORD": "Review-Password-12345",
        })

        self.store = self.app.extensions["store"]
        self.client = self.app.test_client()

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "review-admin@example.test",
                "password": "Review-Password-12345",
            },
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            login.status_code,
            200,
            login.get_json(),
        )

        self.actor = login.get_json()["user"]["id"]

        self.headers = {
            "X-KDH-Request": "1",
            "X-CSRF-Token": login.get_json()["csrf"],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def add_dataset(self, *, with_evidence=False, demo=False):
        dataset_id = uid()

        preview = {
            "preview_schema_version": "0.1",
            "kind": "marketing_internal_preview",
            "client_id": "client_kinderhealth",
            "source_filter": "gsc",
            "sources": ["gsc"],
            "period": {
                "start": "2026-09-10",
                "end": "2026-09-12",
            },
            "comparison": {
                "start": "2026-09-07",
                "end": "2026-09-09",
            },
            "publishable": False,
            "not_a_report_bundle": True,
            "quality": {
                "independently_verified": False,
                "ready_for_customer_claims": False,
                "status": (
                    "unverified_with_data"
                    if with_evidence
                    else "no_eligible_data"
                ),
            },
            "widgets": [{
                "type": "kpi",
                "metric_id": "gsc.clicks",
                "source": "gsc",
                "value": 40 if with_evidence else None,
                "verified": False,
                "publishable": False,
            }],
            "evidence_cards": (
                [{
                    "evidence_id": "test-evidence-1",
                    "metric_id": "gsc.clicks",
                    "source": "gsc",
                    "status": "recorded_unverified",
                    "verified": False,
                    "publishable": False,
                    "lineage": {
                        "sync_run_ids": ["test-run-1"],
                        "sync_run_count": 1,
                    },
                }]
                if with_evidence else []
            ),
            "opportunity_candidates": [],
            "summary": {
                "widget_count": 1,
                "widgets_with_values": (
                    1 if with_evidence else 0
                ),
                "evidence_count": (
                    1 if with_evidence else 0
                ),
                "opportunity_count": 0,
            },
        }

        dataset = {
            "id": dataset_id,
            "client_id": "client_kinderhealth",
            "created_at": now(),
            "dataset_kind": "marketing_internal_preview_v1",
            "data_origin": "persisted_unverified",
            "params": {
                "report_type": "gsc",
                "source": "gsc",
                "start": "2026-09-10",
                "end": "2026-09-12",
                "compare": True,
                "previous_start": "2026-09-07",
                "previous_end": "2026-09-09",
                **({"demo": True} if demo else {}),
            },
            "sources": {
                "gsc": {
                    "source": "gsc",
                    "status": "incomplete",
                    "requested_start": "2026-09-10",
                    "requested_end": "2026-09-12",
                },
            },
            "marketing": {
                "kind": "internal_review_snapshot",
                "review_status": "pending",
                "verified": False,
                "publishable": False,
                "preview_sha256": hashlib.sha256(
                    pack(preview).encode("utf-8")
                ).hexdigest(),
                "preview": preview,
            },
        }

        self.store.execute(
            """
            INSERT INTO datasets (
                id, user_id, report_type,
                created_at, valid, data
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                dataset_id,
                self.actor,
                "gsc",
                now(),
                0,
                pack(dataset),
            ),
        )

        return dataset_id

    def path(self, dataset_id):
        return (
            "/api/marketing/datasets/"
            + dataset_id
            + "/review"
        )

    def submit(self, dataset_id, decision, *, expected_hash=None):
        if expected_hash is None:
            expected_hash = self.client.get(
                self.path(dataset_id)
            ).get_json()["dataset_sha256"]

        return self.client.post(
            self.path(dataset_id),
            json={
                "decision": decision,
                "expected_sha256": expected_hash,
                "note": (
                    "Internal review note, "
                    "no client publication."
                ),
            },
            headers=self.headers,
        )

    def test_no_data_is_not_approvable(self):
        dataset_id = self.add_dataset()

        response = self.client.get(
            self.path(dataset_id)
        )

        self.assertEqual(response.status_code, 200)

        result = response.get_json()

        self.assertEqual(
            result["review_status"],
            "needs_data",
        )

        self.assertFalse(
            result["checks"]["can_approve_internal"]
        )

        self.assertFalse(
            result["checks"]["can_publish_provisional"]
        )

        blocked = self.submit(
            dataset_id,
            "approved_internal",
        )

        self.assertEqual(
            blocked.status_code,
            409,
            blocked.get_json(),
        )

        self.assertEqual(
            blocked.get_json()["code"],
            "insufficient_evidence",
        )

    def test_needs_changes_records_audit(self):
        dataset_id = self.add_dataset()

        before = self.store.one(
            "SELECT * FROM datasets WHERE id=?",
            (dataset_id,),
        )

        response = self.submit(
            dataset_id,
            "needs_changes",
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        self.assertFalse(
            response.get_json()["publishable"]
        )

        self.assertEqual(
            self.store.one(
                "SELECT * FROM datasets WHERE id=?",
                (dataset_id,),
            ),
            before,
        )

        latest = self.client.get(
            self.path(dataset_id)
        ).get_json()["latest_review"]

        self.assertEqual(
            latest["decision"],
            "needs_changes",
        )

        self.assertTrue(
            latest["matches_current_snapshot"]
        )

        audit = self.store.one(
            """
            SELECT COUNT(*) AS n
            FROM events
            WHERE action='review_marketing_dataset'
            """
        )

        self.assertEqual(audit["n"], 1)

    def test_approval_stays_internal(self):
        dataset_id = self.add_dataset(
            with_evidence=True
        )

        review = self.client.get(
            self.path(dataset_id)
        ).get_json()

        self.assertTrue(
            review["checks"]["can_approve_internal"]
        )

        response = self.submit(
            dataset_id,
            "approved_internal",
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        self.assertFalse(
            response.get_json()["provider_verified"]
        )

        self.assertFalse(
            response.get_json()["publishable"]
        )

        dataset = json.loads(
            self.store.one(
                "SELECT data FROM datasets WHERE id=?",
                (dataset_id,),
            )["data"]
        )

        # The publishing guard introduced in 8.8.3
        # must remain in force.
        with self.assertRaises(Problem) as raised:
            _guard_marketing_snapshot({
                "sections": {
                    "gsc": {"data": dataset}
                }
            })

        self.assertEqual(
            raised.exception.status,
            409,
        )

    def test_changed_snapshot_invalidates_review(self):
        dataset_id = self.add_dataset(
            with_evidence=True
        )

        approved = self.submit(
            dataset_id,
            "approved_internal",
        )

        self.assertEqual(
            approved.status_code, 201
        )

        row = self.store.one(
            "SELECT data FROM datasets WHERE id=?",
            (dataset_id,),
        )

        modified = json.loads(row["data"])

        modified["marketing"]["preview"]["widgets"][0][
            "value"
        ] = 50

        self.store.execute(
            "UPDATE datasets SET data=? WHERE id=?",
            (pack(modified), dataset_id),
        )

        result = self.client.get(
            self.path(dataset_id)
        ).get_json()

        self.assertIn(
            "preview_hash_mismatch",
            result["issues"],
        )

        self.assertFalse(
            result["latest_review"][
                "matches_current_snapshot"
            ]
        )

    def test_demo_cannot_be_approved(self):
        dataset_id = self.add_dataset(
            with_evidence=True,
            demo=True,
        )

        response = self.client.get(
            self.path(dataset_id)
        )

        self.assertIn(
            "demo_data",
            response.get_json()["issues"],
        )

        self.assertEqual(
            self.submit(
                dataset_id,
                "approved_internal",
            ).status_code,
            409,
        )

    def test_stale_hash_is_rejected(self):
        dataset_id = self.add_dataset(
            with_evidence=True
        )

        response = self.submit(
            dataset_id,
            "approved_internal",
            expected_hash="0" * 64,
        )

        self.assertEqual(
            response.status_code,
            409,
        )

        self.assertEqual(
            response.get_json()["code"],
            "stale_review",
        )

    def test_authentication_and_csrf(self):
        dataset_id = self.add_dataset()

        anonymous = self.app.test_client()

        self.assertEqual(
            anonymous.get(
                self.path(dataset_id)
            ).status_code,
            401,
        )

        response = self.client.post(
            self.path(dataset_id),
            json={
                "decision": "needs_changes",
                "expected_sha256": "0" * 64,
                "note": "Please check this dataset.",
            },
            headers={
                "X-KDH-Request": "1"
            },
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    def test_viewer_cannot_review(self):
        dataset_id = self.add_dataset()

        self.store.execute(
            "UPDATE users SET role='viewer' WHERE id=?",
            (self.actor,),
        )

        response = self.client.get(
            self.path(dataset_id)
        )

        self.assertEqual(
            response.status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
