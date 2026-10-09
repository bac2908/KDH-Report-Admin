"""Local-only, deterministic bridge for KDH Marketing Data Pack v1.

Run inside Admin container:
    python -m kdh.manual_load_pack /demo-pack

This is a training-data importer, not real provider OAuth or API sync.
It does NOT delete or change the existing real client or real datasets.
"""
import hashlib
import json
import sys
from pathlib import Path

from .app import create_app
from .core import now, pack
from .platform_data import PlatformData
from .report_bundles import create_bundle, publish_provisional

CLIENT_ID = "client_kinderhealth_demo"
ORDER = ["overview", "seo", "facebook-ads", "facebook-content", "tiktok", "youtube", "gmb"]
PROVIDERS = {
    "summary": "other",
    "ga4": "google", "gsc": "google", "keywords": "google",
    "facebook_ads": "meta", "facebook_content": "meta",
    "tiktok_ads": "tiktok", "youtube": "youtube", "gmb": "gmb",
}


def prepare(root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("pack_id") != "kdh_marketing_data_pack_v1"
            or manifest.get("version") != "1.0.0"
            or manifest.get("client", {}).get("client_id") != CLIENT_ID):
        raise SystemExit("STOP: Data Pack ID/version/client is not supported")

    datasets = []
    for section in ORDER:
        file = root / "data" / "snapshots" / f"admin_dataset_{section}.json"
        data = json.loads(file.read_text(encoding="utf-8"))
        p = data["params"]
        if (data.get("client_id") != CLIENT_ID or p.get("client_id") != CLIENT_ID
                or p.get("report_type") != section or p.get("demo") is not True
                or p.get("start") != "2026-04-04" or p.get("end") != "2026-09-30"):
            raise SystemExit(f"STOP: invalid demo dataset metadata in {file}")
        for key, src in data["sources"].items():
            if (key not in PROVIDERS or src.get("demo") is not True
                    or src.get("source_mode") != "demo"
                    or src.get("data_origin") != "simulated"
                    or src.get("status") != "ready"
                    or src.get("requested_start") != p["start"]
                    or src.get("requested_end") != p["end"]):
                raise SystemExit(f"STOP: source not marked simulated demo: {section}/{key}")
        datasets.append(data)
    return datasets


