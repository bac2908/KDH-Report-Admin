"""HTTP integration tests for Meta Reporting; no actual Meta or production DB.

Run:
    python -m unittest discover -s tests -p test_meta_reporting_routes.py -v

Creates a temporary SQLite DB and replaces Meta with a deterministic fake
when Flask is constructed. No external requests or production database writes.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from kdh.core import digest, now, pack, uid
from kdh.platform_data import PlatformData


class FakeMeta:
    """Return deterministic provider responses; never contact Meta's servers."""

    client_id = "client_meta_sandbox"

    def __init__(self, store, config, cipher):
        self.store = store
        self.config = config
        self.cipher = cipher
        self.empty_ads = False
        self.calls = []

    def info(self):
        return {"connected": True, "configured": True, "client_id": self.client_id}

    def read(self):
        return {"account_id": "999123", "access_token": "FAKE_USER_TOKEN"}

    def call(self, method, path, *, token=None, params=None):
        if method != "GET":
            raise AssertionError("Only read requests are allowed in this fake")
        if "access_token" in (params or {}):
            raise AssertionError("Token must not be included in URL params")
        self.calls.append((path, (params or {}).get("level")))

        if path == "me/adaccounts":
            return {"data": [{
                "id": "act_123", "name": "Sandbox Ads", "currency": "VND",
                "account_status": 1, "timezone_name": "Asia/Ho_Chi_Minh"
            }]}
        if path == "me/accounts":
            return {"data": [{
                "id": "1234", "name": "Sandbox Page", "tasks": ["ANALYZE"],
                "access_token": "FAKE_PAGE_TOKEN"
            }]}
        if path == "act_123/insights":
            if self.empty_ads:
                return {"data": []}
            if (params or {}).get("level") == "account":
                return {"data": [
                    {
                        "date_start": "2026-09-01", "spend": "100.75",
                        "impressions": "120", "clicks": "10", "reach": "90",
                        "actions": [{"action_type": "lead", "value": "2"}],
                    },
                    {
                        "date_start": "2026-09-02", "spend": "20.25",
                        "impressions": "50", "clicks": "4", "reach": "30",
                        "actions": [{"action_type": "lead", "value": "1"}],
                    },
                ]}
            if (params or {}).get("level") == "campaign":
                return {"data": [{
                    "date_start": "2026-09-01",
                    "campaign_id": "campaign_1", "campaign_name": "Sandbox Campaign",
                    "spend": "100.75", "impressions": "120", "clicks": "10",
                }]}
        if path == "1234/posts":
            return {"data": [{
                "id": "1234_1", "created_time": "2026-09-01T03:00:00+0000",
                "reactions": {"summary": {"total_count": 4}},
                "comments": {"summary": {"total_count": 2}},
                "shares": {"count": 3},
            }]}
        raise AssertionError("Unexpected provider endpoint: " + path)


