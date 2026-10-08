import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from kdh.core import Store, TYPES, filters, now, pack, uid
from kdh.jobs import Worker, enqueue
from kdh.google import SourceError
from kdh.platform_data import DEFAULT_CLIENT_ID, PlatformData


class FakeGoogle:
    """
    Google giả CHỈ dành cho test.

    Không gọi Google API.
    Không dùng OAuth token.
    Không dùng secret.
    Không phải mock fallback của production.
    """

    def __init__(self, store):
        self.store = store
        self.platform = PlatformData(store)

        # Worker cần JOB_MODE để chạy theo request mode.
        self.config = {
            "JOB_MODE": "request",
        }

    def ensure_platform_records(self):
        connection_id = self.platform.upsert_connection(
            client_id=DEFAULT_CLIENT_ID,
            provider="google",
            external_account_id="fake-google-account",
            account_name="Fake Google Test Account",
            account_email="fake-test@example.com",
            status="connected",
            secret_name=None,
        )

        assets = {
            "ga4": self.platform.upsert_asset(
                client_id=DEFAULT_CLIENT_ID,
                provider="google",
                asset_type="ga4_property",
                external_id="fake-ga4-property",
                name="Fake GA4 Property",
                connection_id=connection_id,
                timezone="Asia/Ho_Chi_Minh",
            ),

            "gsc": self.platform.upsert_asset(
                client_id=DEFAULT_CLIENT_ID,
                provider="google",
                asset_type="search_console_property",
                external_id="https://kinderhealth.vn/",
                name="Fake Search Console Property",
                connection_id=connection_id,
                timezone="America/Los_Angeles",
            ),

            "keywords": self.platform.upsert_asset(
                client_id=DEFAULT_CLIENT_ID,
                provider="google",
                asset_type="keyword_sheet",
                external_id="fake-keyword-sheet:Ranking",
                name="Fake Keyword Sheet",
                connection_id=connection_id,
                timezone="Asia/Ho_Chi_Minh",
            ),
        }

        return {
            "connection_id": connection_id,
            "assets": assets,
        }

    def fetch(self, source, params):
        """
        Giả lập response SAU KHI provider adapter đã normalize.

        source_result() trong production vẫn xử lý object này
        giống như dữ liệu Google thật.
        """

        responses = {
            "ga4": {
                "totals": {
                    "activeUsers": 300,
                    "sessions": 373,
                    "screenPageViews": 670,
                    "engagementRate": 0.62,
                },
                "daily": [
                    {
                        "date": "2026-09-01",
                        "activeUsers": 100,
                        "sessions": 120,
                        "screenPageViews": 210,
                        "engagementRate": 0.60,
                    },
                    {
                        "date": "2026-09-02",
                        "activeUsers": 110,
                        "sessions": 135,
                        "screenPageViews": 240,
                        "engagementRate": 0.64,
                    },
                    {
                        "date": "2026-09-03",
                        "activeUsers": 90,
                        "sessions": 118,
                        "screenPageViews": 220,
                        "engagementRate": 0.62,
                    },
                ],
                "previous": None,
                "previous_daily": [],
                "channels": [],
                "pages": [],
                "latest_available_date": "2026-09-03",
                "timezone": "Asia/Ho_Chi_Minh",
                "asset": "fake-ga4-property",
                "warnings": [],
            },

            "gsc": {
                "totals": {
                    "clicks": 72,
                    "impressions": 3100,
                    "ctr": 0.0232,
                    "position": 8.7,
                },
                "daily": [
                    {
                        "date": "2026-09-01",
                        "clicks": 20,
                        "impressions": 900,
                        "ctr": 0.0222,
                        "position": 9.2,
                    },
                    {
                        "date": "2026-09-02",
                        "clicks": 27,
                        "impressions": 1100,
                        "ctr": 0.0245,
                        "position": 8.5,
                    },
                    {
                        "date": "2026-09-03",
                        "clicks": 25,
                        "impressions": 1100,
                        "ctr": 0.0227,
                        "position": 8.4,
                    },
                ],
                "queries": [],
                "previous": None,
                "previous_daily": [],
                "latest_available_date": "2026-09-03",
                "timezone": "America/Los_Angeles",
                "asset": "https://kinderhealth.vn/",
                "warnings": [],
            },

            "keywords": {
                "totals": {
                    "top5": 1,
                    "top10": 2,
                    "top20": 3,
                    "top100": 3,
                },
                "entries": [
                    {
                        "date": "2026-09-01",
                        "keyword": "khám nhi tphcm",
                        "position": 12,
                        "url": "https://kinderhealth.vn/",
                    },
                    {
                        "date": "2026-09-02",
                        "keyword": "bác sĩ nhi tphcm",
                        "position": 7,
                        "url": "https://kinderhealth.vn/",
                    },
                    {
                        "date": "2026-09-03",
                        "keyword": "phòng khám nhi",
                        "position": 4,
                        "url": "https://kinderhealth.vn/",
                    },
                ],
                "previous": None,
                "previous_entries": [],
                "previous_date": None,
                "latest_available_date": "2026-09-03",
                "timezone": "Ngày tracking trong Google Sheets",
                "asset": "Ranking",
                "warnings": [],
            },
        }

        if source not in responses:
            raise AssertionError(
                f"FakeGoogle không hỗ trợ source: {source}"
            )

        # Tránh test vô tình mutate dữ liệu mẫu.
        return copy.deepcopy(responses[source])


