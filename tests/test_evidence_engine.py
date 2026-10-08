
"""Step 8.6 tests: isolated data, no provider calls."""

import unittest
from unittest.mock import patch

from kdh.evidence_engine import build_metric_evidence


CLIENT = "client_kinderhealth"


def stored(
    metric_id,
    value=30,
    *,
    status="available",
    asset="asset-1",
    period="current",
):
    day = (
        "2026-09-03"
        if period == "current"
        else "2026-09-01"
    )

    return {
        "metric_id": metric_id,
        "status": status,
        "client_id": CLIENT,
        "asset_id": asset,
        "currency": None,
        "data_origin": "persisted_unverified",
        "summary": {
            "value": value,
            "coverage_days": 2,
            "expected_days": 2,
        },
        "series": [
            {
                "date": day,
                "value": 10,
                "sync_run_id": "run-1",
                "fetched_at": "2026-09-05T00:00:00Z",
            }
        ],
        "freshness": {
            "latest_sync_status": "succeeded",
            "latest_available_date": "2026-09-04",
        },
        "warnings": [],
    }


class EvidenceEngineTests(unittest.TestCase):

    def evidence(self, metric_id="gsc.clicks", **opts):
        return build_metric_evidence(
            None,
            metric_id=metric_id,
            client_id=CLIENT,
            allowed_sources={
                metric_id.split(".")[0]
            },
            start="2026-09-03",
            end="2026-09-04",
            **opts,
        )

    def test_recorded_metric_has_lineage(self):
        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=stored("gsc.clicks"),
        ):
            result = self.evidence()

        self.assertEqual(
            result["result"]["value"], 30
        )
        self.assertEqual(
            result["result"]["evidence_status"],
            "recorded_unverified",
        )
        self.assertEqual(
            result["lineage"]["sync_run_ids"],
            ["run-1"],
        )
        self.assertEqual(
            result["source"]["provider"], "google"
        )
        self.assertFalse(
            result["quality"]["independently_verified"]
        )
        self.assertIsNone(result["claim_text"])

    def test_failed_sync_does_not_claim_success(self):
        data = stored("gsc.clicks", status="stale")

        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=data,
        ):
            result = self.evidence()

        self.assertIsNone(
            result["result"]["value"]
        )
        self.assertEqual(
            result["result"]["evidence_status"],
            "not_ready",
        )
        self.assertEqual(
            result["result"]["status"], "stale"
        )

    def test_non_additive_keeps_daily_observations(self):
        data = stored("gsc.position", None)

        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=data,
        ):
            result = self.evidence("gsc.position")

        self.assertEqual(
            result["result"]["evidence_status"],
            "observations_only",
        )
        self.assertIsNone(
            result["result"]["value"]
        )
        self.assertEqual(
            len(result["result"]["daily_observations"]),
            1,
        )

    def test_missing_lineage_is_not_evidence(self):
        data = stored("gsc.clicks")
        data["series"][0].pop("sync_run_id")

        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=data,
        ):
            result = self.evidence()

        self.assertEqual(
            result["result"]["evidence_status"],
            "not_ready",
        )
        self.assertIsNone(
            result["result"]["value"]
        )

    def test_demo_origin_is_not_accepted(self):
        data = stored("gsc.clicks")
        data["data_origin"] = "demo"

        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=data,
        ):
            result = self.evidence()

        self.assertEqual(
            result["result"]["evidence_status"],
            "not_ready",
        )
        self.assertIsNone(
            result["result"]["value"]
        )

    def test_incomplete_coverage_rejected(self):
        data = stored("gsc.clicks")
        data["summary"]["coverage_days"] = 1

        with patch(
            "kdh.evidence_engine.read_metric_series",
            return_value=data,
        ):
            result = self.evidence()

        self.assertEqual(
            result["result"]["evidence_status"],
            "not_ready",
        )
        self.assertIsNone(
            result["result"]["value"]
        )

    def test_calculated_kpi_uses_operand_lineage(self):
        calculated = {
            "status": "available",
            "value": 50000,
            "asset_id": "meta-1",
            "currency": "VND",
            "data_origin": "persisted_unverified",
            "operands": [
                {"sync_run_ids": ["run-spend"]},
                {"sync_run_ids": ["run-leads"]},
            ],
            "warnings": [],
        }

        with patch(
            "kdh.evidence_engine.calculate_metric",
            return_value=calculated,
        ):
            result = self.evidence(
                "facebook_ads.cpl"
            )

        self.assertEqual(
            result["result"]["value"], 50000
        )
        self.assertEqual(
            result["lineage"]["sync_run_count"], 2
        )
        self.assertEqual(
            result["source"]["provider"], "meta"
        )
        self.assertFalse(
            result["quality"][
                "ready_as_verified_client_claim"
            ]
        )

    def test_compare_two_valid_periods(self):

        def fake_read(_, **kwargs):
            is_current = (
                kwargs["start"] == "2026-09-03"
            )

            return stored(
                "gsc.clicks",
                30 if is_current else 20,
                period=(
                    "current"
                    if is_current
                    else "previous"
                ),
            )

        with patch(
            "kdh.evidence_engine.read_metric_series",
            side_effect=fake_read,
        ):
            result = self.evidence(
                compare_start="2026-09-01",
                compare_end="2026-09-02",
            )

        comparison = result["comparison"]

        self.assertEqual(
            comparison["status"], "available"
        )
        self.assertEqual(
            comparison["previous_value"], 20
        )
        self.assertEqual(
            comparison["delta"], 10
        )
        self.assertEqual(
            comparison["change_percent"], 50
        )

    def test_different_assets_cannot_be_compared(self):

        def fake_read(_, **kwargs):
            current = (
                kwargs["start"] == "2026-09-03"
            )

            return stored(
                "gsc.clicks",
                30,
                asset="a" if current else "b",
            )

        with patch(
            "kdh.evidence_engine.read_metric_series",
            side_effect=fake_read,
        ):
            result = self.evidence(
                compare_start="2026-09-01",
                compare_end="2026-09-02",
            )

        self.assertEqual(
            result["comparison"]["status"],
            "incompatible_scope",
        )
        self.assertIsNone(
            result["comparison"]["previous_value"]
        )

    def test_unauthorized_source_rejected(self):
        with patch(
            "kdh.evidence_engine.read_metric_series"
        ) as reader:

            with self.assertRaises(PermissionError):
                build_metric_evidence(
                    None,
                    metric_id="gsc.clicks",
                    client_id=CLIENT,
                    allowed_sources={"ga4"},
                    start="2026-09-03",
                    end="2026-09-04",
                )

            reader.assert_not_called()

    def test_invalid_comparison_rejected(self):
        with patch(
            "kdh.evidence_engine.read_metric_series"
        ) as reader:

            with self.assertRaises(ValueError):
                self.evidence(
                    compare_start="2026-09-02",
                    compare_end="2026-09-03",
                )

            reader.assert_not_called()

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError):
            self.evidence("gsc.never_exists")


if __name__ == "__main__":
    unittest.main()
