
"""Step 8.8.1 tests: preview without real provider data."""

import unittest
from unittest.mock import patch

from kdh.marketing_preview import build_marketing_preview


CLIENT = "client_kinderhealth"


def fake_evidence(
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

    return {
        "evidence_id": "evidence-" + metric_id,
        "metric": {"id": metric_id},
        "scope": {
            "asset_id": "asset-1",
            "client_id": client_id,
        },
        "result": {
            "status": "no_data",
            "evidence_status": "not_ready",
            "value": None,
        },
        "quality": {
            "data_origin": "persisted_unverified",
            "is_demo": None,
            "warnings": [],
        },
        "lineage": {
            "sync_run_ids": [],
        },
    }


class MarketingPreviewTests(unittest.TestCase):

    def build(self, **kwargs):
        options = {
            "client_id": CLIENT,
            "allowed_sources": {"gsc"},
            "start": "2026-09-10",
            "end": "2026-09-12",
            "source": "gsc",
        }

        options.update(kwargs)

        return build_marketing_preview(
            None, **options
        )

    def test_empty_data_is_not_publishable(self):
        with (
            patch(
                "kdh.marketing_preview.build_metric_evidence",
                side_effect=fake_evidence,
            ),
            patch(
                "kdh.marketing_preview.build_opportunities",
                return_value={"opportunities": []},
            ),
        ):
            result = self.build()

        self.assertFalse(result["publishable"])
        self.assertTrue(result["not_a_report_bundle"])

        self.assertEqual(
            result["quality"]["status"],
            "no_eligible_data",
        )

        self.assertEqual(
            result["summary"]["widgets_with_values"],
            0,
        )

        self.assertEqual(
            result["evidence_cards"], []
        )

        self.assertEqual(
            result["comparison"],
            {
                "start": "2026-09-07",
                "end": "2026-09-09",
            },
        )

    def test_unverified_metric_remains_internal(self):

        def reader(*args, **kwargs):
            result = fake_evidence(
                *args, **kwargs
            )

            if kwargs["metric_id"] == "gsc.clicks":
                result["result"] = {
                    "status": "available",
                    "evidence_status": "recorded_unverified",
                    "value": 500,
                }

            return result

        with (
            patch(
                "kdh.marketing_preview.build_metric_evidence",
                side_effect=reader,
            ),
            patch(
                "kdh.marketing_preview.build_opportunities",
                return_value={"opportunities": []},
            ),
        ):
            result = self.build()

        card = next(
            item for item in result["widgets"]
            if item["metric_id"] == "gsc.clicks"
        )

        self.assertEqual(card["value"], 500)
        self.assertFalse(card["verified"])
        self.assertFalse(card["publishable"])

        self.assertEqual(
            result["summary"]["evidence_count"],
            1,
        )

        self.assertFalse(result["publishable"])

    def test_demo_cannot_become_an_evidence_claim(self):

        def reader(*args, **kwargs):
            result = fake_evidence(
                *args, **kwargs
            )

            result["result"] = {
                "status": "available",
                "evidence_status": "recorded_unverified",
                "value": 1000,
            }

            result["quality"]["is_demo"] = True

            return result

        with (
            patch(
                "kdh.marketing_preview.build_metric_evidence",
                side_effect=reader,
            ),
            patch(
                "kdh.marketing_preview.build_opportunities",
                return_value={"opportunities": []},
            ),
        ):
            result = self.build()

        self.assertEqual(
            result["summary"]["widgets_with_values"],
            0,
        )

        self.assertEqual(result["evidence_cards"], [])

    def test_source_permission_checked_before_read(self):
        with patch(
            "kdh.marketing_preview.build_metric_evidence"
        ) as reader:

            with self.assertRaises(PermissionError):
                self.build(
                    allowed_sources={"ga4"},
                )

            reader.assert_not_called()

    def test_invalid_comparison_rejected(self):
        with self.assertRaises(ValueError):
            self.build(
                compare_start="2026-09-08",
                compare_end="2026-09-09",
                allowed_sources={"gsc"},
            )

    def test_asset_requires_source(self):
        with self.assertRaises(ValueError):
            self.build(
                source=None,
                asset_id="asset-1",
            )

    def test_opportunities_always_require_review(self):
        raw = {
            "id": "sample",
            "rule_id": "gsc_clicks_down",
            "source": "gsc",
            "title": "Investigate organic traffic",
            "signal": {"change_percent": -25},
            "evidence": [],
            "suggested_action": "Review queries",
            "publishable": True,
        }

        with (
            patch(
                "kdh.marketing_preview.build_metric_evidence",
                side_effect=fake_evidence,
            ),
            patch(
                "kdh.marketing_preview.build_opportunities",
                return_value={"opportunities": [raw]},
            ),
        ):
            result = self.build()

        candidate = result[
            "opportunity_candidates"
        ][0]

        self.assertFalse(candidate["publishable"])
        self.assertTrue(candidate["review_required"])
        self.assertEqual(
            candidate["status"],
            "candidate_unverified",
        )


if __name__ == "__main__":
    unittest.main()
