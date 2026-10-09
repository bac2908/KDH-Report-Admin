
"""Step 8.8.2: internal Marketing Dataset tests."""

import tempfile
import unittest

from kdh.app import create_app
from kdh.core import pack


class MarketingDatasetTests(unittest.TestCase):

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
            "INITIAL_ADMIN_EMAIL": (
                "dataset-admin@example.test"
            ),
            "INITIAL_ADMIN_PASSWORD": (
                "Dataset-test-password-123"
            ),
        })

        self.store = self.app.extensions["store"]
        self.client = self.app.test_client()

        response = self.client.post(
            "/api/auth/login",
            json={
                "email": "dataset-admin@example.test",
                "password": "Dataset-test-password-123",
            },
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            response.status_code,
            200,
            response.get_json(),
        )

        self.headers = {
            "X-KDH-Request": "1",
            "X-CSRF-Token": response.get_json()["csrf"],
        }

        self.payload = {
            "source": "gsc",
            "start": "2026-09-10",
            "end": "2026-09-12",
        }

    def tearDown(self):
        self.temp.cleanup()

    def create(self, payload=None):
        return self.client.post(
            "/api/marketing/datasets",
            json=(
                self.payload
                if payload is None
                else payload
            ),
            headers=self.headers,
        )

    def count_datasets(self):
        return self.store.one(
            "SELECT COUNT(*) AS n FROM datasets"
        )["n"]

    def test_create_internal_only_dataset(self):
        response = self.create()

        self.assertEqual(
            response.status_code,
            201,
            response.get_json(),
        )

        result = response.get_json()

        self.assertFalse(result["valid"])
        self.assertFalse(result["publishable"])
        self.assertFalse(result["exportable"])

        dataset_id = result["dataset_id"]

        stored = self.store.one(
            """
            SELECT report_type, valid, data
            FROM datasets
            WHERE id=?
            """,
            (dataset_id,),
        )

        self.assertEqual(
            stored["report_type"], "gsc"
        )
        self.assertEqual(stored["valid"], 0)

        import json
        data = json.loads(stored["data"])

        self.assertEqual(
            data["dataset_kind"],
            "marketing_internal_preview_v1",
        )

        self.assertEqual(
            data["sources"]["gsc"]["status"],
            "incomplete",
        )

        self.assertFalse(
            data["marketing"]["publishable"]
        )

        self.assertFalse(
            data["marketing"]["verified"]
        )

        self.assertEqual(
            data["params"]["report_type"], "gsc"
        )

        self.assertEqual(
            data["params"]["start"],
            "2026-09-10",
        )

        self.assertEqual(
            data["marketing"]["preview"]["kind"],
            "marketing_internal_preview",
        )

        audit = self.store.one(
            """
            SELECT id FROM events
            WHERE action='create_marketing_dataset'
            """
        )
        self.assertIsNotNone(audit)

    def test_new_datasets_never_overwrite_old_ones(self):
        first = self.create()
        second = self.create()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)

        self.assertNotEqual(
            first.get_json()["dataset_id"],
            second.get_json()["dataset_id"],
        )

        self.assertEqual(
            self.count_datasets(), 2
        )

    def test_unknown_fields_are_rejected(self):
        before = self.count_datasets()

        response = self.create({
            **self.payload,
            "client_id": "another-client",
            "valid": True,
            "data": {"fake": True},
        })

        self.assertEqual(
            response.status_code, 400
        )

        self.assertEqual(
            self.count_datasets(), before
        )

    def test_unsupported_report_type_rejected(self):
        response = self.create({
            **self.payload,
            "source": "youtube",
        })

        self.assertEqual(
            response.status_code, 409
        )

        self.assertEqual(
            self.count_datasets(), 0
        )

    def test_missing_csrf_rejected(self):
        response = self.client.post(
            "/api/marketing/datasets",
            json=self.payload,
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            response.status_code, 403
        )

        self.assertEqual(
            self.count_datasets(), 0
        )

    def test_anonymous_client_rejected(self):
        anonymous = self.app.test_client()

        response = anonymous.post(
            "/api/marketing/datasets",
            json=self.payload,
            headers={"X-KDH-Request": "1"},
        )

        self.assertEqual(
            response.status_code, 401
        )

        self.assertEqual(
            self.count_datasets(), 0
        )

    def test_dataset_cannot_be_final_report(self):
        created = self.create()

        self.assertEqual(
            created.status_code, 201
        )

        dataset_id = created.get_json()["dataset_id"]

        draft = self.client.post(
            "/api/report-bundles",
            json={
                "client_id": "client_kinderhealth",
                "name": "Internal Marketing Test",
                "start_date": "2026-09-10",
                "end_date": "2026-09-12",
                "compare_start_date": "2026-09-07",
                "compare_end_date": "2026-09-09",
                "default_section": "gsc",
                "sections": [
                    {
                        "key": "gsc",
                        "dataset_id": dataset_id,
                    }
                ],
            },
            headers=self.headers,
        )

        self.assertEqual(
            draft.status_code,
            201,
            draft.get_json(),
        )

        report_id = draft.get_json()["report_id"]

        final = self.client.post(
            (
                "/api/report-bundles/"
                + report_id
                + "/revisions/1/publish"
            ),
            json={"status": "final"},
            headers=self.headers,
        )

        self.assertEqual(
            final.status_code, 409
        )


if __name__ == "__main__":
    unittest.main()
