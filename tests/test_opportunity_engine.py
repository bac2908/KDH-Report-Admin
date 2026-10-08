
"""Tests for Opportunity Engine using fake Evidence records."""

import unittest
from unittest.mock import patch

from kdh.opportunity_engine import build_opportunities


CLIENT = "client_kinderhealth"

CURRENT = {
    "start": "2026-09-03",
    "end": "2026-09-04",
}

PREVIOUS = {
    "start": "2026-09-01",
    "end": "2026-09-02",
}


def evidence(
    metric_id,
    now=60,
    before=100,
    *,
    status="available",
    origin="persisted_unverified",
    demo=None,
    client=CLIENT,
    asset="asset-1",
    lineage=True,
    comp_status="available",
    unit="count",
):
    return {
        "schema_version": "1.0",
        "evidence_id": "evidence-" + metric_id,
        "metric": {
            "id": metric_id,
            "label": metric_id,
            "unit": unit,
        },
        "scope": {
            "client_id": client,
            "asset_id": asset,
            "period": dict(CURRENT),
        },
        "source": {
            "key": metric_id.split(".")[0]
        },
        "result": {
            "status": status,
            "evidence_status": (
                "recorded_unverified"
                if status == "available"
                else "not_ready"
            ),
            "value": now,
        },
        "quality": {
            "data_origin": origin,
            "is_demo": demo,
            "independently_verified": False,
        },
        "lineage": {
            "sync_run_count": 1 if lineage else 0,
            "sync_run_ids": (
                ["run-current"] if lineage else []
            ),
        },
        "comparison": {
            "status": comp_status,
            "previous_value": before,
            "period": dict(PREVIOUS),
            "lineage": {
                "sync_run_count": 1,
                "sync_run_ids": ["run-previous"],
            },
        },
    }


def call(source, data=None, **kwargs):
    data = data or {}

    def fake(
        store,
        *,
        metric_id,
        client_id,
        allowed_sources,
        start,
        end,
        compare_start,
        compare_end,
        asset_id,
    ):
        assert client_id == CLIENT
        assert metric_id.split(".")[0] in allowed_sources

        assert (start, end) == (
            CURRENT["start"],
            CURRENT["end"],
        )

        assert (compare_start, compare_end) == (
            PREVIOUS["start"],
            PREVIOUS["end"],
        )

        assert asset_id is None or asset_id == "asset-1"

        return data.get(
            metric_id,
            evidence(metric_id, status="no_data"),
        )

    with patch(
        "kdh.opportunity_engine.build_metric_evidence",
        side_effect=fake,
    ) as mocked:
        result = build_opportunities(
            None,
            client_id=CLIENT,
            allowed_sources={source},
            start=CURRENT["start"],
            end=CURRENT["end"],
            source=source,
            **kwargs,
        )

    return result, mocked.call_count


