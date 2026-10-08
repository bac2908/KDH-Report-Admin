
"""Internal read-only preview for multi-platform marketing reports.

This is NOT a Dataset or a published Report Bundle.
Unverified evidence and opportunities must never be
presented automatically as approved customer claims.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from flask import g, jsonify, request

from .core import Problem
from .evidence_engine import build_metric_evidence
from .metric_catalog import SOURCES, get_metric
from .metric_reader import MAX_PERIOD_DAYS, _day
from .metric_routes import permitted_metric_sources
from .opportunity_engine import build_opportunities
from .platform_data import DEFAULT_CLIENT_ID


# Initial Executive Preview selection.
# The full Metric Catalog remains available separately.
# Unknown IDs remain visible as not_defined, not fabricated.
PREVIEW_METRICS = {
    "ga4": (
        "ga4.sessions",
        "ga4.active_users",
        "ga4.page_views",
    ),
    "gsc": (
        "gsc.clicks",
        "gsc.impressions",
        "gsc.ctr",
    ),
    "keywords": (
        "keywords.top10",
    ),
    "google_ads": (
        "google_ads.spend",
        "google_ads.clicks",
        "google_ads.conversions",
    ),
    "facebook_ads": (
        "facebook_ads.spend",
        "facebook_ads.leads",
        "facebook_ads.cpl",
    ),
    "facebook_content": (
        "facebook_content.engagements",
    ),
    "instagram": (
        "instagram.engagements",
    ),
    "tiktok_ads": (
        "tiktok_ads.spend",
        "tiktok_ads.conversions",
        "tiktok_ads.cost_per_conversion",
    ),
    "tiktok_organic": (
        "tiktok_organic.views",
    ),
    "youtube": (
        "youtube.views",
    ),
    "gmb": (
        "gmb.website_clicks",
    ),
    "crm": (
        "crm.qualified_leads",
    ),
}


def _period(start, end):
    first = _day(start, "start")
    last = _day(end, "end")
    days = (last - first).days + 1

    if not 1 <= days <= MAX_PERIOD_DAYS:
        raise ValueError("Invalid report period.")

    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
    }, days


def _previous_period(period, days):
    first = date.fromisoformat(period["start"])

    try:
        previous_end = first - timedelta(days=1)
        previous_start = previous_end - timedelta(
            days=days - 1
        )
    except OverflowError as exc:
        raise ValueError(
            "Comparison period is out of range."
        ) from exc

    return {
        "start": previous_start.isoformat(),
        "end": previous_end.isoformat(),
    }


def build_marketing_preview(
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
    """Build internal preview without database writes."""

    if (
        not isinstance(client_id, str)
        or not client_id.strip()
    ):
        raise ValueError("client_id is required.")

    if (
        allowed_sources is None
        or isinstance(allowed_sources, (str, bytes))
    ):
        raise PermissionError(
            "Valid source permissions are required."
        )

    permitted = set(allowed_sources) & set(SOURCES)

    if source is not None:
        if source not in SOURCES:
            raise ValueError("Unknown source.")

        if source not in permitted:
            raise PermissionError("Source not permitted.")

        selected = [source]
    else:
        selected = [
            key for key in PREVIEW_METRICS
            if key in permitted and key in SOURCES
        ]

    if asset_id is not None:
        if (
            not isinstance(asset_id, str)
            or not asset_id.strip()
        ):
            raise ValueError("Invalid asset_id.")

        if source is None:
            raise ValueError(
                "asset_id requires a selected source."
            )

    period, days = _period(start, end)

    if (compare_start is None) != (compare_end is None):
        raise ValueError(
            "Both comparison dates are required."
        )

    if compare_start is None:
        comparison = _previous_period(period, days)
    else:
        comparison, previous_days = _period(
            compare_start, compare_end
        )

        if (
            previous_days != days
            or comparison["end"] >= period["start"]
        ):
            raise ValueError(
                "Comparison must be earlier "
                "and have the same length."
            )

    widgets = []
    evidence_cards = []

    for source_key in selected:
        for metric_id in PREVIEW_METRICS.get(
            source_key, ()
        ):
            meta = get_metric(metric_id)

            if meta is None:
                widgets.append({
                    "type": "kpi",
                    "metric_id": metric_id,
                    "source": source_key,
                    "status": "not_defined",
                    "value": None,
                    "evidence_id": None,
                    "verified": False,
                })
                continue

            evidence = build_metric_evidence(
                store,
                metric_id=metric_id,
                client_id=client_id,
                allowed_sources=set(selected),
                start=period["start"],
                end=period["end"],
                compare_start=comparison["start"],
                compare_end=comparison["end"],
                asset_id=asset_id,
            )

            result = evidence.get("result") or {}
            quality = evidence.get("quality") or {}
            scope = evidence.get("scope") or {}

            eligible = (
                result.get("status") == "available"
                and result.get("evidence_status")
                == "recorded_unverified"
                and quality.get("data_origin")
                == "persisted_unverified"
                and quality.get("is_demo") is not True
            )

            value = (
                result.get("value")
                if eligible else None
            )

            card = {
                "type": "kpi",
                "metric_id": metric_id,
                "label": meta["label"],
                "unit": meta["unit"],
                "source": source_key,
                "asset_id": scope.get("asset_id"),
                "status": result.get(
                    "status", "unavailable"
                ),
                "evidence_status": result.get(
                    "evidence_status", "not_ready"
                ),
                "value": value,
                "evidence_id": evidence.get(
                    "evidence_id"
                ),
                "verified": False,
                "publishable": False,
                "warnings": quality.get(
                    "warnings", []
                ),
            }
            widgets.append(card)

            if eligible:
                evidence_cards.append({
                    "evidence_id": evidence.get(
                        "evidence_id"
                    ),
                    "metric_id": metric_id,
                    "source": source_key,
                    "asset_id": scope.get("asset_id"),
                    "period": period,
                    "value": value,
                    "lineage": evidence.get(
                        "lineage", {}
                    ),
                    "status": "recorded_unverified",
                    "verified": False,
                    "publishable": False,
                })

    if selected:
        raw_opportunities = build_opportunities(
            store,
            client_id=client_id,
            allowed_sources=set(selected),
            start=period["start"],
            end=period["end"],
            compare_start=comparison["start"],
            compare_end=comparison["end"],
            source=source,
            asset_id=asset_id,
        )

        candidates = []

        for item in raw_opportunities.get(
            "opportunities", []
        ):
            candidates.append({
                "id": item.get("id"),
                "rule_id": item.get("rule_id"),
                "source": item.get("source"),
                "title": item.get("title"),
                "signal": item.get("signal"),
                "evidence": item.get("evidence", []),
                "suggested_action": item.get(
                    "suggested_action"
                ),
                "status": "candidate_unverified",
                "review_required": True,
                "publishable": False,
            })
    else:
        candidates = []

    available = sum(
        item.get("value") is not None
        for item in widgets
    )

    return {
        "preview_schema_version": "0.1",
        "kind": "marketing_internal_preview",
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "client_id": client_id,
        "period": period,
        "comparison": comparison,
        "sources": selected,
        "source_filter": source,
        "asset_id": asset_id,
        "quality": {
            "status": (
                "unverified_with_data"
                if available else "no_eligible_data"
            ),
            "independently_verified": False,
            "ready_for_customer_claims": False,
        },
        "summary": {
            "widget_count": len(widgets),
            "widgets_with_values": available,
            "evidence_count": len(evidence_cards),
            "opportunity_count": len(candidates),
        },
        "widgets": widgets,
        "evidence_cards": evidence_cards,
        "opportunity_candidates": candidates,
        "publishable": False,
        "not_a_report_bundle": True,
        "note": (
            "Internal preview only. Not verified "
            "and not approved for client publication."
        ),
    }


def register_marketing_preview_routes(
    app, store, require
):
    """Register an admin/operator-only preview API."""

    @app.get("/api/marketing/preview")
    @require("admin", "operator")
    def api_marketing_preview():
        accepted = {
            "start",
            "end",
            "compare_start",
            "compare_end",
            "source",
            "asset_id",
        }

        if (
            set(request.args) - accepted
            or any(
                len(request.args.getlist(key)) != 1
                for key in request.args
            )
            or not request.args.get("start")
            or not request.args.get("end")
        ):
            raise Problem(
                "Tham so bao cao khong hop le.",
                400,
                "invalid_preview_query",
            )

        permitted = permitted_metric_sources(g.user)

        try:
            payload = build_marketing_preview(
                store,
                client_id=DEFAULT_CLIENT_ID,
                allowed_sources=permitted,
                start=request.args["start"],
                end=request.args["end"],
                compare_start=request.args.get(
                    "compare_start"
                ),
                compare_end=request.args.get(
                    "compare_end"
                ),
                source=request.args.get("source"),
                asset_id=request.args.get("asset_id"),
            )

        except PermissionError:
            raise Problem(
                "Khong co quyen xem nguon du lieu.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_preview_query",
            ) from None

        return jsonify(payload)
