"""Incremental schema migrations shared by SQLite (local/demo) and PostgreSQL (production)."""
from __future__ import annotations

from datetime import datetime, timezone


MIGRATIONS = [
    (
        1,
        "reporting_platform_foundation",
        """
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    provider TEXT NOT NULL,
    external_account_id TEXT,
    account_name TEXT,
    account_email TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    secret_name TEXT UNIQUE,
    connected_at TEXT,
    last_sync_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(provider IN ('google','meta','tiktok','youtube','gmb','other')),
    CHECK(status IN ('pending','connected','disconnected','error'))
);

CREATE INDEX IF NOT EXISTS idx_connections_client_provider
ON connections(client_id, provider);

CREATE TABLE IF NOT EXISTS source_assets (
    id TEXT PRIMARY KEY,
    connection_id TEXT REFERENCES connections(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    provider TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    timezone TEXT,
    currency TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(client_id, provider, asset_type, external_id)
);

CREATE INDEX IF NOT EXISTS idx_source_assets_client_provider
ON source_assets(client_id, provider, enabled);

CREATE TABLE IF NOT EXISTS sync_runs (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    connection_id TEXT REFERENCES connections(id),
    asset_id TEXT REFERENCES source_assets(id),
    provider TEXT NOT NULL,
    sync_type TEXT NOT NULL,
    requested_start TEXT,
    requested_end TEXT,
    status TEXT NOT NULL,
    latest_available_date TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    fetched_at TEXT,
    error_code TEXT,
    error_message TEXT,
    warnings TEXT NOT NULL DEFAULT '[]',
    job_id TEXT REFERENCES jobs(id),
    created_at TEXT NOT NULL,
    CHECK(sync_type IN ('backfill','incremental','manual','validation')),
    CHECK(status IN ('queued','running','succeeded','partial','failed'))
);

CREATE INDEX IF NOT EXISTS idx_sync_runs_asset_created
ON sync_runs(asset_id, created_at);

CREATE INDEX IF NOT EXISTS idx_sync_runs_client_provider
ON sync_runs(client_id, provider, created_at);

CREATE TABLE IF NOT EXISTS sync_watermarks (
    asset_id TEXT PRIMARY KEY REFERENCES source_assets(id),
    last_complete_date TEXT,
    last_attempt_at TEXT,
    lookback_days INTEGER NOT NULL DEFAULT 3,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    id TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    asset_id TEXT NOT NULL REFERENCES source_assets(id),
    provider TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '',
    metric_date TEXT NOT NULL,
    dimension_key TEXT NOT NULL DEFAULT '',
    dimensions TEXT NOT NULL DEFAULT '{}',
    metrics TEXT NOT NULL,
    source_hash TEXT,
    sync_run_id TEXT REFERENCES sync_runs(id),
    fetched_at TEXT NOT NULL,
    UNIQUE(asset_id, entity_type, entity_id, metric_date, dimension_key)
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_client_date
ON daily_metrics(client_id, metric_date);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_provider_date
ON daily_metrics(provider, metric_date);

CREATE TABLE IF NOT EXISTS report_bundles (
    id TEXT PRIMARY KEY,
    bundle_key TEXT NOT NULL,
    revision INTEGER NOT NULL,
    parent_id TEXT REFERENCES report_bundles(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    compare_start_date TEXT,
    compare_end_date TEXT,
    default_section TEXT NOT NULL DEFAULT 'overview',
    schema_version TEXT NOT NULL DEFAULT '1.0',
    quality_status TEXT NOT NULL DEFAULT 'unknown',
    warnings TEXT NOT NULL DEFAULT '[]',
    branding TEXT NOT NULL DEFAULT '{}',
    created_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(bundle_key, revision),
    CHECK(status IN ('draft','provisional','final')),
    CHECK(quality_status IN ('unknown','complete','partial','failed'))
);

CREATE INDEX IF NOT EXISTS idx_report_bundles_client_period
ON report_bundles(client_id, start_date, end_date);

CREATE TABLE IF NOT EXISTS report_bundle_sections (
    bundle_id TEXT NOT NULL REFERENCES report_bundles(id),
    section_key TEXT NOT NULL,
    position INTEGER NOT NULL,
    dataset_id TEXT REFERENCES datasets(id),
    config TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(bundle_id, section_key)
);


""",
    ),
    (
        2,
        "report_bundle_snapshots",
        """
ALTER TABLE report_bundles ADD COLUMN snapshot_payload TEXT;
CREATE INDEX IF NOT EXISTS idx_report_bundles_published_revision
ON report_bundles(bundle_key, status, revision);
""",
    ),
    (
        3,
        "meta_oauth_states",
        """
CREATE TABLE IF NOT EXISTS meta_oauth_states (
    state TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(id),
    session_id TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed INTEGER NOT NULL DEFAULT 0
);
""",
    ),
    (
        4,
        "source_snapshots",
        """
CREATE TABLE IF NOT EXISTS source_snapshots (
    id TEXT PRIMARY KEY,
    sync_run_id TEXT NOT NULL UNIQUE REFERENCES sync_runs(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    asset_id TEXT NOT NULL REFERENCES source_assets(id),
    provider TEXT NOT NULL,
    source_key TEXT NOT NULL,
    requested_start TEXT,
    requested_end TEXT,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_client_source
ON source_snapshots(client_id, source_key, created_at);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_asset
ON source_snapshots(asset_id, created_at);
""",
    ),
    
    (
        5,
        "marketing_dataset_reviews",
        """
CREATE TABLE IF NOT EXISTS marketing_dataset_reviews (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    dataset_sha256 TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('needs_changes', 'approved_internal')
    ),
    note TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_marketing_reviews_dataset
ON marketing_dataset_reviews(dataset_id, created_at);
""",
    ),
    (
        6,
        "marketing_verified_releases",
        """
CREATE TABLE IF NOT EXISTS source_attestations (
    sync_run_id TEXT PRIMARY KEY REFERENCES sync_runs(id),
    claims TEXT NOT NULL,
    seal TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS marketing_release_approvals (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES datasets(id),
    origin_dataset_id TEXT NOT NULL REFERENCES datasets(id),
    client_id TEXT NOT NULL REFERENCES clients(id),
    reviewer_id TEXT NOT NULL REFERENCES users(id),
    internal_review_id TEXT NOT NULL REFERENCES marketing_dataset_reviews(id),
    dataset_sha256 TEXT NOT NULL,
    candidate_sha256 TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('release_approved','release_blocked')),
    note TEXT NOT NULL,
    checks TEXT NOT NULL,
    approved_opportunity_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_release_approvals_candidate
ON marketing_release_approvals(candidate_id, created_at);
CREATE TABLE IF NOT EXISTS marketing_release_snapshots (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id),
    candidate_id TEXT NOT NULL REFERENCES datasets(id),
    approval_id TEXT NOT NULL REFERENCES marketing_release_approvals(id),
    version INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_id, version)
);
""",
    ),
    (
        7,
        "report_viewer_grants",
        """
CREATE TABLE IF NOT EXISTS report_viewer_grants (
    report_id TEXT NOT NULL,
    client_id TEXT NOT NULL REFERENCES clients(id),
    user_id TEXT NOT NULL REFERENCES users(id),
    min_revision INTEGER NOT NULL DEFAULT 1 CHECK (min_revision>0),
    max_revision INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    granted_by TEXT NOT NULL REFERENCES users(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(report_id,user_id),
    CHECK (max_revision IS NULL OR max_revision>=min_revision)
);
""",
    ),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def apply_migrations(store) -> None:
    """Apply each migration exactly once.

    The existing SCHEMA remains the compatibility baseline. New platform tables
    are introduced here so future schema changes can be versioned safely.
    """
    with store.connect(immediate=True) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            int(row["version"])
            for row in db.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, name, script in MIGRATIONS:
            if version in applied:
                continue
            # sqlite3.executescript commits the current transaction first. Execute
            # these plain DDL statements individually to keep migration + version
            # registration atomic and serialized on both database backends.
            for statement in script.split(';'):
                if statement.strip():
                    db.execute(statement)
            db.execute(
                "INSERT INTO schema_migrations (version,name,applied_at) VALUES (?,?,?)",
                (version, name, _utc_now()),
            )

        timestamp = _utc_now()
        db.execute(
            """
            INSERT INTO clients (
                id,name,slug,timezone,active,created_at,updated_at
            )
            SELECT ?,?,?,?,?,?,?
            WHERE NOT EXISTS (SELECT 1 FROM clients WHERE id=?)
            """,
            (
                "client_kinderhealth",
                "KinderHealth",
                "kinderhealth",
                "Asia/Ho_Chi_Minh",
                1,
                timestamp,
                timestamp,
                "client_kinderhealth",
            ),
        )
