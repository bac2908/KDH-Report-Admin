import json
import os
import tempfile
import unittest
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from unittest.mock import patch

from kdh.core import Store
from kdh.platform_data import DEFAULT_CLIENT_ID, PlatformData
from kdh.migrations import MIGRATIONS, apply_migrations


class PlatformDataTests(unittest.TestCase):
    def test_upgrade_from_v1_preserves_existing_data_and_does_not_reapply(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('kdh.migrations.MIGRATIONS',MIGRATIONS[:1]):
                old=Store(folder)
                old.execute('''INSERT INTO report_bundles
                    (id,bundle_key,revision,client_id,name,status,start_date,end_date,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',('old-row','rpt_existing',1,DEFAULT_CLIENT_ID,'Old final','final','2026-09-01','2026-09-28','2026-10-01T00:00:00Z'))
                old.execute('INSERT INTO settings (key,value) VALUES (?,?)',('migration_sentinel','"keep-me"'))
                before=old.one('SELECT * FROM report_bundles WHERE id=?',('old-row',))
            upgraded=Store(folder)
            after=upgraded.one('SELECT * FROM report_bundles WHERE id=?',('old-row',))
            self.assertIsNone(after.pop('snapshot_payload'))
            self.assertEqual(after,before)
            self.assertEqual(upgraded.setting('migration_sentinel'),'keep-me')
            Store(folder)
            self.assertEqual(upgraded.one('SELECT COUNT(*) AS n FROM schema_migrations')['n'],len(MIGRATIONS))

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

    def snapshot_args(self):
        connection_id = self.platform.upsert_connection(
            client_id=DEFAULT_CLIENT_ID, provider="google", external_account_id="snapshot-test",
        )
        asset_id = self.platform.upsert_asset(
            client_id=DEFAULT_CLIENT_ID, provider="google", asset_type="ga4_property",
            external_id="snapshot-property", name="Snapshot test", connection_id=connection_id,
        )
        sync_id = self.platform.start_sync(
            client_id=DEFAULT_CLIENT_ID, provider="google", sync_type="manual",
            requested_start="2026-09-01", requested_end="2026-09-03",
            connection_id=connection_id, asset_id=asset_id,
        )
        return dict(sync_run_id=sync_id, client_id=DEFAULT_CLIENT_ID, asset_id=asset_id,
                    provider="google", source_key="ga4", requested_start="2026-09-01",
                    requested_end="2026-09-03")

    def test_source_snapshot_upsert_retains_id_and_exact_payload(self):
        args = self.snapshot_args()
        before = {"status": "ready", "totals": {"sessions": 1}, "daily": []}
        first = self.platform.save_source_snapshot(**args, payload=before)
        created_at = self.store.one("SELECT created_at FROM source_snapshots WHERE id=?", (first,))["created_at"]
        after = {"status": "ready", "totals": {"sessions": 2, "missing": None},
                 "daily": [], "pages": [{"path": "/khám-nhi", "views": 0}]}
        second = self.platform.save_source_snapshot(**args, payload=after)
        rows = self.store.all("SELECT * FROM source_snapshots WHERE sync_run_id=?", (args["sync_run_id"],))
        self.assertEqual(len(rows), 1)
        self.assertEqual(first, second)
        self.assertEqual(second, rows[0]["id"])
        self.assertEqual(rows[0]["created_at"], created_at)
        self.assertEqual(json.loads(rows[0]["payload"]), after)
        for key, value in args.items():
            self.assertEqual(rows[0][key], value)

    def test_source_snapshot_rejects_credentials_without_overwriting_saved_data(self):
        args = self.snapshot_args()
        clean = {"totals": {"sessions": 1}, "status": "ready"}
        snapshot_id = self.platform.save_source_snapshot(**args, payload=clean)
        for unsafe in (
            {"access_token": "test-sensitive"}, {"nested": [{"client_secret": "test-sensitive"}]},
            {"headers": {"Authorization": "Bearer test-sensitive"}},
            {"url": "https://example.test/?api_key=test-sensitive"},
            {"value": "Bearer test-sensitive"},
        ):
            with self.subTest(fields=list(unsafe)):
                with self.assertRaises(ValueError) as error:
                    self.platform.save_source_snapshot(**args, payload=unsafe)
                self.assertNotIn("test-sensitive", str(error.exception))
        row = self.store.one("SELECT payload FROM source_snapshots WHERE id=?", (snapshot_id,))
        self.assertEqual(json.loads(row["payload"]), clean)

    def test_migration_four_is_idempotent_and_preserves_snapshots(self):
        self.assertEqual([m[0] for m in MIGRATIONS], [1, 2, 3, 4, 5, 6, 7])
        args = self.snapshot_args()
        self.platform.save_source_snapshot(**args, payload={"totals": {}, "status": "empty"})
        before = self.store.all("SELECT * FROM source_snapshots")
        apply_migrations(self.store)
        apply_migrations(self.store)
        self.assertEqual(self.store.all("SELECT * FROM source_snapshots"), before)
        self.assertEqual(self.store.one("SELECT COUNT(*) AS n FROM schema_migrations WHERE version=4")["n"], 1)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Requires an isolated PostgreSQL test database")
class PostgresPlatformDataTests(PlatformDataTests):
    def setUp(self):
        import psycopg
        from psycopg import sql

        url = os.environ["TEST_DATABASE_URL"]
        schema = "kdh_snapshot_test_" + uuid4().hex
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

        def cleanup():
            with psycopg.connect(url, autocommit=True) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

        self.addCleanup(cleanup)
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query))
        query["options"] = "-csearch_path=" + schema
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name, urlunsplit(parts._replace(query=urlencode(query))))
        self.platform = PlatformData(self.store)


if __name__ == "__main__":
    unittest.main()