class OpportunityEngineTests(unittest.TestCase):

    def test_no_data_yields_no_opportunities(self):
        result, count = call("gsc")

        self.assertEqual(
            result["summary"]["candidate_count"], 0
        )
        self.assertEqual(result["opportunities"], [])
        self.assertGreaterEqual(count, 1)

    def test_gsc_clicks_drop_is_review_only(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", 60, 140
            ),
        })

        self.assertEqual(
            result["summary"]["candidate_count"], 1
        )

        item = result["opportunities"][0]

        self.assertEqual(
            item["rule_id"], "gsc_clicks_down"
        )
        self.assertEqual(
            item["status"], "candidate_unverified"
        )
        self.assertFalse(item["publishable"])
        self.assertTrue(item["review_required"])

        self.assertEqual(
            item["evidence"][0]["sync_run_ids"],
            ["run-current"],
        )

    def test_small_change_is_ignored(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", 99, 100
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_small_baseline_is_ignored(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", 10, 20
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_stale_data_is_rejected(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", status="stale"
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_demo_data_is_rejected(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", demo=True
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_missing_lineage_is_rejected(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", lineage=False
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_wrong_client_is_rejected(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks", client="another"
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_missing_comparison_is_rejected(self):
        result, _ = call("gsc", {
            "gsc.clicks": evidence(
                "gsc.clicks",
                comp_status="insufficient_data",
            ),
        })
        self.assertEqual(result["opportunities"], [])

    def test_ctr_needs_sufficient_impressions(self):
        ctr = evidence(
            "gsc.ctr",
            now=0.02,
            before=0.06,
            unit="ratio",
        )

        low = evidence(
            "gsc.impressions",
            now=100,
            before=2000,
        )

        result, _ = call("gsc", {
            "gsc.ctr": ctr,
            "gsc.impressions": low,
        })

        self.assertEqual(
            result["summary"]["candidate_count"], 0
        )

        enough = evidence(
            "gsc.impressions",
            now=1500,
            before=2000,
        )

        result, _ = call("gsc", {
            "gsc.ctr": ctr,
            "gsc.impressions": enough,
        })

        self.assertEqual(
            len(result["opportunities"]), 1
        )

        item = result["opportunities"][0]

        self.assertEqual(
            item["rule_id"], "gsc_ctr_down"
        )
        self.assertAlmostEqual(
            item["signal"]["change_percentage_points"],
            -4,
        )
        self.assertEqual(len(item["evidence"]), 2)

    def test_cpl_increase_requires_leads(self):
        cpl = evidence(
            "facebook_ads.cpl",
            130000,
            80000,
            unit="currency",
        )

        few = evidence(
            "facebook_ads.leads", 5, 20
        )

        result, _ = call("facebook_ads", {
            "facebook_ads.cpl": cpl,
            "facebook_ads.leads": few,
        })

        self.assertFalse(
            any(
                item["rule_id"] == "facebook_ads_cpl_up"
                for item in result["opportunities"]
            )
        )

        enough = evidence(
            "facebook_ads.leads", 30, 40
        )

        result, _ = call("facebook_ads", {
            "facebook_ads.cpl": cpl,
            "facebook_ads.leads": enough,
        })

        self.assertIn(
            "facebook_ads_cpl_up",
            [
                item["rule_id"]
                for item in result["opportunities"]
            ],
        )

    def test_wrong_asset_guard_is_rejected(self):
        result, _ = call("facebook_ads", {
            "facebook_ads.cpl": evidence(
                "facebook_ads.cpl",
                130000,
                80000,
                unit="currency",
            ),
            "facebook_ads.leads": evidence(
                "facebook_ads.leads",
                30,
                40,
                asset="asset-2",
            ),
        })

        self.assertFalse(
            any(
                item["rule_id"] == "facebook_ads_cpl_up"
                for item in result["opportunities"]
            )
        )

    def test_permission_rejected_before_read(self):
        with patch(
            "kdh.opportunity_engine.build_metric_evidence"
        ) as reader:
            with self.assertRaises(PermissionError):
                build_opportunities(
                    None,
                    client_id=CLIENT,
                    allowed_sources={"ga4"},
                    source="gsc",
                    start="2026-09-03",
                    end="2026-09-04",
                )

            reader.assert_not_called()

    def test_invalid_period_rejected(self):
        with self.assertRaises(ValueError):
            build_opportunities(
                None,
                client_id=CLIENT,
                allowed_sources={"gsc"},
                start="2026-09-04",
                end="2026-09-03",
            )

        with self.assertRaises(ValueError):
            build_opportunities(
                None,
                client_id=CLIENT,
                allowed_sources={"gsc"},
                start="2026-09-03",
                end="2026-09-04",
                compare_start="2026-09-02",
                compare_end="2026-09-03",
            )

    def test_previous_period_is_generated(self):
        result, _ = call("gsc")

        self.assertEqual(
            result["comparison_period"],
            PREVIOUS,
        )


if __name__ == "__main__":
    unittest.main()