def main():
    root = Path(sys.argv[1]) if len(sys.argv) == 2 else Path("/demo-pack")
    if not root.is_dir():
        raise SystemExit(f"Cannot find Data Pack directory: {root}")
    datasets = prepare(root)
    app = create_app()
    store = app.extensions["store"]
    admin = store.one("SELECT id FROM users WHERE role='admin' AND active=1 ORDER BY created_at LIMIT 1")
    if not admin:
        raise SystemExit("Create/login an Admin account before running this script")
    actor = admin["id"]
    stamp = now()
    store.execute("""INSERT INTO clients (id,name,slug,timezone,active,created_at,updated_at)
                     VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                  (CLIENT_ID, "KinderHealth DEMO - KHONG PHAI DU LIEU THAT",
                   "kinderhealth-demo", "Asia/Ho_Chi_Minh", 1, stamp, stamp))
    platform = PlatformData(store)
    seen = set()

    for section, data in zip(ORDER, datasets):
        for key, src in data["sources"].items():
            if key in seen:
                continue
            seen.add(key)
            provider = PROVIDERS[key]
            connection_id = platform.upsert_connection(
                client_id=CLIENT_ID, provider=provider,
                external_account_id="DEMO:KDH-PACK-v1",
                account_name=f"DEMO ONLY - {provider.upper()} (NO OAUTH)",
                status="connected", secret_name=None)
            asset_id = platform.upsert_asset(
                client_id=CLIENT_ID, provider=provider,
                asset_type="demo_report_source", external_id=f"DEMO:{key}:v1",
                name=f"DEMO ONLY - {key}", connection_id=connection_id,
                timezone="Asia/Ho_Chi_Minh", currency="VND",
                metadata={"mode": "demo", "data_origin": "simulated", "source_key": key})
            already = store.one("""SELECT r.id FROM source_snapshots s
                                   JOIN sync_runs r ON r.id=s.sync_run_id
                                   WHERE s.client_id=? AND s.source_key=?
                                   AND s.requested_start=? AND s.requested_end=?
                                   AND r.status='succeeded' LIMIT 1""",
                                (CLIENT_ID, key, data["params"]["start"], data["params"]["end"]))
            if already:
                print(f"SYNC SKIP {key}: already imported", flush=True)
                continue
            sync_id = platform.start_sync(
                client_id=CLIENT_ID, provider=provider, sync_type="manual",
                requested_start=data["params"]["start"],
                requested_end=data["params"]["end"],
                connection_id=connection_id, asset_id=asset_id)
            try:
                daily = src.get("daily", [])
                if not isinstance(daily, list):
                    daily = []
                for row in daily:
                    if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                        continue
                    metrics = {k: v for k, v in row.items()
                               if k != "date" and isinstance(v, (int, float)) and not isinstance(v, bool)}
                    if metrics:
                        platform.upsert_daily_metric(
                            client_id=CLIENT_ID, asset_id=asset_id,
                            provider=provider, entity_type=key + "_daily_total",
                            entity_id="DEMO-AGGREGATE", metric_date=row["date"],
                            metrics=metrics, dimensions={"demo": True, "source_key": key},
                            source_hash=hashlib.sha256(pack(row).encode("utf-8")).hexdigest(),
                            sync_run_id=sync_id)
                platform.save_source_snapshot(
                    sync_run_id=sync_id, client_id=CLIENT_ID, asset_id=asset_id,
                    provider=provider, source_key=key,
                    requested_start=data["params"]["start"],
                    requested_end=data["params"]["end"], payload=src)
                count = len(daily) or len(src.get("entries", [])) or len(src.get("posts", [])) or 1
                platform.finish_sync(sync_id, status="succeeded",
                                     latest_available_date=src["latest_available_date"],
                                     record_count=count, warnings=["DEMO - simulated, NOT customer data"])
                print(f"SYNC OK   {key}: {count} records", flush=True)
            except Exception:
                platform.finish_sync(sync_id, status="failed",
                                     error_code="demo_import_error",
                                     error_message="Manual Data Pack import failed")
                raise

    for data in datasets:
        ds_id = data["id"]
        existing = store.one("SELECT id,data FROM datasets WHERE id=?", (ds_id,))
        if existing:
            if json.loads(existing["data"]) != data:
                raise SystemExit(f"STOP: dataset ID collision / changed fixture: {ds_id}")
            print(f"DATASET SKIP {data['params']['report_type']}", flush=True)
            continue
        store.execute("""INSERT INTO datasets (id,user_id,report_type,created_at,valid,data)
                         VALUES (?,?,?,?,?,?)""",
                      (ds_id, actor, data["params"]["report_type"],
                       data["created_at"], 1, pack(data)))
        print(f"DATASET OK   {data['params']['report_type']} {ds_id}", flush=True)

    name = "KDH DATA PACK v1 - 180 DAYS - DEMO ONLY"
    prior = store.one("""SELECT bundle_key,revision,status FROM report_bundles
                         WHERE client_id=? AND name=? ORDER BY revision DESC LIMIT 1""",
                      (CLIENT_ID, name))
    if prior:
        result = {"report_id": prior["bundle_key"], "revision": prior["revision"],
                  "status": prior["status"]}
        if prior["status"] == "draft":
            result = publish_provisional(store, actor, prior["bundle_key"], prior["revision"])
        print("BUNDLE ALREADY EXISTS", flush=True)
    else:
        p = datasets[0]["params"]
        draft = create_bundle(store, actor, {
            "client_id": CLIENT_ID, "name": name,
            "start_date": p["start"], "end_date": p["end"],
            "compare_start_date": p["previous_start"],
            "compare_end_date": p["previous_end"],
            "default_section": "overview",
            "branding": {"demo": True, "watermark": "DEMO / SIMULATED - NOT REAL RESULTS"},
            "sections": [{"key": key, "dataset_id": data["id"]}
                         for key, data in zip(ORDER, datasets)],
        })
        result = publish_provisional(store, actor, draft["report_id"], 1)
        print("BUNDLE CREATED + PUBLISHED PROVISIONAL", flush=True)
    print("\n" + "=" * 62, flush=True)
    print("REPORT_ID = " + result["report_id"], flush=True)
    print("REVISION  = " + str(result["revision"]), flush=True)
    print("STATUS    = " + result["status"], flush=True)
    print("== COPY REPORT_ID FOR KDH-REPORT-NEW ==", flush=True)


if __name__ == "__main__":
    main()
