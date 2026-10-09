
"""Read normalized, source-scoped metrics from KDH Data Foundation.

Read-only: no provider calls, mock fallback or database writes.
Client ID and allowed sources must come from trusted backend logic.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime
from typing import Any

from .metric_catalog import SOURCES, get_metric


MAX_PERIOD_DAYS = 366


def _day(value: str | date, name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
    ):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass

    raise ValueError(
        f"{name} must be an ISO date (YYYY-MM-DD)."
    )


def _number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        return False

    try:
        return math.isfinite(value) and value >= 0
    except (ValueError, OverflowError):
        return False


def _metrics(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        return {}

    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}

    return decoded if isinstance(decoded, dict) else {}


def _is_summary_dimensions(raw: Any) -> bool:
    """Only an explicitly empty JSON object is a summary row."""
    if isinstance(raw, dict):
        return not raw

    if not isinstance(raw, str):
        return False

    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return False

    return isinstance(value, dict) and not value


def _empty_result(
    metric: dict,
    *,
    client_id: str,
    start: str,
    end: str,
    days: int,
) -> dict:
    return {
        "metric_id": metric["id"],
        "label": metric["label"],
        "source": metric["source"],
        "unit": metric["unit"],
        "aggregation": metric["aggregation"],
        "grain": metric["grain"],
        "client_id": client_id,
        "asset_id": None,
        "currency": None,
        "period": {
            "start": start,
            "end": end,
        },
        "status": "no_data",
        "reason": None,
        "data_origin": "persisted_unverified",
        "series": [],
        "summary": {
            "value": None,
            "coverage_days": 0,
            "expected_days": days,
        },
        "freshness": {
            "latest_sync_status": None,
            "latest_sync_at": None,
            "latest_available_date": None,
            "last_metric_date": None,
        },
        "warnings": [],
    }


def read_metric_series(
    store,
    *,
    metric_id: str,
    client_id: str,
    allowed_sources,
    start: str | date,
    end: str | date,
    asset_id: str | None = None,
) -> dict:
    """Read one metric for one client and one normalized asset.

    Supported:
    - Daily persisted source metrics.
    - Safe SUM totals when every requested date is present.

    Non-additive metrics can have daily values without period totals.

    Snapshot, monthly and calculated metrics need separate
    readers/calculators in later steps.
    """

    if not isinstance(client_id, str) or not client_id.strip():
        raise ValueError("client_id is required.")

    if not isinstance(metric_id, str):
        raise ValueError("metric_id must be a string.")

    metric = get_metric(metric_id)

    if metric is None:
        raise ValueError(f"Unknown metric: {metric_id}")

    # Reject unauthorized sources BEFORE looking up tenant data.
    source = metric["source"]

    if (
        allowed_sources is None
        or isinstance(allowed_sources, (str, bytes))
        or source not in set(allowed_sources)
    ):
        raise PermissionError(
            "Metric source is not permitted."
        )

    first = _day(start, "start")
    last = _day(end, "end")

    days = (last - first).days + 1

    if days < 1 or days > MAX_PERIOD_DAYS:
        raise ValueError(
            f"Period must be 1-{MAX_PERIOD_DAYS} days."
        )

    start_text = first.isoformat()
    end_text = last.isoformat()

    result = _empty_result(
        metric,
        client_id=client_id,
        start=start_text,
        end=end_text,
        days=days,
    )

    if metric["kind"] != "source" or (metric["grain"] != "day" and source != 'keywords'):
        result["status"] = "unsupported"
        result["reason"] = (
            "Requires a separate snapshot/month/"
            "derived metric reader."
        )
        return result

    spec = SOURCES[source]

    # Find enabled assets belonging to the requested client.
    assets = store.all(
        """
        SELECT id, currency
        FROM source_assets
        WHERE client_id=?
          AND provider=?
          AND asset_type=?
          AND enabled=1
        ORDER BY id
        """,
        (
            client_id,
            spec["provider"],
            spec["asset_type"],
        ),
    )

    if asset_id is not None:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError(
                "asset_id must be a nonempty string."
            )

        matches = [
            asset for asset in assets
            if asset["id"] == asset_id
        ]

        if not matches:
            result["status"] = "asset_not_available"
            result["reason"] = (
                "Asset is disabled, missing, "
                "or outside the client/source scope."
            )
            return result

        chosen = matches[0]

    elif not assets:
        result["status"] = "not_configured"
        result["reason"] = (
            "No enabled asset for this client and metric source."
        )
        return result

    elif len(assets) > 1:
        result["status"] = "asset_selection_required"
        result["reason"] = (
            "Multiple eligible assets; "
            "select an asset explicitly."
        )
        return result

    else:
        chosen = assets[0]

    asset_id = chosen["id"]

    result["asset_id"] = asset_id
    result["currency"] = chosen["currency"]

    from .metric_snapshot import snapshot_series
    snapshot = snapshot_series(store, metric, result)
    if snapshot is not None:
        return snapshot

    # Latest sync overlapping the requested reporting period.
    latest = store.one(
        """
        SELECT
            status,
            record_count,
            error_code,
            created_at,
            latest_available_date
        FROM sync_runs
        WHERE client_id=?
          AND provider=?
          AND asset_id=?
          AND (
              requested_start IS NULL
              OR requested_start <= ?
          )
          AND (
              requested_end IS NULL
              OR requested_end >= ?
          )
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (
            client_id,
            spec["provider"],
            asset_id,
            end_text,
            start_text,
        ),
    )

    if latest:
        result["freshness"]["latest_sync_status"] = (
            latest["status"]
        )

        result["freshness"]["latest_sync_at"] = (
            latest["created_at"]
        )

        result["freshness"]["latest_available_date"] = (
            latest["latest_available_date"]
        )

        if latest["status"] != "succeeded":
            result["warnings"].append(
                "Latest overlapping sync did not succeed; "
                "any older data is not fresh."
            )

            if latest.get("error_code"):
                result["warnings"].append(
                    "Latest sync error code: "
                    + str(latest["error_code"])
                )

        elif not latest["record_count"]:
            result["warnings"].append(
                "Latest sync returned no rows; "
                "earlier stored data may be stale."
            )

    # Canonical daily summary rows only.
    # Do not sum individual keywords, campaigns, posts,
    # other assets or dimensional breakdowns.
    rows = store.all(
        """
        SELECT
            dm.metric_date,
            dm.metrics,
            dm.dimensions,
            dm.sync_run_id,
            dm.fetched_at
        FROM daily_metrics dm
        INNER JOIN sync_runs sr
            ON sr.id = dm.sync_run_id
        WHERE dm.client_id=?
          AND dm.asset_id=?
          AND dm.provider=?
          AND dm.entity_type=?
          AND dm.entity_id=''
          AND dm.dimension_key=''
          AND dm.metric_date BETWEEN ? AND ?
          AND sr.client_id=dm.client_id
          AND sr.asset_id=dm.asset_id
          AND sr.provider=dm.provider
          AND sr.status='succeeded'
          AND sr.record_count > 0
          AND sr.sync_type != 'validation'
          AND (
              sr.requested_start IS NULL
              OR dm.metric_date >= sr.requested_start
          )
          AND (
              sr.requested_end IS NULL
              OR dm.metric_date <= sr.requested_end
          )
        ORDER BY dm.metric_date
        """,
        (
            client_id,
            asset_id,
            spec["provider"],
            spec["entity_type"],
            start_text,
            end_text,
        ),
    )

    for row in rows:
        # A blank dimension_key alone does not prove
        # this is a whole-source summary row.
        if not _is_summary_dimensions(row["dimensions"]):
            continue

        value = _metrics(row["metrics"]).get(
            metric["field"]
        )

        if not _number(value):
            continue

        result["series"].append(
            {
                "date": row["metric_date"],
                "value": value,
                "sync_run_id": row["sync_run_id"],
                "fetched_at": row["fetched_at"],
            }
        )

    series = result["series"]

    if not series:
        result["reason"] = (
            "No eligible, succeeded-sync metric rows "
            "for the selected period."
        )
        return result

    # Do not turn missing days into zeros.
    result["summary"]["coverage_days"] = len(
        {item["date"] for item in series}
    )

    result["freshness"]["last_metric_date"] = (
        series[-1]["date"]
    )

    complete = (
        result["summary"]["coverage_days"] == days
    )

    latest_date = (
        latest["latest_available_date"]
        if latest else None
    )

    if latest_date is None:
        result["warnings"].append(
            "Source does not specify a latest available date."
        )

    elif latest_date < end_text:
        result["warnings"].append(
            "Source latest available date "
            "precedes requested period end."
        )

    freshness_complete = bool(
        latest_date and latest_date >= end_text
    )

    if not complete:
        result["warnings"].append(
            "Some dates have no eligible metric rows; "
            "missing is not zero."
        )

    # Only SUM metrics can produce simple period totals.
    if metric["aggregation"] != "sum":
        result["warnings"].append(
            "Period total is not safe for this aggregation; "
            "use scoped provider totals/calculation."
        )

    elif metric["unit"] == "currency" and not result["currency"]:
        result["warnings"].append(
            "Asset currency is unknown; "
            "period monetary total is unavailable."
        )

    elif complete and freshness_complete:
        result["summary"]["value"] = sum(
            item["value"] for item in series
        )

    # Never describe a failed/empty latest sync as fresh.
    if latest and (
        latest["status"] != "succeeded"
        or not latest["record_count"]
    ):
        result["status"] = "stale"

    elif not complete or not freshness_complete:
        result["status"] = "partial"

    else:
        result["status"] = "available"

    # Persisted data is not independent proof that
    # the original provider response was authentic.
    return result
