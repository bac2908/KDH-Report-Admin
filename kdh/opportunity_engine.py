
"""Rule-based Marketing Opportunity Engine.

Read-only. Produces INTERNAL review candidates,
not independently verified claims or growth promises.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone

from .evidence_engine import build_metric_evidence
from .metric_catalog import SOURCES, get_metric
from .metric_reader import MAX_PERIOD_DAYS, _day


# Only summary-level metrics with safely comparable periods.
# Relative threshold: change / previous value.
# Absolute threshold: change in the metric's own unit.
RULES = (
    {
        "id": "ga4_sessions_down",
        "metric": "ga4.sessions",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.20,
        "min_previous": 100,
        "title": "Review website traffic decline",
        "action": (
            "Check channel mix, tracking continuity "
            "and landing pages."
        ),
    },
    {
        "id": "gsc_clicks_down",
        "metric": "gsc.clicks",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.20,
        "min_previous": 100,
        "title": "Review decline in organic search clicks",
        "action": (
            "Inspect query/page-level GSC data "
            "before choosing SEO changes."
        ),
    },
    {
        "id": "gsc_ctr_down",
        "metric": "gsc.ctr",
        "direction": "down",
        "kind": "absolute",
        "threshold": 0.02,
        "min_previous": 0,
        "guard_metric": "gsc.impressions",
        "guard_min": 1000,
        "title": "Investigate lower search CTR",
        "action": (
            "Inspect high-impression queries and pages; "
            "do not infer rank changes."
        ),
    },
    {
        "id": "google_ads_conversions_down",
        "metric": "google_ads.conversions",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 10,
        "title": "Review Google Ads conversion decline",
        "action": (
            "Check conversion tracking, attribution "
            "and campaign segments."
        ),
    },
    {
        "id": "facebook_ads_leads_down",
        "metric": "facebook_ads.leads",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 10,
        "title": "Review decline in Meta-attributed leads",
        "action": (
            "Check attribution, campaigns, forms "
            "and lead quality in CRM."
        ),
    },
    {
        "id": "facebook_ads_cpl_up",
        "metric": "facebook_ads.cpl",
        "direction": "up",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 0,
        "guard_metric": "facebook_ads.leads",
        "guard_min": 10,
        "title": "Investigate rising Meta cost per lead",
        "action": (
            "Review spend, lead quality and creatives "
            "before changing budgets."
        ),
    },
    {
        "id": "facebook_content_engagements_down",
        "metric": "facebook_content.engagements",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 100,
        "title": "Review lower Facebook content engagement",
        "action": (
            "Compare post format and publication volume "
            "before conclusions."
        ),
    },
    {
        "id": "instagram_engagements_down",
        "metric": "instagram.engagements",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 100,
        "title": "Review lower Instagram engagement",
        "action": (
            "Inspect post mix and engagement definitions "
            "before conclusions."
        ),
    },
    {
        "id": "tiktok_ads_conversions_down",
        "metric": "tiktok_ads.conversions",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 10,
        "title": "Review decline in TikTok Ads conversions",
        "action": (
            "Check tracking, attribution, campaigns "
            "and video creatives."
        ),
    },
    {
        "id": "tiktok_ads_cost_up",
        "metric": "tiktok_ads.cost_per_conversion",
        "direction": "up",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 0,
        "guard_metric": "tiktok_ads.conversions",
        "guard_min": 10,
        "title": "Investigate higher TikTok cost per conversion",
        "action": (
            "Review conversion definitions and audiences "
            "before scaling."
        ),
    },
    {
        "id": "youtube_views_down",
        "metric": "youtube.views",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 200,
        "title": "Review decline in YouTube views",
        "action": (
            "Check publishing cadence, traffic sources "
            "and video mix."
        ),
    },
    {
        "id": "gmb_website_clicks_down",
        "metric": "gmb.website_clicks",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 30,
        "title": "Review fewer Business Profile website clicks",
        "action": (
            "Inspect listing performance "
            "and local search trends."
        ),
    },
    {
        "id": "crm_qualified_leads_down",
        "metric": "crm.qualified_leads",
        "direction": "down",
        "kind": "relative",
        "threshold": 0.25,
        "min_previous": 10,
        "title": "Review decline in qualified leads",
        "action": (
            "Audit CRM definitions, deduplication "
            "and lead sources."
        ),
    },
)


def _number(value):
    if isinstance(value, bool) or not isinstance(
        value, (int, float)
    ):
        return None

    try:
        if math.isfinite(value) and value >= 0:
            return float(value)
    except (TypeError, ValueError, OverflowError):
        pass

    return None


def _period(start, end):
    first = _day(start, "start")
    last = _day(end, "end")
    days = (last - first).days + 1

    if not 1 <= days <= MAX_PERIOD_DAYS:
        raise ValueError(
            "Report period must contain 1-366 days."
        )

    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
    }, days


def _eligible(
    evidence,
    *,
    metric_id,
    client_id,
    current_period,
    previous_period,
    asset_id=None,
):
    """Accept only comparable evidence with sync lineage."""
    if not isinstance(evidence, dict):
        return False

    metric = evidence.get("metric") or {}
    scope = evidence.get("scope") or {}
    result = evidence.get("result") or {}
    quality = evidence.get("quality") or {}
    lineage = evidence.get("lineage") or {}
    comparison = evidence.get("comparison") or {}
    asset = scope.get("asset_id")

    return bool(
        metric.get("id") == metric_id
        and scope.get("client_id") == client_id
        and scope.get("period") == current_period
        and isinstance(asset, str)
        and asset
        and (asset_id is None or asset == asset_id)
        and result.get("status") == "available"
        and result.get("evidence_status")
        == "recorded_unverified"
        and quality.get("data_origin")
        == "persisted_unverified"
        and quality.get("is_demo") is not True
        and lineage.get("sync_run_count", 0) > 0
        and isinstance(
            lineage.get("sync_run_ids"), list
        )
        and len(lineage["sync_run_ids"]) > 0
        and comparison.get("status") == "available"
        and comparison.get("period") == previous_period
        and isinstance(
            comparison.get("lineage"), dict
        )
        and comparison["lineage"].get(
            "sync_run_count", 0
        ) > 0
        and len(
            comparison["lineage"].get(
                "sync_run_ids"
            ) or []
        ) > 0
        and _number(result.get("value")) is not None
        and _number(
            comparison.get("previous_value")
        ) is not None
    )


def build_opportunities(
    store,
    *,
    client_id,
    allowed_sources,
    start,
    end,
    compare_start=None,
    compare_end=None,
    source=None,
    asset_id=None,
):
    """Generate internal review candidates from stored evidence."""

    if (
        not isinstance(client_id, str)
        or not client_id.strip()
    ):
        raise ValueError("client_id is required.")

    if (
        allowed_sources is None
        or isinstance(
            allowed_sources, (str, bytes)
        )
    ):
        raise PermissionError(
            "Source permission set is required."
        )

    permitted = set(allowed_sources) & set(SOURCES)

    if source is not None:
        if source not in SOURCES:
            raise ValueError("Unknown source.")

        if source not in permitted:
            raise PermissionError("Source not permitted.")

        permitted = {source}

    if asset_id is not None:
        if (
            not isinstance(asset_id, str)
            or not asset_id.strip()
        ):
            raise ValueError("Invalid asset_id.")

        if source is None:
            raise ValueError(
                "Selecting an asset requires a source."
            )

    current, days = _period(start, end)

    if (compare_start is None) != (compare_end is None):
        raise ValueError(
            "Both compare_start and compare_end are required."
        )

    if compare_start is None:
        current_start = date.fromisoformat(
            current["start"]
        )
        try:
            past_end = current_start - timedelta(days=1)
            past_start = past_end - timedelta(
                days=days - 1
            )
        except OverflowError as exc:
            raise ValueError(
                "Comparison period is out of range."
            ) from exc

        previous = {
            "start": past_start.isoformat(),
            "end": past_end.isoformat(),
        }

    else:
        previous, past_days = _period(
            compare_start, compare_end
        )

        if (
            past_days != days
            or previous["end"] >= current["start"]
        ):
            raise ValueError(
                "Comparison periods must be disjoint, "
                "ordered and equal-length."
            )

    cache = {}
    scanned = 0
    skipped = 0
    candidates = []

    def evidence_for(metric_id, selected_asset):
        key = (metric_id, selected_asset)

        if key not in cache:
            cache[key] = build_metric_evidence(
                store,
                metric_id=metric_id,
                client_id=client_id,
                allowed_sources=permitted,
                start=current["start"],
                end=current["end"],
                compare_start=previous["start"],
                compare_end=previous["end"],
                asset_id=selected_asset,
            )

        return cache[key]

    for rule in RULES:
        source_key = rule["metric"].split(".", 1)[0]

        if (
            source_key not in permitted
            or get_metric(rule["metric"]) is None
        ):
            continue

        scanned += 1

        main = evidence_for(
            rule["metric"], asset_id
        )

        if not _eligible(
            main,
            metric_id=rule["metric"],
            client_id=client_id,
            current_period=current,
            previous_period=previous,
            asset_id=asset_id,
        ):
            skipped += 1
            continue

        now_value = _number(
            main["result"]["value"]
        )
        old_value = _number(
            main["comparison"]["previous_value"]
        )

        if (
            old_value <= 0
            or old_value < rule["min_previous"]
        ):
            skipped += 1
            continue

        change = now_value - old_value

        if rule["kind"] == "relative":
            magnitude = abs(change) / old_value
        else:
            magnitude = abs(change)

        moved = (
            change < 0
            if rule["direction"] == "down"
            else change > 0
        )

        if (
            not moved
            or magnitude < rule["threshold"]
        ):
            skipped += 1
            continue

        support = [main]

        # Some rules need minimum sample volumes.
        if "guard_metric" in rule:
            guard_id = rule["guard_metric"]

            if get_metric(guard_id) is None:
                skipped += 1
                continue

            guard = evidence_for(
                guard_id,
                main["scope"]["asset_id"],
            )

            if not _eligible(
                guard,
                metric_id=guard_id,
                client_id=client_id,
                current_period=current,
                previous_period=previous,
                asset_id=main["scope"]["asset_id"],
            ):
                skipped += 1
                continue

            if (
                _number(
                    guard["result"]["value"]
                ) < rule["guard_min"]
                or _number(
                    guard["comparison"]["previous_value"]
                ) < rule["guard_min"]
            ):
                skipped += 1
                continue

            support.append(guard)

        fingerprint = json.dumps(
            {
                "rule": rule["id"],
                "client": client_id,
                "asset": main["scope"]["asset_id"],
                "period": current,
                "comparison": previous,
                "evidence_ids": [
                    item["evidence_id"]
                    for item in support
                ],
            },
            sort_keys=True,
        )

        opportunity_id = hashlib.sha256(
            fingerprint.encode()
        ).hexdigest()[:32]

        candidates.append({
            "id": opportunity_id,
            "rule_id": rule["id"],
            "source": source_key,
            "asset_id": main["scope"]["asset_id"],
            "status": "candidate_unverified",
            "review_required": True,
            "publishable": False,
            "priority": "review",
            "title": rule["title"],
            "interpretation": (
                "Measured period-over-period movement "
                "crossed a review threshold. "
                "It does not establish cause, "
                "future upside or ROI."
            ),
            "suggested_action": rule["action"],
            "metric": {
                "id": rule["metric"],
                "label": main["metric"]["label"],
                "unit": main["metric"]["unit"],
            },
            "signal": {
                "current_value": now_value,
                "previous_value": old_value,
                "change": change,
                "change_percent": (
                    change / old_value
                ) * 100,
                "change_percentage_points": (
                    change * 100
                    if main["metric"]["unit"] == "ratio"
                    else None
                ),
                "threshold_kind": rule["kind"],
                "threshold": rule["threshold"],
            },
            "evidence": [
                {
                    "id": item["evidence_id"],
                    "metric_id": item["metric"]["id"],
                    "sync_run_ids": (
                        item["lineage"]["sync_run_ids"]
                    ),
                    "previous_sync_run_ids": (
                        item["comparison"]["lineage"][
                            "sync_run_ids"
                        ]
                    ),
                }
                for item in support
            ],
        })

    return {
        "schema_version": "1.0",
        "mode": "internal_review",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "client_id": client_id,
        "period": current,
        "comparison_period": previous,
        "source_filter": source,
        "publishable": False,
        "data_origin": "persisted_unverified",
        "summary": {
            "evaluated_rules": scanned,
            "skipped_rules": skipped,
            "candidate_count": len(candidates),
        },
        "opportunities": candidates,
        "note": (
            "Internal review candidates, not verified "
            "customer claims. Empty results mean no "
            "eligible rule signal, not no growth potential."
        ),
    }
