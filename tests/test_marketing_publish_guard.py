
"""Step 8.8.3: Marketing Report Bundle publication guard."""

import json
import tempfile
import unittest

from kdh.app import create_app
from kdh.core import now, pack, uid


class MarketingPublishGuardTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

        self.app = create_app({
            "TESTING": True,
            "DATA_DIR": self.temp.name,
            "DATABASE_URL": "",
            "JOB_MODE": "request",
            "ENCRYPTION_KEY": "",
            "COOKIE_SECURE": False,
            "APP_URL": "http://localhost",
            "INITIAL_ADMIN_EMAIL": "",
            "INITIAL_ADMIN_PASSWORD": "",
        })

        self.store = self.app.extensions["store"]
        self.client = self.app.test_client()

        setup = self.client.post(
            "/api/auth/setup",
            json={
                "name": "Guard Test Admin",
                "email": "guard@example.test",
                "password": "Guard-test-password-123",
            },
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            setup.status_code, 201, setup.get_json()
        )

        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "guard@example.test",
                "password": "Guard-test-password-123",
            },
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            login.status_code, 200, login.get_json()
        )

        self.actor = login.get_json()["user"]["id"]

        self.headers = {
            "X-KDH-Request": "1",
            "X-CSRF-Token": login.get_json()["csrf"],
        }

    def tearDown(self):
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post(
            path,
            json=data,
            headers=self.headers,
        )

    def add_dataset(
        self,
        *,
        marketing=True,
        valid=False,
        marker_only=False,
    ):
        dataset_id = uid()

        source_status = (
            "ready" if valid else "incomplete"
        )

        data = {
            "id": dataset_id,
            "client_id": "client_kinderhealth",
            "created_at": now(),
            "params": {
                "report_type": "gsc",
                "start": "2026-09-10",
                "end": "2026-09-12",
                "compare": False,
            },
            "sources": {
                "gsc": {
                    "source": "gsc",
                    "status": source_status,
                    "requested_start": "2026-09-10",
                    "requested_end": "2026-09-12",
                    "latest_available_date": (
                        "2026-09-12" if valid else None
                    ),
                    "totals": {},
                    "daily": [],
                    "warnings": [],
                }
            },
        }

        if marketing:
            if not marker_only:
                data["dataset_kind"] = (
                    "marketing_internal_preview_v1"
                )

            data["marketing"] = {
                "kind": "internal_review_snapshot",
                "review_status": "pending",
                "verified": False,
                "publishable": False,
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
                int(valid),
                pack(data),
            ),
        )

        return dataset_id

    def create_bundle(self, dataset_ids):
        sections = [
            {
                "key": (
                    "gsc" if index == 0
                    else "extra" + str(index)
                ),
                "dataset_id": dataset_id,
            }
            for index, dataset_id
            in enumerate(dataset_ids)
        ]

        response = self.post(
            "/api/report-bundles",
            {
                "client_id": "client_kinderhealth",
                "name": "Marketing Guard Test",
                "start_date": "2026-09-10",
                "end_date": "2026-09-12",
                "default_section": "gsc",
                "sections": sections,
            },
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        return response.get_json()["report_id"]

    def publish(self, report_id, status, revision=1):
        return self.post(
            (
                "/api/report-bundles/"
                + report_id
                + "/revisions/"
                + str(revision)
                + "/publish"
            ),
            {"status": status},
        )

    def assert_blocked(self, response):
        self.assertEqual(
            response.status_code,
            409,
            response.get_json(),
        )
        self.assertEqual(
            response.get_json()["code"],
            "marketing_review_required",
        )

    def test_internal_marketing_draft_can_be_previewed(self):
        dataset_id = self.add_dataset()
        report_id = self.create_bundle([dataset_id])

        response = self.client.get(
            "/api/report-bundles/" + report_id
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["report"]["status"],
            "draft",
        )

    def test_both_publication_states_are_blocked(self):
        dataset_id = self.add_dataset()
        report_id = self.create_bundle([dataset_id])

        for status in ("provisional", "final"):
            with self.subTest(status=status):
                self.assert_blocked(
                    self.publish(report_id, status)
                )

        row = self.store.one(
            """
            SELECT status, published_at
            FROM report_bundles
            WHERE bundle_key=?
            """,
            (report_id,),
        )

        self.assertEqual(row["status"], "draft")
        self.assertIsNone(row["published_at"])

    def test_marketing_marker_cannot_be_bypassed(self):
        dataset_id = self.add_dataset(
            marketing=True,
            valid=True,
            marker_only=True,
        )

        report_id = self.create_bundle([dataset_id])

        self.assert_blocked(
            self.publish(report_id, "provisional")
        )

        self.assert_blocked(
            self.publish(report_id, "final")
        )

    def test_mixed_report_is_blocked(self):
        legacy = self.add_dataset(
            marketing=False,
            valid=True,
        )

        internal = self.add_dataset(
            marketing=True,
            valid=False,
        )

        report_id = self.create_bundle(
            [legacy, internal]
        )

        self.assert_blocked(
            self.publish(report_id, "provisional")
        )

    def test_inherited_revision_is_also_blocked(self):
        dataset_id = self.add_dataset()
        report_id = self.create_bundle([dataset_id])

        response = self.post(
            (
                "/api/report-bundles/"
                + report_id
                + "/revisions"
            ),
            {},
        )

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        self.assert_blocked(
            self.publish(report_id, "provisional", 2)
        )

    def test_previously_published_unsafe_bundle_not_served(self):
        dataset_id = self.add_dataset()
        report_id = self.create_bundle([dataset_id])

        # Simulate a historical unsafe publication,
        # only inside this temporary test database.
        row = self.store.one(
            """
            SELECT id, snapshot_payload
            FROM report_bundles
            WHERE bundle_key=?
            """,
            (report_id,),
        )

        payload = json.loads(
            row["snapshot_payload"]
        )

        payload["report"]["status"] = "provisional"
        payload["freshness"]["published_at"] = now()

        self.store.execute(
            """
            UPDATE report_bundles
            SET status=?, published_at=?,
                snapshot_payload=?
            WHERE id=?
            """,
            (
                "provisional",
                now(),
                pack(payload),
                row["id"],
            ),
        )

        self.app.config["REPORT_SERVICE_TOKEN"] = (
            "guard-test-service-token"
        )

        response = self.app.test_client().get(
            (
                "/api/internal/v1/report-bundles/"
                + report_id
            ),
            headers={
                "Authorization":
                    "Bearer guard-test-service-token"
            },
        )

        self.assert_blocked(response)

    def test_existing_legacy_publication_still_works(self):
        dataset_id = self.add_dataset(
            marketing=False,
            valid=True,
        )

        report_id = self.create_bundle([dataset_id])

        provisional = self.publish(
            report_id, "provisional"
        )

        self.assertEqual(
            provisional.status_code,
            200,
            provisional.get_json(),
        )

        final = self.publish(
            report_id, "final"
        )

        self.assertEqual(
            final.status_code,
            200,
            final.get_json(),
        )

        self.assertEqual(
            final.get_json()["status"],
            "final",
        )


if __name__ == "__main__":
    unittest.main()
