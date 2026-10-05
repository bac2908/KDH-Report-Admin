import json
import tempfile
import unittest

from kdh.core import Store
from kdh.platform_data import DEFAULT_CLIENT_ID, PlatformData


class PlatformDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.platform = PlatformData(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def test_platform_schema_and_default_client(self):
        client = self.platform.client(DEFAULT_CLIENT_ID)
        self.assertIsNotNone(client)
        self.assertEqual(client["name"], "KinderHealth")
        self.assertEqual(client["slug"], "kinderhealth")

        migration = self.store.one(
            "SELECT version,name FROM schema_migrations WHERE version=1"
        )
        self.assertEqual(migration["name"], "reporting_platform_foundation")

    def test_connection_asset_sync_and_metric_upsert(self):
        connection_id = self.platform.upsert_connection(
            client_id=DEFAULT_CLIENT_ID,
            provider="meta",
            external_account_id="business-1",
            account_name="KinderHealth Meta",
            status="connected",
            secret_name="meta:client_kinderhealth:business-1",
        )
        asset_id = self.platform.upsert_asset(
            client_id=DEFAULT_CLIENT_ID,
            provider="meta",
            asset_type="facebook_page",
            external_id="page-1",
            name="KinderHealth",
            connection_id=connection_id,
            timezone="Asia/Ho_Chi_Minh",
        )

        sync_id = self.platform.start_sync(
            client_id=DEFAULT_CLIENT_ID,
            provider="meta",
            sync_type="manual",
            requested_start="2026-10-01",
            requested_end="2026-10-05",
            connection_id=connection_id,
            asset_id=asset_id,
        )

        first_id = self.platform.upsert_daily_metric(
            client_id=DEFAULT_CLIENT_ID,
            asset_id=asset_id,
            provider="meta",
            entity_type="page",
            metric_date="2026-10-01",
            metrics={"reach": 100, "views": 150},
            sync_run_id=sync_id,
        )
        second_id = self.platform.upsert_daily_metric(
            client_id=DEFAULT_CLIENT_ID,
            asset_id=asset_id,
            provider="meta",
            entity_type="page",
            metric_date="2026-10-01",
            metrics={"reach": 120, "views": 180},
            sync_run_id=sync_id,
        )
        self.assertEqual(first_id, second_id)

        self.platform.finish_sync(
            sync_id,
            status="succeeded",
            latest_available_date="2026-10-01",
            record_count=1,
        )

        row = self.store.one(
            "SELECT metrics FROM daily_metrics WHERE id=?", (first_id,)
        )
        self.assertEqual(json.loads(row["metrics"])["reach"], 120)

        watermark = self.store.one(
            "SELECT * FROM sync_watermarks WHERE asset_id=?", (asset_id,)
        )
        self.assertEqual(watermark["last_complete_date"], "2026-10-01")

        connection = self.store.one(
            "SELECT * FROM connections WHERE id=?", (connection_id,)
        )
        self.assertIsNotNone(connection["last_sync_at"])


if __name__ == "__main__":
    unittest.main()
