
"""Step 8.2 Metric Catalog tests."""

import unittest

from kdh.metric_catalog import (
    CATALOG_VERSION,
    EVIDENCE_CONTRACT,
    METRICS,
    SOURCES,
    get_catalog,
    get_metric,
    list_metrics,
    validate_catalog,
)


class MetricCatalogTests(unittest.TestCase):

    def test_valid_catalog_and_platform_coverage(self):
        self.assertGreaterEqual(validate_catalog(), 150)
        self.assertEqual(len(SOURCES), 12)

        for source in SOURCES:
            self.assertTrue(list_metrics(source), source)

    def test_source_fields_match_google_storage(self):
        metric_ids = (
            "ga4.sessions",
            "ga4.active_users",
            "ga4.page_views",
            "ga4.engagement_rate",
            "gsc.clicks",
            "gsc.impressions",
            "gsc.ctr",
            "gsc.position",
        )

        for metric_id in metric_ids:
            metric = get_metric(metric_id)

            self.assertIsNotNone(metric, metric_id)
            self.assertEqual(metric["kind"], "source")

    def test_planned_integrations_not_marked_available(self):
        planned_sources = (
            "google_ads",
            "tiktok_ads",
            "tiktok_organic",
            "youtube",
            "crm",
        )

        for source in planned_sources:
            self.assertEqual(
                SOURCES[source]["integration"],
                "planned",
            )

        self.assertEqual(
            SOURCES["gmb"]["integration"],
            "csv_only",
        )

    def test_derived_metrics_have_valid_operands(self):
        derived = list_metrics(kind="derived")

        self.assertGreaterEqual(len(derived), 10)

        for metric in derived:
            self.assertEqual(
                metric["operation"],
                "divide",
            )

            self.assertEqual(
                len(metric["requires"]),
                2,
            )

            self.assertTrue(
                all(
                    dependency in METRICS
                    for dependency in metric["requires"]
                )
            )

    def test_catalog_returns_defensive_copies(self):
        self.assertEqual(
            list_metrics("unknown"),
            [],
        )

        self.assertIsNone(
            get_metric("does_not_exist")
        )

        original = get_metric("ga4.sessions")["label"]

        modified = get_metric("ga4.sessions")
        modified["label"] = "changed"

        self.assertEqual(
            get_metric("ga4.sessions")["label"],
            original,
        )

    def test_api_ready_catalog_contract(self):
        catalog = get_catalog()

        self.assertEqual(
            catalog["version"],
            CATALOG_VERSION,
        )

        self.assertIn(
            "sync_run_id",
            EVIDENCE_CONTRACT["lineage"],
        )

        self.assertIn(
            "is_demo",
            EVIDENCE_CONTRACT["quality"],
        )

        self.assertEqual(
            len(catalog["metrics"]),
            len(METRICS),
        )


if __name__ == "__main__":
    unittest.main()
