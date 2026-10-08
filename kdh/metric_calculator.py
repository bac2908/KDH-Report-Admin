
"""Safe KPI calculations from persisted KDH marketing metrics.

No provider calls, mock fallback, database writes or
cross-asset aggregation.
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, InvalidOperation

from .metric_catalog import get_metric
from .metric_reader import (
    _day,
    MAX_PERIOD_DAYS,
    read_metric_series,
)


# Formulas for source metrics that require recalculation.
# Other metrics remain unsupported until safe scope rules exist.
SOURCE_FORMULAS = {
    "ga4.engagement_rate": (
        "ga4.engaged_sessions", "ga4.sessions", "divide", 1
    ),
    "ga4.bounce_rate": (
        "ga4.engaged_sessions", "ga4.sessions", "one_minus", 1
    ),
    "gsc.ctr": (
        "gsc.clicks", "gsc.impressions", "divide", 1
    ),
    "google_ads.ctr": (
        "google_ads.clicks", "google_ads.impressions", "divide", 1
    ),
    "google_ads.average_cpc": (
        "google_ads.spend", "google_ads.clicks", "divide", 1
    ),
    "google_ads.cpm": (
        "google_ads.spend", "google_ads.impressions", "divide", 1000
    ),
    "google_ads.cost_per_conversion": (
        "google_ads.spend", "google_ads.conversions", "divide", 1
    ),
    "google_ads.roas": (
        "google_ads.conversion_value", "google_ads.spend", "divide", 1
    ),
    "facebook_ads.ctr": (
        "facebook_ads.clicks", "facebook_ads.impressions", "divide", 1
    ),
    "facebook_ads.link_ctr": (
        "facebook_ads.link_clicks",
        "facebook_ads.impressions", "divide", 1
    ),
    "facebook_ads.cpc": (
        "facebook_ads.spend", "facebook_ads.clicks", "divide", 1
    ),
    "facebook_ads.cpm": (
        "facebook_ads.spend", "facebook_ads.impressions", "divide", 1000
    ),
    "facebook_ads.cpl": (
        "facebook_ads.spend", "facebook_ads.leads", "divide", 1
    ),
    "facebook_ads.roas": (
        "facebook_ads.conversion_value",
        "facebook_ads.spend", "divide", 1
    ),
    "tiktok_ads.ctr": (
        "tiktok_ads.clicks", "tiktok_ads.impressions", "divide", 1
    ),
    "tiktok_ads.cpc": (
        "tiktok_ads.spend", "tiktok_ads.clicks", "divide", 1
    ),
    "tiktok_ads.cpm": (
        "tiktok_ads.spend", "tiktok_ads.impressions", "divide", 1000
    ),
    "tiktok_ads.cost_per_conversion": (
        "tiktok_ads.spend", "tiktok_ads.conversions", "divide", 1
    ),
    "tiktok_ads.roas": (
        "tiktok_ads.conversion_value", "tiktok_ads.spend", "divide", 1
    ),
}

# Fractions must be in [0, 1].
# 0.12 means 12%; never store 12 as a 12% ratio.
PROPORTION_METRICS = {
    "ga4.engagement_rate",
    "ga4.bounce_rate",
    "gsc.ctr",
    "gsc.recalculated_ctr",
    "google_ads.ctr",
    "facebook_ads.ctr",
    "facebook_ads.link_ctr",
    "tiktok_ads.ctr",
}


def _decimal(value):
    """Convert valid nonnegative values to Decimal."""
    if isinstance(value, bool) or not isinstance(
        value, (int, float, Decimal)
    ):
        return None

    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None

    if not number.is_finite() or number < 0:
        return None

    return number


def _finite_float(value):
    """Return a JSON-safe float or None."""
    try:
        converted = float(value)
    except (ValueError, OverflowError):
        return None

    return converted if math.isfinite(converted) else None


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


def _rule(metric):
    """Resolve only formulas with known operands."""

    if metric["kind"] == "derived":
        dependencies = metric.get("requires", ())

        if (
            metric.get("operation") == "divide"
            and len(dependencies) == 2
        ):
            return (
                dependencies[0],
                dependencies[1],
                "divide",
                1,
            )

    elif (
        metric["kind"] == "source"
        and metric["aggregation"] == "recalculate"
    ):
        return SOURCE_FORMULAS.get(metric["id"])

    return None


def calculate_metric(
    store,
    *,
    metric_id,
    client_id,
    allowed_sources,
    start,
    end,
    asset_id=None,
):
    """Calculate one scoped KPI from two additive period totals.

    Caller must supply the authenticated client's ID and
    server-derived allowed_sources.

    A status other than 'available' always has value=None.
    """

    metric = (
        get_metric(metric_id)
        if isinstance(metric_id, str)
        else None
    )

    if metric is None:
        raise ValueError("Unknown metric ID.")

    source = metric["source"]

    if (
        allowed_sources is None
        or isinstance(allowed_sources, (str, bytes))
    ):
        raise PermissionError(
            "Metric source is not permitted."
        )

    permitted = set(allowed_sources)

    if source not in permitted:
        raise PermissionError(
            "Metric source is not permitted."
        )

    period, days = _period(start, end)
    rule = _rule(metric)

    output = {
        "metric_id": metric_id,
        "label": metric["label"],
        "source": source,
        "unit": metric["unit"],
        "period": period,
        "client_id": client_id,
        "asset_id": None,
        "currency": None,
        "status": "unsupported",
        "value": None,
        "reason": "No safe calculation rule for this metric.",
        "formula": None,
        "operands": [],
        "data_origin": "persisted_unverified",
        "verified_provider": False,
        "warnings": [],
    }

    if rule is None:
        return output

    numerator_id, denominator_id, operation, scale = rule

    output["formula"] = {
        "operation": operation,
        "numerator": numerator_id,
        "denominator": denominator_id,
        "scale": scale,
        "ratio_convention": (
            "fraction" if metric["unit"] == "ratio"
            else None
        ),
    }

    inputs = []

    for operand_id in (numerator_id, denominator_id):
        operand_meta = get_metric(operand_id)

        # Only additive, daily source totals can currently
        # be used as period operands.
        if (
            operand_meta is None
            or operand_meta["kind"] != "source"
            or operand_meta["aggregation"] != "sum"
            or operand_meta["grain"] != "day"
            or operand_meta["source"] != source
        ):
            output["reason"] = (
                "Operand requires a safely scoped period total."
            )
            return output

        item = read_metric_series(
            store,
            metric_id=operand_id,
            client_id=client_id,
            allowed_sources=permitted,
            start=period["start"],
            end=period["end"],
            asset_id=asset_id,
        )

        inputs.append(item)

        output["operands"].append({
            "metric_id": operand_id,
            "status": item["status"],
            "value": item["summary"]["value"],
            "asset_id": item["asset_id"],
            "currency": item["currency"],
            "coverage_days": item["summary"]["coverage_days"],
            "expected_days": item["summary"]["expected_days"],
            "sync_run_ids": sorted({
                row["sync_run_id"]
                for row in item["series"]
                if row.get("sync_run_id")
            }),
        })

    left, right = inputs

    # Never calculate from stale, partial or missing data.
    if any(
        item["status"] != "available"
        for item in inputs
    ):
        output["status"] = "insufficient_data"
        output["reason"] = (
            "An input is missing, partial, stale or unsupported."
        )
        return output

    if any(
        item["summary"]["coverage_days"] != days
        or item["summary"]["expected_days"] != days
        for item in inputs
    ):
        output["status"] = "insufficient_data"
        output["reason"] = (
            "Both inputs must cover the full requested period."
        )
        return output

    # Verify tenant, asset, period and source origin.
    if (
        not left["asset_id"]
        or left["asset_id"] != right["asset_id"]
        or left["client_id"] != right["client_id"]
        or left["client_id"] != client_id
        or left["period"] != period
        or right["period"] != period
        or left["data_origin"] != right["data_origin"]
    ):
        output["status"] = "incompatible_scope"
        output["reason"] = (
            "Operands must share client, asset, period and origin."
        )
        return output

    # Money requires a consistent known currency.
    monetary = any(
        get_metric(item["metric_id"])["unit"] == "currency"
        for item in output["operands"]
    )

    if monetary and (
        not left["currency"]
        or left["currency"] != right["currency"]
    ):
        output["status"] = "incompatible_scope"
        output["reason"] = (
            "Currency is missing or inconsistent."
        )
        return output

    numerator = _decimal(left["summary"]["value"])
    denominator = _decimal(right["summary"]["value"])

    if numerator is None or denominator is None:
        output["status"] = "insufficient_data"
        output["reason"] = (
            "A safe numeric period total is unavailable."
        )
        return output

    if denominator == 0:
        output["status"] = "division_by_zero"
        output["reason"] = (
            "Denominator is zero; KPI is unavailable."
        )
        return output

    result = numerator / denominator * Decimal(scale)

    if operation == "one_minus":
        result = Decimal(1) - result

    if (
        metric_id in PROPORTION_METRICS
        and not 0 <= result <= 1
    ):
        output["status"] = "invalid_ratio"
        output["reason"] = (
            "Proportion is outside the valid 0..1 range."
        )
        return output

    calculated = _finite_float(result)

    if calculated is None:
        output["status"] = "insufficient_data"
        output["reason"] = (
            "Calculated value is not finite."
        )
        return output

    output.update(
        value=calculated,
        status="available",
        reason=None,
        asset_id=left["asset_id"],
        currency=(
            left["currency"]
            if metric["unit"] == "currency"
            else None
        ),
    )

    output["warnings"].append(
        "Computed from persisted totals. Original provider "
        "authenticity, timezone and attribution have not "
        "been independently verified."
    )

    return output


def compare_calculated_periods(current, previous):
    """Compare two finalized KPIs with the same metric/scope.

    For ratio metrics, return percentage-point change.
    For others, return relative percentage change.
    """

    if current["metric_id"] != previous["metric_id"]:
        raise ValueError(
            "Cannot compare different metric IDs."
        )

    output = {
        "metric_id": current["metric_id"],
        "status": "insufficient_data",
        "delta": None,
        "change_percent": None,
        "change_percentage_points": None,
    }

    if (
        current["status"] != "available"
        or previous["status"] != "available"
    ):
        return output

    fields = (
        "source",
        "unit",
        "client_id",
        "asset_id",
        "currency",
        "data_origin",
    )

    if any(
        current.get(key) != previous.get(key)
        for key in fields
    ):
        output["status"] = "incompatible_scope"
        return output

    try:
        current_start = date.fromisoformat(
            current["period"]["start"]
        )
        current_end = date.fromisoformat(
            current["period"]["end"]
        )
        previous_start = date.fromisoformat(
            previous["period"]["start"]
        )
        previous_end = date.fromisoformat(
            previous["period"]["end"]
        )

    except (KeyError, TypeError, ValueError):
        output["status"] = "incompatible_scope"
        return output

    if (
        (current_end - current_start).days
        != (previous_end - previous_start).days
        or not previous_end < current_start
    ):
        output["status"] = "incompatible_scope"
        return output

    new = _decimal(current.get("value"))
    old = _decimal(previous.get("value"))

    if new is None or old is None:
        return output

    difference = _finite_float(new - old)

    if difference is None:
        return output

    output["status"] = "available"
    output["delta"] = difference

    if current["unit"] == "ratio":
        output["change_percentage_points"] = (
            _finite_float((new - old) * 100)
        )

    elif old != 0:
        output["change_percent"] = (
            _finite_float((new - old) / old * 100)
        )

    return output
