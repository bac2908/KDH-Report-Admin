
"""Read-only, source-traceable Marketing Evidence Engine.

An evidence record proves what the internal database contains.
It does NOT independently verify the provider's original data.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone

from .metric_catalog import SOURCES, get_metric
from .metric_reader import (
    MAX_PERIOD_DAYS,
    _day,
    read_metric_series,
)
from .metric_calculator import (
    calculate_metric,
    compare_calculated_periods,
)


MAX_LINEAGE_IDS = 50


def _period(start, end):
    first = _day(start, "start")
    last = _day(end, "end")

    days = (last - first).days + 1

    if not 1 <= days <= MAX_PERIOD_DAYS:
        raise ValueError(
            f"Period must be 1-{MAX_PERIOD_DAYS} days."
        )

    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
    }, days


def _safe_number(value):
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        return None

    try:
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _lineage(ids):
    clean = sorted({
        value
        for value in ids
        if isinstance(value, str) and value
    })

    return {
        "sync_run_ids": clean[:MAX_LINEAGE_IDS],
        "sync_run_count": len(clean),
        "truncated": len(clean) > MAX_LINEAGE_IDS,
    }


def _read(
    store,
    metric,
    *,
    client_id,
    allowed_sources,
    period,
    asset_id,
):
    metric_id = metric["id"]

    is_calculated = (
        metric["kind"] == "derived"
        or (
            metric["kind"] == "source"
            and metric["aggregation"] == "recalculate"
        )
    )

    if is_calculated:
        item = calculate_metric(
            store,
            metric_id=metric_id,
            client_id=client_id,
            allowed_sources=allowed_sources,
            start=period["start"],
            end=period["end"],
            asset_id=asset_id,
        )

        ids = [
            run
            for operand in item.get("operands", [])
            for run in operand.get("sync_run_ids", [])
        ]

        points = []

        value = (
            item.get("value")
            if item.get("status") == "available"
            else None
        )

        freshness = None

    else:
        item = read_metric_series(
            store,
            metric_id=metric_id,
            client_id=client_id,
            allowed_sources=allowed_sources,
            start=period["start"],
            end=period["end"],
            asset_id=asset_id,
        )

        points = [
            {
                "date": row["date"],
                "value": row["value"],
            }
            for row in item.get("series", [])
        ]

        ids = [
            row.get("sync_run_id")
            for row in item.get("series", [])
        ]

        value = (
            item.get("summary", {}).get("value")
            if item.get("status") == "available"
            else None
        )

        freshness = item.get("freshness")

    value = _safe_number(value)

    coverage = item.get("summary", {})

    coverage_ok = (
        is_calculated
        or (
            isinstance(coverage, dict)
            and type(coverage.get("coverage_days")) is int
            and type(coverage.get("expected_days")) is int
            and coverage["coverage_days"] > 0
            and (
                coverage["coverage_days"]
                == coverage["expected_days"]
            )
        )
    )

    lineage = _lineage(ids)

    status = item.get("status", "unsupported")

    eligible_origin = (
        item.get("data_origin") == "persisted_unverified"
    )

    if (
        status == "available"
        and eligible_origin
        and coverage_ok
        and value is not None
        and lineage["sync_run_count"]
    ):
        evidence_status = "recorded_unverified"

    elif (
        status == "available"
        and eligible_origin
        and coverage_ok
        and points
        and lineage["sync_run_count"]
    ):
        evidence_status = "observations_only"

    else:
        evidence_status = "not_ready"
        value = None

    warnings = [
        warning
        for warning in item.get("warnings", [])
        if isinstance(warning, str)
    ]

    if (
        status == "available"
        and not lineage["sync_run_count"]
    ):
        warnings.append(
            "No sync-run lineage: "
            "evidence cannot be presented."
        )

    if status == "available" and not eligible_origin:
        warnings.append(
            "Data origin is not eligible "
            "for this evidence record."
        )

    if status == "available" and not coverage_ok:
        warnings.append(
            "Incomplete period coverage: "
            "no period claim can be presented."
        )

    return {
        "status": status,
        "evidence_status": evidence_status,
        "value": value,
        "asset_id": item.get("asset_id"),
        "currency": item.get("currency"),
        "data_origin": item.get(
            "data_origin", "unknown"
        ),
        "freshness": freshness,
        "daily_observations": points,
        "lineage": lineage,
        "warnings": warnings,
    }


def _comparison_view(
    current,
    previous,
    metric,
    client_id,
    current_period,
    previous_period,
):
    def as_calculated(item, period):
        return {
            "metric_id": metric["id"],
            "source": metric["source"],
            "unit": metric["unit"],
            "client_id": client_id,
            "asset_id": item["asset_id"],
            "currency": item["currency"],
            "data_origin": item["data_origin"],
            "period": period,
            "status": (
                "available"
                if item["evidence_status"]
                == "recorded_unverified"
                else "insufficient_data"
            ),
            "value": item["value"],
        }

    outcome = compare_calculated_periods(
        as_calculated(current, current_period),
        as_calculated(previous, previous_period),
    )

    return {
        "period": previous_period,
        "status": outcome["status"],
        "previous_value": (
            previous["value"]
            if outcome["status"] == "available"
            else None
        ),
        "delta": outcome["delta"],
        "change_percent": outcome["change_percent"],
        "change_percentage_points": outcome[
            "change_percentage_points"
        ],
        "lineage": previous["lineage"],
        "warnings": previous["warnings"],
    }


def build_metric_evidence(
    store,
    *,
    metric_id,
    client_id,
    allowed_sources,
    start,
    end,
    asset_id=None,
    compare_start=None,
    compare_end=None,
):
    """Build evidence for one KPI and optional previous period.

    Permissions and client_id must be supplied by trusted
    server-side logic, never copied from a browser request.
    """

    if not isinstance(metric_id, str):
        raise ValueError(
            "metric_id must be a string."
        )

    metric = get_metric(metric_id)

    if metric is None:
        raise ValueError(
            "Unknown metric ID."
        )

    if (
        not isinstance(client_id, str)
        or not client_id.strip()
    ):
        raise ValueError(
            "client_id is required."
        )

    if (
        allowed_sources is None
        or isinstance(
            allowed_sources, (str, bytes)
        )
    ):
        raise PermissionError(
            "Metric source is not permitted."
        )

    permitted = set(allowed_sources)

    if metric["source"] not in permitted:
        raise PermissionError(
            "Metric source is not permitted."
        )

    period, days = _period(start, end)

    has_comparison = (
        compare_start is not None
        or compare_end is not None
    )

    if has_comparison:
        if (
            compare_start is None
            or compare_end is None
        ):
            raise ValueError(
                "Both compare_start and "
                "compare_end are required."
            )

        previous_period, previous_days = _period(
            compare_start, compare_end
        )

        if (
            previous_days != days
            or previous_period["end"]
            >= period["start"]
        ):
            raise ValueError(
                "Comparison must precede and "
                "match period length."
            )

    current = _read(
        store,
        metric,
        client_id=client_id,
        allowed_sources=permitted,
        period=period,
        asset_id=asset_id,
    )

    spec = SOURCES[metric["source"]]

    identifier = json.dumps(
        {
            "metric": metric_id,
            "client": client_id,
            "asset": current["asset_id"],
            "period": period,
            "lineage": current[
                "lineage"
            ]["sync_run_ids"],
        },
        sort_keys=True,
    )

    evidence_id = hashlib.sha256(
        identifier.encode("utf-8")
    ).hexdigest()[:32]

    response = {
        "schema_version": "1.0",
        "evidence_id": evidence_id,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "metric": {
            "id": metric_id,
            "label": metric["label"],
            "unit": metric["unit"],
            "aggregation": metric[
                "aggregation"
            ],
        },
        "scope": {
            "client_id": client_id,
            "asset_id": current["asset_id"],
            "period": period,
            "currency": current["currency"],
        },
        "source": {
            "key": metric["source"],
            "provider": spec["provider"],
            "asset_type": spec["asset_type"],
            "provider_verified": False,
            "source_url": None,
        },
        "result": {
            "status": current["status"],
            "evidence_status": current[
                "evidence_status"
            ],
            "value": current["value"],
            "daily_observations": current[
                "daily_observations"
            ],
        },
        "freshness": current["freshness"],
        "lineage": current["lineage"],
        "quality": {
            "data_origin": current[
                "data_origin"
            ],
            "is_demo": None,
            "independently_verified": False,
            "ready_as_verified_client_claim": False,
            "warnings": current["warnings"],
        },
        "comparison": None,
        "claim_text": None,
    }

    if has_comparison:
        previous = _read(
            store,
            metric,
            client_id=client_id,
            allowed_sources=permitted,
            period=previous_period,
            asset_id=(
                current["asset_id"]
                or asset_id
            ),
        )

        response["comparison"] = _comparison_view(
            current,
            previous,
            metric,
            client_id,
            period,
            previous_period,
        )

    return response
