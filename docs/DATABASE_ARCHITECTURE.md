# Database architecture

## Decision

- **Production / shared environment:** PostgreSQL (Neon via `DATABASE_URL`).
- **Local development / Docker demo:** SQLite in `instance/kdh.sqlite3`.
- PostgreSQL is the source of truth for deployed reporting data.
- `KDH-Report-New` does not own a second reporting database in the current architecture; it will read published report bundles from the Admin internal API.

## Data flow

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
        daily_metrics
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
