
"""Step 8.5 tests. No real database or provider calls."""

import unittest
from unittest.mock import patch

from kdh.metric_calculator import (
    calculate_metric,
    compare_calculated_periods,
)


class MetricCalculatorTests(unittest.TestCase):

    PERIOD = {
        "start": "2026-09-01",
        "end": "2026-09-02",
    }

    def item(
        self,
        metric_id,
        value,
        *,
        status="available",
        asset="asset-1",
        currency="VND",
        days=2,
    ):
        return {
            "metric_id": metric_id,
            "status": status,
            "client_id": "client_kinderhealth",
            "asset_id": asset,
            "currency": currency,
            "period": dict(self.PERIOD),
            "data_origin": "persisted_unverified",
            "summary": {
                "value": value,
                "coverage_days": days,
                "expected_days": 2,
            },
            "series": [{
                "date": "2026-09-01",
                "sync_run_id": "test-run",
            }],
        }

    def calc(self, metric_id, values):
        data = {
            name: self.item(name, value)
            for name, value in values.items()
        }

        with patch(
            "kdh.metric_calculator.read_metric_series",
            side_effect=lambda _, **kw: data[kw["metric_id"]],
        ):
            return calculate_metric(
                None,
                metric_id=metric_id,
                client_id="client_kinderhealth",
                allowed_sources={metric_id.split(".")[0]},
                start="2026-09-01",
                end="2026-09-02",
            )

    def test_cpl_and_currency(self):
        r = self.calc("facebook_ads.cpl", {
            "facebook_ads.spend": 5000000,
            "facebook_ads.leads": 100,
        })
        self.assertEqual(r["status"], "available")
        self.assertEqual(r["value"], 50000)
        self.assertEqual(r["currency"], "VND")
        self.assertFalse(r["verified_provider"])

    def test_derived_metric(self):
        r = self.calc("facebook_ads.calculated_cpl", {
            "facebook_ads.spend": 5000000,
            "facebook_ads.leads": 100,
        })
        self.assertEqual(r["value"], 50000)

    def test_ctr_returns_fraction(self):
        r = self.calc("gsc.ctr", {
            "gsc.clicks": 50,
            "gsc.impressions": 1000,
        })
        self.assertAlmostEqual(r["value"], 0.05)
        self.assertEqual(
            r["formula"]["ratio_convention"],
            "fraction",
        )

    def test_cpm_and_roas(self):
        cpm = self.calc("facebook_ads.cpm", {
            "facebook_ads.spend": 7000,
            "facebook_ads.impressions": 2000,
        })
        self.assertEqual(cpm["value"], 3500)

        roas = self.calc("google_ads.roas", {
            "google_ads.conversion_value": 250000,
            "google_ads.spend": 100000,
        })
        self.assertEqual(roas["value"], 2.5)

    def test_zero_denominator(self):
        r = self.calc("facebook_ads.cpl", {
            "facebook_ads.spend": 1000000,
            "facebook_ads.leads": 0,
        })
        self.assertEqual(r["status"], "division_by_zero")
        self.assertIsNone(r["value"])

    def test_partial_stale_rejected(self):
        data = {
            "facebook_ads.spend": self.item(
                "facebook_ads.spend",
                5000000,
                status="stale",
            ),
            "facebook_ads.leads": self.item(
                "facebook_ads.leads", 100
            ),
        }

        with patch(
            "kdh.metric_calculator.read_metric_series",
            side_effect=lambda _, **kw: data[kw["metric_id"]],
        ):
            r = calculate_metric(
                None,
                metric_id="facebook_ads.cpl",
                client_id="client_kinderhealth",
                allowed_sources={"facebook_ads"},
                start="2026-09-01",
                end="2026-09-02",
            )

        self.assertEqual(r["status"], "insufficient_data")
        self.assertIsNone(r["value"])

    def test_wrong_asset_rejected(self):
        data = {
            "facebook_ads.spend": self.item(
                "facebook_ads.spend", 5000000, asset="a"
            ),
            "facebook_ads.leads": self.item(
                "facebook_ads.leads", 100, asset="b"
            ),
        }

        with patch(
            "kdh.metric_calculator.read_metric_series",
            side_effect=lambda _, **kw: data[kw["metric_id"]],
        ):
            r = calculate_metric(
                None,
                metric_id="facebook_ads.cpl",
                client_id="client_kinderhealth",
                allowed_sources={"facebook_ads"},
                start="2026-09-01",
                end="2026-09-02",
            )

        self.assertEqual(r["status"], "incompatible_scope")

    def test_distinct_metric_is_unsupported(self):
        r = calculate_metric(
            None,
            metric_id="crm.lead_to_customer_rate",
            client_id="client_kinderhealth",
            allowed_sources={"crm"},
            start="2026-09-01",
            end="2026-09-02",
        )
        self.assertEqual(r["status"], "unsupported")
        self.assertIsNone(r["value"])

    def test_permission_and_dates(self):
        with self.assertRaises(PermissionError):
            calculate_metric(
                None,
                metric_id="gsc.ctr",
                client_id="client_kinderhealth",
                allowed_sources={"ga4"},
                start="2026-09-01",
                end="2026-09-02",
            )

        with self.assertRaises(ValueError):
            calculate_metric(
                None,
                metric_id="gsc.ctr",
                client_id="client_kinderhealth",
                allowed_sources={"gsc"},
                start="2026-09-03",
                end="2026-09-01",
            )

    def test_compare_percentage_points(self):
        current = {
            "metric_id": "gsc.ctr",
            "status": "available",
            "value": 0.15,
            "source": "gsc",
            "unit": "ratio",
            "client_id": "client_kinderhealth",
            "asset_id": "a",
            "currency": None,
            "data_origin": "persisted_unverified",
            "period": {
                "start": "2026-09-03",
                "end": "2026-09-04",
            },
        }

        previous = {
            **current,
            "value": 0.10,
            "period": dict(self.PERIOD),
        }

        result = compare_calculated_periods(
            current, previous
        )

        self.assertEqual(result["status"], "available")
        self.assertAlmostEqual(
            result["change_percentage_points"], 5
        )
        self.assertIsNone(result["change_percent"])


if __name__ == "__main__":
    unittest.main()
