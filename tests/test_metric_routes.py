
"""Step 8.4: authenticated Metric API tests.

Uses temporary SQLite, never production PostgreSQL.
"""

import tempfile
import unittest

from werkzeug.security import generate_password_hash

from kdh.app import create_app
from kdh.core import now, pack


class MetricRoutesTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

        self.app = create_app({
            "DATA_DIR": self.tmp.name,
            "DATABASE_URL": "",
            "ENCRYPTION_KEY": "",
            "JOB_MODE": "request",
            "COOKIE_SECURE": False,
            "INITIAL_ADMIN_EMAIL": "metric-admin@example.test",
            "INITIAL_ADMIN_PASSWORD": "Metric-test-password-123",
        })

        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, email, password):
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": password,
            },
            headers={"X-KDH-Request": "1"},
        )
        self.assertEqual(
            response.status_code,
            200,
            response.get_json(),
        )

    def login_admin(self):
        self.login(
            "metric-admin@example.test",
            "Metric-test-password-123",
        )

    def test_anonymous_cannot_access_metrics(self):
        self.assertEqual(
            self.client.get(
                "/api/metrics/catalog"
            ).status_code,
            401,
        )

        self.assertEqual(
            self.client.get(
                "/api/metrics/series"
                "?metric_id=ga4.sessions"
                "&start=2026-09-01"
                "&end=2026-09-03"
            ).status_code,
            401,
        )

    def test_admin_sees_catalog_and_can_filter(self):
        self.login_admin()

        response = self.client.get(
            "/api/metrics/catalog"
        )

        self.assertEqual(response.status_code, 200)

        payload = response.get_json()

        self.assertEqual(payload["version"], "1.0")
        self.assertGreaterEqual(payload["count"], 150)

        self.assertIn(
            "facebook_ads",
            payload["sources"],
        )

        single = self.client.get(
            "/api/metrics/catalog?source=ga4"
        ).get_json()

        self.assertEqual(
            set(single["sources"]),
            {"ga4"},
        )

        self.assertTrue(
            all(
                metric["source"] == "ga4"
                for metric in single["metrics"]
            )
        )

    def test_empty_database_never_fabricates_metrics(self):
        self.login_admin()

        response = self.client.get(
            "/api/metrics/series"
            "?metric_id=ga4.sessions"
            "&start=2026-09-01"
            "&end=2026-09-03"
        )

        self.assertEqual(response.status_code, 200)

        payload = response.get_json()

        self.assertEqual(
            payload["status"],
            "not_configured",
        )
        self.assertEqual(payload["series"], [])
        self.assertIsNone(payload["summary"]["value"])

        self.assertEqual(
            payload["data_origin"],
            "persisted_unverified",
        )

    def test_invalid_parameters_rejected(self):
        self.login_admin()

        url = (
            "/api/metrics/series"
            "?metric_id=ga4.sessions"
            "&start=2026-09-01"
            "&end=2026-09-03"
        )

        self.assertEqual(
            self.client.get(
                url + "&client_id=another-client"
            ).status_code,
            400,
        )

        self.assertEqual(
            self.client.get(
                url + "&demo=1"
            ).status_code,
            400,
        )

        self.assertEqual(
            self.client.get(
                url + "&start=2026-09-01"
            ).status_code,
            400,
        )

        self.assertEqual(
            self.client.get(
                url.replace("2026-09-01", "wrong")
            ).status_code,
            400,
        )

        self.assertEqual(
            self.client.get(
                url.replace(
                    "ga4.sessions",
                    "ga4.missing",
                )
            ).status_code,
            404,
        )

    def test_viewer_cannot_read_other_sources(self):
        store = self.app.extensions["store"]

        store.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?,?,?)",
            (
                "metric-viewer-test",
                "metric-viewer@example.test",
                "Viewer",
                generate_password_hash(
                    "Viewer-test-password-123"
                ),
                "viewer",
                pack(["seo"]),
                1,
                now(),
            ),
        )

        self.login(
            "metric-viewer@example.test",
            "Viewer-test-password-123",
        )

        catalog = self.client.get(
            "/api/metrics/catalog"
        ).get_json()

        self.assertEqual(
            set(catalog["sources"]),
            {"ga4", "gsc", "keywords"},
        )

        self.assertEqual(
            self.client.get(
                "/api/metrics/series"
                "?metric_id=facebook_ads.spend"
                "&start=2026-09-01"
                "&end=2026-09-03"
            ).status_code,
            403,
        )

        self.assertEqual(
            self.client.get(
                "/api/metrics/catalog?source=youtube"
            ).status_code,
            403,
        )

        self.assertEqual(
            self.client.get(
                "/api/metrics/series"
                "?metric_id=ga4.sessions"
                "&start=2026-09-01"
                "&end=2026-09-03"
            ).status_code,
            200,
        )


if __name__ == "__main__":
    unittest.main()