class GooglePlatformSuccessTests(unittest.TestCase):

    def setUp(self):
        # Database hoàn toàn tạm thời.
        # Test xong TemporaryDirectory sẽ bị xóa.
        self.tmp = tempfile.TemporaryDirectory()

        self.store = Store(
            self.tmp.name,
            database_url="",
        )

        self._prepare_worker()

    def _prepare_worker(self):
        no_network = patch("requests.sessions.Session.request", side_effect=AssertionError("Network disabled in tests"))
        no_network.start()
        self.addCleanup(no_network.stop)

        self.google = FakeGoogle(
            self.store
        )

        self.worker = Worker(
            self.store,
            self.google,
        )

        self.admin_id = uid()

        self.store.execute(
            """
            INSERT INTO users (
                id,
                email,
                name,
                password,
                role,
                allowed,
                active,
                created_at
            )
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                self.admin_id,
                "admin-test@example.com",
                "Admin Test",
                "not-used-in-this-test",
                "admin",
                pack(list(TYPES)),
                1,
                now(),
            ),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_google_success_creates_three_sync_runs_and_daily_metrics(self):
        params = filters({
            "report_type": "seo",
            "start": "2026-09-01",
            "end": "2026-09-03",
            "compare": False,
        })

        job_id, created = enqueue(
            self.store,
            self.admin_id,
            "connection",
            params,
        )

        self.assertTrue(created)

        executed = self.worker.run_one(
            job_id=job_id
        )

        self.assertTrue(executed)

        snapshots = self.store.all("SELECT * FROM source_snapshots ORDER BY source_key")
        self.assertEqual(len(snapshots), 3)
        self.assertEqual({row["source_key"] for row in snapshots}, {"ga4", "gsc", "keywords"})
        for row in snapshots:
            self.assertEqual(row["provider"], "google")
            self.assertEqual(row["requested_start"], "2026-09-01")
            self.assertEqual(row["requested_end"], "2026-09-03")
            payload = json.loads(row["payload"])
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(payload["source"], row["source_key"])
            # Preserve all normalized provider fields, not just daily metrics.
            expected = self.google.fetch(row["source_key"], params)
            for key, value in expected.items():
                self.assertEqual(payload[key], value)
            fields = {"ga4": {"totals", "daily", "channels", "pages"},
                      "gsc": {"totals", "daily", "queries"},
                      "keywords": {"totals", "entries"}}[row["source_key"]]
            self.assertTrue(fields <= payload.keys())

        # =========================================================
        # JOB
        # =========================================================

        job = self.store.one(
            """
            SELECT
                id,
                status,
                error,
                started_at,
                finished_at
            FROM jobs
            WHERE id=?
            """,
            (job_id,),
        )

        self.assertIsNotNone(job)

        self.assertEqual(
            job["status"],
            "succeeded",
        )

        self.assertIsNone(
            job["error"]
        )

        # =========================================================
        # SYNC RUNS
        # =========================================================

        sync_runs = self.store.all(
            """
            SELECT
                sa.asset_type,
                sr.id,
                sr.status,
                sr.error_code,
                sr.error_message,
                sr.record_count,
                sr.requested_start,
                sr.requested_end,
                sr.latest_available_date
            FROM sync_runs sr
            JOIN source_assets sa
              ON sa.id=sr.asset_id
            WHERE sr.job_id=?
            ORDER BY sa.asset_type
            """,
            (job_id,),
        )

        self.assertEqual(
            len(sync_runs),
            3,
        )

        expected_assets = {
            "ga4_property",
            "search_console_property",
            "keyword_sheet",
        }

        self.assertEqual(
            {
                row["asset_type"]
                for row in sync_runs
            },
            expected_assets,
        )

        for row in sync_runs:
            self.assertEqual(
                row["status"],
                "succeeded",
            )

            self.assertIsNone(
                row["error_code"]
            )

            self.assertIsNone(
                row["error_message"]
            )

            self.assertEqual(
                row["record_count"],
                3,
            )

            self.assertEqual(
                row["requested_start"],
                "2026-09-01",
            )

            self.assertEqual(
                row["requested_end"],
                "2026-09-03",
            )

            self.assertEqual(
                row["latest_available_date"],
                "2026-09-03",
            )

        # =========================================================
        # DAILY METRICS
        # =========================================================

        metrics_total = self.store.one(
            """
            SELECT COUNT(*) AS n
            FROM daily_metrics
            WHERE sync_run_id IN (
                SELECT id
                FROM sync_runs
                WHERE job_id=?
            )
            """,
            (job_id,),
        )

        self.assertEqual(
            metrics_total["n"],
            9,
        )

        metrics_by_asset = self.store.all(
            """
            SELECT
                sa.asset_type,
                COUNT(*) AS n,
                MIN(dm.metric_date) AS first_date,
                MAX(dm.metric_date) AS last_date
            FROM daily_metrics dm
            JOIN source_assets sa
              ON sa.id=dm.asset_id
            WHERE dm.sync_run_id IN (
                SELECT id
                FROM sync_runs
                WHERE job_id=?
            )
            GROUP BY sa.asset_type
            ORDER BY sa.asset_type
            """,
            (job_id,),
        )

        self.assertEqual(
            len(metrics_by_asset),
            3,
        )

        for row in metrics_by_asset:
            self.assertEqual(
                row["n"],
                3,
            )

            self.assertEqual(
                row["first_date"],
                "2026-09-01",
            )

            self.assertEqual(
                row["last_date"],
                "2026-09-03",
            )

        # =========================================================
        # VERIFY ONE GA4 ROW
        # =========================================================

        ga4_row = self.store.one(
            """
            SELECT dm.metrics
            FROM daily_metrics dm
            JOIN source_assets sa
              ON sa.id=dm.asset_id
            WHERE sa.asset_type='ga4_property'
              AND dm.metric_date='2026-09-01'
            LIMIT 1
            """
        )

        self.assertIsNotNone(
            ga4_row
        )

        ga4_metrics = json.loads(
            ga4_row["metrics"]
        )

        self.assertEqual(
            ga4_metrics["active_users"],
            100,
        )

        self.assertEqual(
            ga4_metrics["sessions"],
            120,
        )

        self.assertEqual(
            ga4_metrics["page_views"],
            210,
        )

        # =========================================================
        # VERIFY ONE GSC ROW
        # =========================================================

        gsc_row = self.store.one(
            """
            SELECT dm.metrics
            FROM daily_metrics dm
            JOIN source_assets sa
              ON sa.id=dm.asset_id
            WHERE sa.asset_type='search_console_property'
              AND dm.metric_date='2026-09-03'
            LIMIT 1
            """
        )

        self.assertIsNotNone(
            gsc_row
        )

        gsc_metrics = json.loads(
            gsc_row["metrics"]
        )

        self.assertEqual(
            gsc_metrics["clicks"],
            25,
        )

        self.assertEqual(
            gsc_metrics["impressions"],
            1100,
        )

        # =========================================================
        # VERIFY KEYWORD ROW
        # =========================================================

        keyword_row = self.store.one(
            """
            SELECT
                dm.entity_id,
                dm.dimensions,
                dm.metrics
            FROM daily_metrics dm
            JOIN source_assets sa
              ON sa.id=dm.asset_id
            WHERE sa.asset_type='keyword_sheet'
              AND dm.metric_date='2026-09-03'
            LIMIT 1
            """
        )

        self.assertIsNotNone(
            keyword_row
        )

        self.assertEqual(
            keyword_row["entity_id"],
            "phòng khám nhi",
        )

        keyword_metrics = json.loads(
            keyword_row["metrics"]
        )

        self.assertEqual(
            keyword_metrics["position"],
            4,
        )

        # =========================================================
        # WATERMARKS
        # =========================================================

        watermarks = self.store.all(
            """
            SELECT
                sa.asset_type,
                sw.last_complete_date
            FROM sync_watermarks sw
            JOIN source_assets sa
              ON sa.id=sw.asset_id
            ORDER BY sa.asset_type
            """
        )

        self.assertEqual(
            len(watermarks),
            3,
        )

        for row in watermarks:
            self.assertEqual(
                row["last_complete_date"],
                "2026-09-03",
            )

        # =========================================================
        # CONNECTION
        # =========================================================

        connection = self.store.one(
            """
            SELECT *
            FROM connections
            WHERE client_id=?
              AND provider='google'
            LIMIT 1
            """,
            (DEFAULT_CLIENT_ID,),
        )

        self.assertIsNotNone(
            connection
        )

        self.assertIsNotNone(
            connection["last_sync_at"]
        )

        # Connection-validation job chưa tạo dataset.
        # Dataset sẽ được xây từ Data Foundation ở bước kế tiếp.
        dataset_count = self.store.one(
            """
            SELECT COUNT(*) AS n
            FROM datasets
            """
        )

        self.assertEqual(
            dataset_count["n"],
            0,
        )


    def _run_connection(self, fetch):
        params = filters({"report_type": "seo", "start": "2026-09-01", "end": "2026-09-03", "compare": False})
        job_id, _ = enqueue(self.store, self.admin_id, "connection", params)
        with patch.object(self.google, "fetch", side_effect=fetch):
            self.assertTrue(self.worker.run_one(job_id=job_id))
        return job_id

    def test_provider_failures_create_no_metrics_or_snapshots_for_failed_source(self):
        original = self.google.fetch
        for status in ("permission_denied", "disconnected", "revoked", "timeout", "api_error", "invalid_data"):
            with self.subTest(status=status):
                def fetch(source, params):
                    if source == "ga4":
                        raise SourceError(status, "Provider unavailable")
                    return original(source, params)

                job_id = self._run_connection(fetch)
                runs = self.store.all("SELECT * FROM sync_runs WHERE job_id=?", (job_id,))
                failed = [r for r in runs if r["status"] == "failed"]
                self.assertEqual(len(failed), 1)
                self.assertEqual(failed[0]["error_code"], status)
                self.assertEqual(failed[0]["record_count"], 0)
                asset_id = failed[0]["asset_id"]
                for table in ("daily_metrics", "source_snapshots"):
                    self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM " + table + " WHERE asset_id=?", (asset_id,))["n"], 0)
                self.assertEqual(sum(r["record_count"] for r in runs), 6)
                snapshots = self.store.all("SELECT s.source_key FROM source_snapshots s JOIN sync_runs r ON r.id=s.sync_run_id WHERE r.job_id=?", (job_id,))
                self.assertEqual({r["source_key"] for r in snapshots}, {"gsc", "keywords"})
                self.assertEqual(self.store.one("SELECT status FROM jobs WHERE id=?", (job_id,))["status"], "partial")

    def test_partial_result_is_saved_exactly_with_provider_specific_fields(self):
        original = self.google.fetch
        def fetch(source, params):
            result = original(source, params)
            if source == "ga4":
                result["latest_available_date"] = "2026-09-02"
                result["daily"] = result["daily"][:2]
                result["channels"] = [{"channel": "Organic Search", "sessions": None}]
                result["pages"] = [{"path": "/pediatrics", "views": 0}]
            return result

        job_id = self._run_connection(fetch)
        row = self.store.one("SELECT s.payload,r.status,r.record_count FROM source_snapshots s JOIN sync_runs r ON r.id=s.sync_run_id WHERE r.job_id=? AND s.source_key='ga4'", (job_id,))
        self.assertEqual((row["status"], row["record_count"]), ("partial", 2))
        payload = json.loads(row["payload"])
        self.assertEqual(payload["status"], "delayed")
        self.assertEqual(payload["channels"], [{"channel": "Organic Search", "sessions": None}])
        self.assertEqual(payload["pages"], [{"path": "/pediatrics", "views": 0}])
        self.assertTrue(payload["warnings"])

    def test_snapshot_persistence_failure_marks_sync_and_step_invalid_without_leaking_error(self):
        original = self.worker.platform.save_source_snapshot
        def save(**kwargs):
            if kwargs["source_key"] == "ga4":
                raise RuntimeError("private-storage-detail-not-for-users")
            return original(**kwargs)

        with patch.object(self.worker.platform, "save_source_snapshot", side_effect=save):
            job_id = self._run_connection(self.google.fetch)
        failed = self.store.one("SELECT * FROM sync_runs WHERE job_id=? AND status='failed'", (job_id,))
        self.assertEqual(failed["error_code"], "persistence_error")
        self.assertEqual(failed["record_count"], 0)
        self.assertNotIn("private-storage-detail", failed["error_message"])
        self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM source_snapshots WHERE sync_run_id=?", (failed["id"],))["n"], 0)
        job = self.store.one("SELECT status,steps FROM jobs WHERE id=?", (job_id,))
        self.assertEqual(job["status"], "partial")
        step = next(s for s in json.loads(job["steps"]) if s["source"] == "ga4")
        self.assertEqual(step["status"], "invalid_data")
        self.assertNotIn("private-storage-detail", step["error"])
        self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM sync_watermarks WHERE asset_id=?", (failed["asset_id"],))["n"], 0)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Requires an isolated PostgreSQL test database")
class PostgresGooglePlatformSuccessTests(GooglePlatformSuccessTests):
    def setUp(self):
        from test_platform_data import PostgresPlatformDataTests
        PostgresPlatformDataTests.setUp(self)
        self._prepare_worker()


if __name__ == "__main__":
    unittest.main()
