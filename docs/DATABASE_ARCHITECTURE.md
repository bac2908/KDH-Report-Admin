# Database architecture

## Decision

- **Current Compose configuration:** PostgreSQL 16 in service `postgres`, persisted in `postgres-data`; Admin receives `DATABASE_URL` and a stable `ENCRYPTION_KEY` through its environment.
- **Local development without DATABASE_URL:** SQLite in `instance/kdh.sqlite3` remains supported.
- **Legacy Docker files:** `admin-data` remains mounted at `/app/instance`, retaining application files and old SQLite data for rollback. It is not the current Compose primary database.
- The configured Admin database is the source of truth for reporting data. Changing the database connection does not migrate existing data.
- `KDH-Report-New` does not own a second reporting database in the current architecture; it will read published report bundles from the Admin internal API.

See [SYSTEM_CONTEXT.md](SYSTEM_CONTEXT.md) for the dated cross-project review and unfinished work. Migration 4/source snapshots was deployed to Docker PostgreSQL on 2026-10-08 after SQLite/PostgreSQL regression tests passed; migrations 1–3 remain unchanged. Dataset-from-stored-sync and Report-New integration are still pending.

## Data flow

Target flow (the Dataset-from-stored-sync reader and Report-New renderer integration are not yet wired end to end):

```text
Google / Meta / TikTok / YouTube
              |
              v
       provider adapters
              |
              v
          sync_runs
              |
              v
 daily_metrics + source_snapshots
              |
              v
           datasets
              |
              v
        report_bundles
              |
              v
      internal report API
              |
              v
       KDH-Report-New
```

## Main tables

### clients
One row per agency customer. KinderHealth is seeded as the first client.

### connections
One logical connection to a provider for a client. This table stores account identity and status only.

**Provider secrets/tokens are not stored here.** They remain encrypted in the existing `secrets` table. `connections.secret_name` only points to the encrypted secret record.

### source_assets
The concrete assets that can be synchronized, for example:

- GA4 property
- Search Console property
- Facebook Page
- Meta Ad Account
- TikTok Advertiser
- YouTube channel

### sync_runs
Audit record for each backfill, incremental sync, manual refresh, or connection validation.

Important fields:

- requested_start / requested_end
- latest_available_date
- status
- record_count
- warnings / error
- asset_id / provider
- job_id

### sync_watermarks
Tracks the last complete date per asset and the lookback window used when re-fetching recent data.

### daily_metrics
Normalized day-grain provider data. Metrics and dimensions are JSON so each provider can evolve without immediately creating a new physical table for every metric.

Uniqueness is enforced by:

```text
asset + entity type + entity id + date + dimension key
```

This enables idempotent sync/upsert.

### datasets
Existing immutable report snapshots remain unchanged for compatibility.

The current analysis job still fetches provider results before saving a Dataset. Building a new Dataset entirely from persisted sync data is a pending integration step; Builder and Preview already consume saved snapshots only.

### source_snapshots (migration 4)

Stores normalized source payloads and their sync/client/asset lineage, including detail that daily metrics do not preserve. The current writer upserts one row per `sync_run_id`; these source records are distinct from immutable report Dataset snapshots. Provider credentials and OAuth tokens must never enter the payload.

### report_bundles
A published/reportable view over one or more datasets. A bundle owns:

- client
- period
- revision
- DRAFT / PROVISIONAL / FINAL status
- quality status
- selected sections
- branding
- warnings

### report_bundle_sections
Ordered sections included in a bundle, each optionally pointing to its immutable dataset.

## Sync policy

Do not wait for a user to click "Create report" before fetching every provider.

Use three sync modes:

1. **backfill** — initial historical load after connecting an asset.
2. **incremental** — scheduled updates for recent data.
3. **manual** — "Refresh now" from Admin.

Recent days can be re-fetched and upserted because advertising and analytics providers may revise attribution or late data.

## Security

- OAuth refresh/access tokens stay encrypted in `secrets`.
- Never put provider tokens in `daily_metrics`, URLs, browser storage, or Report-New.
- Report-New later receives only a service-to-service credential for the Admin internal API.
- Do not store entire provider responses unless needed for a defined audit/debug requirement; store normalized reporting fields and lineage metadata.

## Migration strategy

The old inline `SCHEMA` remains as the compatibility baseline.

New schema changes are applied through `kdh/migrations.py` and recorded in:

```text
schema_migrations
```

Future changes must be added as new numbered migrations rather than editing production tables ad hoc.
