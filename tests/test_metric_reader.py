"""Step 8.3 safety tests; isolated in-memory DB, no external APIs."""

import json
import sqlite3
import unittest

from kdh.metric_reader import read_metric_series


class MiniStore:
    """Minimal Store.one/all adapter backed by exact foundation columns."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE source_assets (
                id TEXT PRIMARY KEY, client_id TEXT NOT NULL,
                provider TEXT NOT NULL, asset_type TEXT NOT NULL,
                currency TEXT, enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE sync_runs (
                id TEXT PRIMARY KEY, client_id TEXT NOT NULL,
                asset_id TEXT, provider TEXT NOT NULL,
                sync_type TEXT NOT NULL DEFAULT 'manual',
                status TEXT NOT NULL, record_count INTEGER NOT NULL,
                requested_start TEXT, requested_end TEXT,
                created_at TEXT NOT NULL, latest_available_date TEXT,
                error_code TEXT
            );
            CREATE TABLE daily_metrics (
                id TEXT PRIMARY KEY, client_id TEXT NOT NULL,
                asset_id TEXT NOT NULL, provider TEXT NOT NULL,
                entity_type TEXT NOT NULL, entity_id TEXT NOT NULL DEFAULT '',
                dimension_key TEXT NOT NULL DEFAULT '',
                dimensions TEXT NOT NULL DEFAULT '{}',
                metric_date TEXT NOT NULL, metrics TEXT NOT NULL,
                sync_run_id TEXT, fetched_at TEXT NOT NULL
            );
            CREATE TABLE source_snapshots (
                sync_run_id TEXT PRIMARY KEY, payload TEXT, source_key TEXT,
                client_id TEXT, asset_id TEXT, provider TEXT,
                requested_start TEXT, requested_end TEXT
            );
            """
        )

    def all(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def close(self):
        self.db.close()


class MetricReaderTests(unittest.TestCase):
    CLIENT = "client_kinderhealth"
    START = "2026-09-01"
    END = "2026-09-02"

    def setUp(self):
        self.store = MiniStore()

    def tearDown(self):
        self.store.close()

    def asset(self, *, aid="ga4-a", client=None, provider="google", asset_type="ga4_property", currency=None, enabled=1):
        self.store.db.execute(
            "INSERT INTO source_assets VALUES (?,?,?,?,?,?)",
            (aid, client or self.CLIENT, provider, asset_type, currency, enabled),
        )
        return aid

    def sync(self, *, sid="run-1", aid="ga4-a", client=None, provider="google", status="succeeded", count=2,
             created_at="2026-10-01T00:00:00Z", sync_type="manual", error_code=None):
        self.store.db.execute(
            "INSERT INTO sync_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, client or self.CLIENT, aid, provider, sync_type, status, count, self.START, self.END,
             created_at, self.END, error_code),
        )
        return sid

    def row(self, *, rid="row-1", aid="ga4-a", sid="run-1", client=None, provider="google", entity="website",
            day="2026-09-01", metrics=None, entity_id="", dimension_key="", dimensions=None):
        self.store.db.execute(
            "INSERT INTO daily_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, client or self.CLIENT, aid, provider, entity, entity_id, dimension_key,
             json.dumps(dimensions if dimensions is not None else {}), day,
             json.dumps(metrics if metrics is not None else {"sessions": 120}), sid,
             "2026-10-01T00:00:00Z"),
        )

    def read(self, metric="ga4.sessions", *, client=None, allowed=None, asset_id=None, start=None, end=None):
        return read_metric_series(
            self.store, metric_id=metric,
            client_id=client or self.CLIENT,
            allowed_sources=(allowed if allowed is not None else {"ga4"}),
            start=start or self.START, end=end or self.END,
            asset_id=asset_id,
        )

    def test_empty_db_is_not_configured(self):
        item = self.read()
        self.assertEqual(item["status"], "not_configured")
        self.assertIsNone(item["summary"]["value"])

    def test_denies_unapproved_source_before_database_query(self):
        with self.assertRaises(PermissionError):
            self.read(allowed={"gsc"})

    def test_success_from_succeeded_sync_and_safe_additive_total(self):
        self.asset()
        self.sync()
        self.row(metrics={"sessions": 120, "active_users": 100})
        self.row(rid="row-2", day="2026-09-02", metrics={"sessions": 130, "active_users": 110})
        result = self.read()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["summary"]["value"], 250)
        self.assertEqual(result["summary"]["coverage_days"], 2)
        self.assertEqual([r["value"] for r in result["series"]], [120, 130])
        self.assertEqual(result["series"][0]["sync_run_id"], "run-1")
        self.assertEqual(result["data_origin"], "persisted_unverified")

    def test_distinct_count_has_no_cross_day_total(self):
        self.asset()
        self.sync()
        self.row(metrics={"active_users": 100})
        self.row(rid="row-2", day="2026-09-02", metrics={"active_users": 110})
        result = self.read("ga4.active_users")
        self.assertEqual(result["status"], "available")
        self.assertEqual([d["value"] for d in result["series"]], [100, 110])
        self.assertIsNone(result["summary"]["value"])

    def test_ratio_keeps_day_values_without_calculating_false_total(self):
        self.asset(aid="gsc-a",asset_type="search_console_property")
        self.sync(aid="gsc-a")
        self.row(aid="gsc-a", metrics={"ctr": 0.25})
        self.row(rid="row-2", aid="gsc-a", day="2026-09-02", metrics={"ctr": 0.4})
        res = self.read("gsc.ctr", allowed={"gsc"})
        self.assertEqual(res["status"], "available")
        self.assertIsNone(res["summary"]["value"])

    def test_missing_date_never_becomes_zero(self):
        self.asset()
        self.sync()
        self.row(metrics={"sessions": 23})
        item = self.read()
        self.assertEqual(item["status"], "partial")
        self.assertIsNone(item["summary"]["value"])
        self.assertEqual(len(item["series"]), 1)

    def test_failure_only_is_no_data(self):
        self.asset()
        self.sync(status="failed",count=0,error_code="permission_denied")
        self.row()
        res = self.read()
        self.assertEqual(res["status"], "no_data")
        self.assertEqual(res["series"], [])
        self.assertIsNone(res["summary"]["value"])
        self.assertIn("permission_denied", " ".join(res["warnings"]))

    def test_last_failure_marks_prior_data_stale(self):
        self.asset()
        self.sync()
        self.row()
        self.row(rid="row-2",day=self.END,metrics={"sessions": 130})
        self.sync(sid="run-2",status="failed",count=0,created_at="2026-10-02T00:00:00Z",error_code="permission_denied")
        res = self.read()
        self.assertEqual(res["status"], "stale")
        self.assertEqual(res["summary"]["value"], 250)
        self.assertEqual(res["freshness"]["latest_sync_status"], "failed")

    def test_mixed_clients_never_expose_other_client_rows(self):
        self.asset()
        self.sync()
        self.row(client="another-client")
        self.row(rid="row-2",client="another-client",day=self.END,metrics={"sessions": 130})
        self.assertEqual(self.read()["status"], "no_data")
        self.assertEqual(self.read()["series"], [])

    def test_cannot_query_another_clients_asset(self):
        self.asset(aid="other", client="another-client")
        self.assertEqual(self.read(asset_id="other")["status"], "asset_not_available")
        self.assertIsNone(self.read(asset_id="other")["asset_id"])

    def test_ambiguous_assets_require_explicit_selection(self):
        self.asset(aid="ga4-a")
        self.asset(aid="ga4-b")
        self.assertEqual(self.read()["status"], "asset_selection_required")
        self.sync()
        self.row()
        self.assertEqual(self.read(asset_id="ga4-a")["status"], "partial")

    def test_detailed_rows_are_not_summed_into_canonical_day(self):
        self.asset()
        self.sync()
        self.row(entity_id="post-1", metrics={"sessions": 10})
        self.row(rid="row-2", day=self.END, dimension_key="campaign=abc", metrics={"sessions": 20})
        self.assertEqual(self.read()["status"], "no_data")

    def test_nonempty_dimensions_cannot_claim_summary_even_with_blank_key(self):
        self.asset()
        self.sync()
        self.row(dimensions={"campaign": "ad-1"}, metrics={"sessions": 55})
        self.row(rid="row-2", day=self.END, dimensions={"channel": "paid"}, metrics={"sessions": 75})
        self.assertEqual(self.read()["status"], "no_data")

    def test_corrupt_dimensions_are_not_treated_as_summary(self):
        self.asset()
        self.sync()
        self.row()
        self.store.db.execute("UPDATE daily_metrics SET dimensions='broken' WHERE id='row-1'")
        self.assertEqual(self.read()["status"], "no_data")

    def test_unknown_latest_data_date_keeps_total_unavailable(self):
        self.asset()
        self.sync()
        self.row()
        self.row(rid="row-2", day=self.END, metrics={"sessions": 130})
        self.store.db.execute("UPDATE sync_runs SET latest_available_date=NULL")
        res = self.read()
        self.assertEqual(res["status"], "partial")
        self.assertIsNone(res["summary"]["value"])

    def test_latest_empty_success_cannot_represent_old_data_as_fresh(self):
        self.asset()
        self.sync()
        self.row()
        self.row(rid="row-2", day=self.END, metrics={"sessions": 130})
        self.sync(sid="run-2", status="succeeded", count=0,
                  created_at="2026-10-02T00:00:00Z")
        res = self.read()
        self.assertEqual(res["status"], "stale")
        self.assertEqual(res["summary"]["value"], 250)

    def test_invalid_values_are_ignored(self):
        self.asset()
        self.sync()
        self.row(metrics={"sessions": True})
        self.row(rid="row-2",day=self.END,metrics={"sessions": float("nan")})
        res = self.read()
        self.assertEqual(res["status"], "no_data")

    def test_derived_snapshot_and_month_return_unsupported(self):
        for metric, allowed in [
            ("facebook_ads.calculated_cpl", {"facebook_ads"}),
            ("keywords.top10", {"keywords"}),
            ("gmb.search_keyword_impressions", {"gmb"}),
        ]:
            with self.subTest(metric=metric):
                res = self.read(metric, allowed=allowed)
                self.assertEqual(res["status"], "not_configured" if metric == "keywords.top10" else "unsupported")
                self.assertIsNone(res["summary"]["value"])

    def test_multiple_providers_supported_by_same_reader(self):
        sources = [
            ("facebook_ads", "meta", "facebook_ad_account", "ad_account", "spend", "VND"),
            ("tiktok_ads", "tiktok", "tiktok_ad_account", "ad_account", "spend", "VND"),
            ("youtube", "youtube", "youtube_channel", "channel", "views", None),
            ("gmb", "gmb", "business_location", "location", "website_clicks", None),
        ]
        for idx, (source, provider, asset_type, entity_type, key, currency) in enumerate(sources):
            aid=f"asset-{idx}"
            sid=f"run-{idx}"
            self.asset(aid=aid,provider=provider,asset_type=asset_type,currency=currency)
            self.sync(sid=sid,aid=aid,provider=provider)
            self.row(rid=f"m-{idx}-1",aid=aid,sid=sid,provider=provider,entity=entity_type,metrics={key: 10})
            self.row(rid=f"m-{idx}-2",aid=aid,sid=sid,provider=provider,entity=entity_type,day=self.END,metrics={key: 15})
            res=self.read(f"{source}.{key}",allowed={source})
            self.assertEqual(res["status"],"available",source)
            self.assertEqual(res["summary"]["value"],25,source)

    def test_period_validation_and_disabled_assets(self):
        self.asset(enabled=0)
        self.assertEqual(self.read()["status"], "not_configured")
        with self.assertRaises(ValueError):
            self.read(start="2026-09-03")
        with self.assertRaises(ValueError):
            self.read(start="2024-01-01")
        with self.assertRaises(ValueError):
            self.read(start="not-a-date")

    def test_source_without_currency_cannot_report_monetary_period_value(self):
        self.asset(aid="fb",provider="meta",asset_type="facebook_ad_account",currency=None)
        self.sync(aid="fb",provider="meta")
        self.row(aid="fb",provider="meta",entity="ad_account",metrics={"spend": 5})
        self.row(aid="fb",provider="meta",entity="ad_account",rid="row-2",day=self.END,metrics={"spend": 6})
        res=self.read("facebook_ads.spend",allowed={"facebook_ads"})
        self.assertEqual(res["status"],"available")
        self.assertIsNone(res["summary"]["value"])

    def test_validation_sync_is_not_used_as_reporting_lineage(self):
        self.asset()
        self.sync(sync_type="validation")
        self.row()
        self.assertEqual(self.read()["status"], "no_data")


if __name__ == "__main__":
    unittest.main()