class MetaReportingHttpTests(unittest.TestCase):
    START = "2026-09-01"
    END = "2026-09-02"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kdh_meta_http_")
        self.addCleanup(self.temp.cleanup)

        # Prevent accidental access to a real PostgreSQL instance. The app
        # receives DATABASE_URL='' even if the workstation uses PostgreSQL.
        from kdh.app import create_app

        with patch.dict(os.environ, {"META_REPORTING_ALLOW_PRIMARY_CLIENT": "0"}):
            with patch("kdh.app.Meta", FakeMeta):
                self.app = create_app({
                    "TESTING": True,
                    "DATA_DIR": self.temp.name,
                    "DATABASE_URL": "",
                    "DATABASE_BACKEND": "sqlite",
                    "JOB_MODE": "request",
                    "COOKIE_SECURE": False,
                    "APP_URL": "http://localhost",
                    "INITIAL_ADMIN_EMAIL": "",
                    "INITIAL_ADMIN_PASSWORD": "",
                    "META_CLIENT_ID": "client_meta_sandbox",
                })

        self.assertEqual(self.app.extensions["store"].postgres, False)
        self.store = self.app.extensions["store"]
        self.meta = self.app.extensions["meta"]
        self.platform = PlatformData(self.store)
        self.client = self.app.test_client()

        stamp = now()
        self.store.execute(
            """INSERT INTO clients
               (id,name,slug,timezone,active,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            ("client_meta_sandbox", "Meta HTTP Tests", "meta-http-test",
             "Asia/Ho_Chi_Minh", 1, stamp, stamp),
        )
        self.admin_email = "http-test-admin@example.invalid"
        self.admin_password = "temporary-local-test-password"
        self.admin_id = uid()
        self.store.execute(
            """INSERT INTO users
               (id,email,name,password,role,allowed,active,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (self.admin_id, self.admin_email, "HTTP Test Admin",
             generate_password_hash(self.admin_password), "admin", "[]", 1, stamp),
        )
        self.connection_id = self.platform.upsert_connection(
            client_id="client_meta_sandbox", provider="meta",
            external_account_id="999123", account_name="Sandbox Fake OAuth",
        )

        # Use the real Flask login endpoint to obtain cookie + CSRF.
        login = self.client.post(
            "/api/auth/login",
            json={"email": self.admin_email, "password": self.admin_password},
            headers={"X-KDH-Request": "1"},
        )
        self.assertEqual(login.status_code, 200, login.get_data(as_text=True))
        self.csrf = login.get_json()["csrf"]

    def post(self, route, payload, *, csrf=True):
        headers = {"X-KDH-Request": "1"}
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        return self.client.post(route, json=payload, headers=headers)

    def select_asset(self, source, external_id):
        response = self.post("/api/meta/reporting/assets", {
            "source": source, "external_id": external_id, "enabled": True,
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["asset_id"]

    def sync_asset(self, asset_id):
        response = self.post("/api/meta/reporting/sync", {
            "asset_id": asset_id, "start": self.START, "end": self.END,
        })
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job_id = response.get_json()["job_id"]
        self.assertTrue(self.app.extensions["worker"].run_one(job_id))
        job = self.store.one("SELECT status,error FROM jobs WHERE id=?", (job_id,))
        self.assertEqual(job["status"], "succeeded", job)
        return job_id

    def test_01_requires_authentication_and_csrf(self):
        anonymous = self.app.test_client()
        unauthenticated = anonymous.get("/api/meta/reporting/assets")
        self.assertEqual(unauthenticated.status_code, 401)

        without_csrf = self.post("/api/meta/reporting/assets", {
            "source": "facebook_ads", "external_id": "act_123",
            "enabled": True,
        }, csrf=False)
        self.assertEqual(without_csrf.status_code, 403)

    def test_02_discover_assets_without_exposing_tokens(self):
        response = self.client.get("/api/meta/reporting/assets")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["client_id"], "client_meta_sandbox")
        self.assertEqual(data["discovered"]["facebook_ads"][0]["id"], "act_123")
        self.assertEqual(data["discovered"]["facebook_content"][0]["id"], "1234")
        body = response.get_data(as_text=True)
        self.assertNotIn("FAKE_USER_TOKEN", body)
        self.assertNotIn("FAKE_PAGE_TOKEN", body)
        self.assertEqual(data["selected"], [])

    def test_03_reject_assets_outside_meta_grant(self):
        invalid = self.post("/api/meta/reporting/assets", {
            "source": "facebook_ads", "external_id": "act_98765",
            "enabled": True,
        })
        self.assertEqual(invalid.status_code, 403, invalid.get_data(as_text=True))
        missing = self.post("/api/meta/reporting/sync", {
            "asset_id": "not-an-asset", "start": self.START, "end": self.END,
        })
        self.assertEqual(missing.status_code, 403, missing.get_data(as_text=True))

    def test_04_ads_queue_worker_history_and_kpis(self):
        asset_id = self.select_asset("facebook_ads", "act_123")
        self.sync_asset(asset_id)

        history = self.client.get("/api/meta/reporting/syncs/" + asset_id)
        self.assertEqual(history.status_code, 200, history.get_data(as_text=True))
        runs = history.get_json()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "succeeded")
        self.assertEqual(runs[0]["record_count"], 3)

        response = self.client.get(
            "/api/meta/reporting/kpis/" + asset_id
            + "?start=" + self.START + "&end=" + self.END
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data["client_id"], "client_meta_sandbox")
        self.assertEqual(data["source"], "facebook_ads")
        self.assertIs(data["publishable"], False)
        spend = data["metrics"]["facebook_ads.spend"]
        self.assertEqual(spend["status"], "available", spend)
        self.assertEqual(spend["summary"]["value"], 121.0)
        self.assertEqual(spend["currency"], "VND")
        self.assertNotIn("FAKE_USER_TOKEN", response.get_data(as_text=True))

    def test_05_content_queue_worker_and_post_kpi(self):
        asset_id = self.select_asset("facebook_content", "1234")
        self.sync_asset(asset_id)
        response = self.client.get(
            "/api/meta/reporting/kpis/" + asset_id
            + "?start=" + self.START + "&end=" + self.END
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        posts = data["metrics"]["facebook_content.posts_published"]
        self.assertEqual(posts["summary"]["value"], 1)
        engagement = data["metrics"]["facebook_content.engagements"]
        self.assertIsNone(engagement["summary"]["value"])
        self.assertNotIn("FAKE_PAGE_TOKEN", response.get_data(as_text=True))

    def test_06_empty_ads_does_not_invent_kpis(self):
        self.meta.empty_ads = True
        asset_id = self.select_asset("facebook_ads", "act_123")
        self.sync_asset(asset_id)
        response = self.client.get(
            "/api/meta/reporting/kpis/" + asset_id
            + "?start=" + self.START + "&end=" + self.END
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        metric = response.get_json()["metrics"]["facebook_ads.spend"]
        self.assertIsNone(metric["summary"]["value"])
        n = self.store.one("SELECT COUNT(*) AS n FROM daily_metrics WHERE asset_id=?", (asset_id,))
        self.assertEqual(n["n"], 0)

    def test_07_sandbox_marketing_preview(self):
        """Preview reads stored Meta metrics but never creates a Dataset."""
        from kdh.marketing_preview import build_marketing_preview

        before = self.store.one("SELECT COUNT(*) AS n FROM datasets")["n"]
        cases = [
            ("facebook_ads", "act_123", "facebook_ads.spend", 121.0),
            ("facebook_content", "1234", "facebook_content.posts_published", 1),
        ]

        for source, external_id, metric_id, expected in cases:
            with self.subTest(source=source):
                asset_id = self.select_asset(source, external_id)
                self.sync_asset(asset_id)

                preview = build_marketing_preview(
                    self.store,
                    client_id="client_meta_sandbox",
                    allowed_sources={source},
                    source=source,
                    asset_id=asset_id,
                    start=self.START,
                    end=self.END,
                )

                self.assertEqual(preview["client_id"], "client_meta_sandbox")
                self.assertEqual(preview["sources"], [source])
                self.assertIs(preview["publishable"], False)
                self.assertIs(preview["quality"]["independently_verified"], False)

                values = {
                    item["metric_id"]: item["value"]
                    for item in preview["widgets"]
                }
                self.assertEqual(values[metric_id], expected)
                if source == "facebook_content":
                    self.assertIsNone(values["facebook_content.engagements"])

        after = self.store.one("SELECT COUNT(*) AS n FROM datasets")["n"]
        self.assertEqual(before, after, "Preview must not create a Dataset")

    def test_08_sandbox_preview_api(self):
        """Admin Preview API returns unverified data without mutating datasets."""
        before = self.store.one("SELECT COUNT(*) AS n FROM datasets")["n"]
        cases = [
            ("facebook_ads", "act_123", "facebook_ads.spend", 121.0),
            ("facebook_content", "1234", "facebook_content.posts_published", 1),
        ]

        for source, external_id, metric_id, expected in cases:
            with self.subTest(source=source):
                asset_id = self.select_asset(source, external_id)
                self.sync_asset(asset_id)

                response = self.client.get(
                    "/api/meta/reporting/preview",
                    query_string={
                        "asset_id": asset_id,
                        "start": self.START,
                        "end": self.END,
                    },
                )
                self.assertEqual(
                    response.status_code,
                    200,
                    response.get_data(as_text=True),
                )
                preview = response.get_json()
                self.assertEqual(preview["client_id"], "client_meta_sandbox")
                self.assertEqual(preview["sources"], [source])
                self.assertIs(preview["publishable"], False)
                self.assertIs(preview["quality"]["independently_verified"], False)

                values = {
                    item["metric_id"]: item["value"]
                    for item in preview["widgets"]
                }
                self.assertEqual(values[metric_id], expected)
                if source == "facebook_content":
                    self.assertIsNone(values["facebook_content.engagements"])

                body = response.get_data(as_text=True)
                self.assertNotIn("FAKE_USER_TOKEN", body)
                self.assertNotIn("FAKE_PAGE_TOKEN", body)

        after = self.store.one("SELECT COUNT(*) AS n FROM datasets")["n"]
        self.assertEqual(before, after, "Preview API must not create a Dataset")


if __name__ == "__main__":
    unittest.main()
