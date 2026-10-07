"""Persistence helpers for the multi-client reporting platform.

Provider adapters (Google/Meta/TikTok/YouTube) should normalize their results and
write through this module. Provider credentials themselves stay encrypted in the
existing `secrets` table; ordinary connection rows only keep a secret reference.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .core import now, pack, uid


DEFAULT_CLIENT_ID = "client_kinderhealth"


def _stable_metric_id(
    asset_id: str,
    entity_type: str,
    entity_id: str,
    metric_date: str,
    dimension_key: str,
) -> str:
    raw = "|".join((asset_id, entity_type, entity_id, metric_date, dimension_key))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class PlatformData:
    def __init__(self, store):
        self.store = store

    def clients(self, active_only: bool = True):
        sql = "SELECT * FROM clients"
        args = ()
        if active_only:
            sql += " WHERE active=1"
        sql += " ORDER BY name"
        return self.store.all(sql, args)

    def client(self, client_id: str = DEFAULT_CLIENT_ID):
        return self.store.one("SELECT * FROM clients WHERE id=?", (client_id,))

    def upsert_connection(
        self,
        *,
        client_id: str,
        provider: str,
        external_account_id: str | None = None,
        account_name: str | None = None,
        account_email: str | None = None,
        status: str = "connected",
        secret_name: str | None = None,
        db=None,
    ) -> str:
        if db is None:
            with self.store.connect(immediate=True) as db:
                return self.upsert_connection(
                    client_id=client_id, provider=provider,
                    external_account_id=external_account_id, account_name=account_name,
                    account_email=account_email, status=status, secret_name=secret_name, db=db,
                )
        existing = db.execute(
            """
            SELECT id FROM connections
            WHERE client_id=? AND provider=? AND COALESCE(external_account_id,'')=?
            ORDER BY created_at LIMIT 1
            """,
            (client_id, provider, external_account_id or ""),
        ).fetchone()
        connection_id = existing["id"] if existing else uid()
        timestamp = now()
        if existing:
            db.execute(
                """
                UPDATE connections
                SET account_name=?, account_email=?, status=?, secret_name=?,
                    connected_at=CASE WHEN ?='connected' THEN COALESCE(connected_at,?) ELSE connected_at END,
                    updated_at=?
                WHERE id=?
                """,
                (
                    account_name,
                    account_email,
                    status,
                    secret_name,
                    status,
                    timestamp,
                    timestamp,
                    connection_id,
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO connections (
                    id,client_id,provider,external_account_id,account_name,
                    account_email,status,secret_name,connected_at,last_sync_at,
                    created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    connection_id,
                    client_id,
                    provider,
                    external_account_id,
                    account_name,
                    account_email,
                    status,
                    secret_name,
                    timestamp if status == "connected" else None,
                    None,
                    timestamp,
                    timestamp,
                ),
            )
        return connection_id

    def upsert_asset(
        self,
        *,
        client_id: str,
        provider: str,
        asset_type: str,
        external_id: str,
        name: str,
        connection_id: str | None = None,
        timezone: str | None = None,
        currency: str | None = None,
        metadata: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> str:
        existing = self.store.one(
            """
            SELECT id FROM source_assets
            WHERE client_id=? AND provider=? AND asset_type=? AND external_id=?
            """,
            (client_id, provider, asset_type, external_id),
        )
        asset_id = existing["id"] if existing else uid()
        timestamp = now()
        if existing:
            self.store.execute(
                """
                UPDATE source_assets
                SET connection_id=?, name=?, timezone=?, currency=?, enabled=?,
                    metadata=?, updated_at=?
                WHERE id=?
                """,
                (
                    connection_id,
                    name,
                    timezone,
                    currency,
                    int(enabled),
                    pack(metadata or {}),
                    timestamp,
                    asset_id,
                ),
            )
        else:
            self.store.execute(
                """
                INSERT INTO source_assets (
                    id,connection_id,client_id,provider,asset_type,external_id,
                    name,timezone,currency,enabled,metadata,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset_id,
                    connection_id,
                    client_id,
                    provider,
                    asset_type,
                    external_id,
                    name,
                    timezone,
                    currency,
                    int(enabled),
                    pack(metadata or {}),
                    timestamp,
                    timestamp,
                ),
            )
        return asset_id

    def start_sync(
        self,
        *,
        client_id: str,
        provider: str,
        sync_type: str,
        requested_start: str | None,
        requested_end: str | None,
        connection_id: str | None = None,
        asset_id: str | None = None,
        job_id: str | None = None,
    ) -> str:
        sync_id = uid()
        timestamp = now()
        self.store.execute(
            """
            INSERT INTO sync_runs (
                id,client_id,connection_id,asset_id,provider,sync_type,
                requested_start,requested_end,status,latest_available_date,
                record_count,started_at,finished_at,fetched_at,error_code,
                error_message,warnings,job_id,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sync_id,
                client_id,
                connection_id,
                asset_id,
                provider,
                sync_type,
                requested_start,
                requested_end,
                "running",
                None,
                0,
                timestamp,
                None,
                None,
                None,
                None,
                "[]",
                job_id,
                timestamp,
            ),
        )
        return sync_id

    def finish_sync(
        self,
        sync_id: str,
        *,
        status: str,
        latest_available_date: str | None = None,
        record_count: int = 0,
        warnings: list[str] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        timestamp = now()
        self.store.execute(
            """
            UPDATE sync_runs
            SET status=?, latest_available_date=?, record_count=?,
                finished_at=?, fetched_at=?, warnings=?, error_code=?, error_message=?
            WHERE id=?
            """,
            (
                status,
                latest_available_date,
                record_count,
                timestamp,
                timestamp,
                pack(warnings or []),
                error_code,
                error_message,
                sync_id,
            ),
        )
        row = self.store.one("SELECT connection_id,asset_id FROM sync_runs WHERE id=?", (sync_id,))
        if status in ("succeeded", "partial") and row:
            if row.get("connection_id"):
                self.store.execute(
                    "UPDATE connections SET last_sync_at=?,updated_at=? WHERE id=?",
                    (timestamp, timestamp, row["connection_id"]),
                )
            if row.get("asset_id"):
                self.store.execute(
                    """
                    INSERT INTO sync_watermarks (
                        asset_id,last_complete_date,last_attempt_at,lookback_days,updated_at
                    ) VALUES (?,?,?,?,?)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        last_complete_date=excluded.last_complete_date,
                        last_attempt_at=excluded.last_attempt_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        row["asset_id"],
                        latest_available_date,
                        timestamp,
                        3,
                        timestamp,
                    ),
                )

    def upsert_daily_metric(
        self,
        *,
        client_id: str,
        asset_id: str,
        provider: str,
        entity_type: str,
        metric_date: str,
        metrics: dict[str, Any],
        entity_id: str = "",
        dimension_key: str = "",
        dimensions: dict[str, Any] | None = None,
        source_hash: str | None = None,
        sync_run_id: str | None = None,
    ) -> str:
        metric_id = _stable_metric_id(
            asset_id, entity_type, entity_id, metric_date, dimension_key
        )
        timestamp = now()
        self.store.execute(
            """
            INSERT INTO daily_metrics (
                id,client_id,asset_id,provider,entity_type,entity_id,metric_date,
                dimension_key,dimensions,metrics,source_hash,sync_run_id,fetched_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id,entity_type,entity_id,metric_date,dimension_key)
            DO UPDATE SET
                metrics=excluded.metrics,
                dimensions=excluded.dimensions,
                source_hash=excluded.source_hash,
                sync_run_id=excluded.sync_run_id,
                fetched_at=excluded.fetched_at
            """,
            (
                metric_id,
                client_id,
                asset_id,
                provider,
                entity_type,
                entity_id,
                metric_date,
                dimension_key,
                pack(dimensions or {}),
                pack(metrics),
                source_hash,
                sync_run_id,
                timestamp,
            ),
        )
        return metric_id
