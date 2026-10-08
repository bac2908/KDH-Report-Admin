
"""Read normalized multi-platform trends for Admin Overview.

Read-only. No provider calls and no mock fallback.
"""

import json
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .core import TZ
from .platform_data import DEFAULT_CLIENT_ID


# Shared daily-summary contract.
#
# Entries other than GA4/GSC define the target normalized
# storage format for future platform adapters.
#
# Every chart-ready daily summary must use:
#   entity_id = ""
#   dimension_key = ""
#
# Campaign/post/keyword detail rows must not be summed here.

SOURCE_SPECS = {
    "ga4": {
        "provider": "google",
        "asset_type": "ga4_property",
        "entity_type": "website",
        "default_metric": "sessions",
        "fields": (
            "sessions", "active_users",
            "page_views", "engagement_rate",
        ),
    },
    "gsc": {
        "provider": "google",
        "asset_type": "search_console_property",
        "entity_type": "website",
        "default_metric": "clicks",
        "fields": (
            "clicks", "impressions", "ctr", "position",
        ),
    },
    "keywords": {
        "provider": "google",
        "asset_type": "keyword_sheet",
        "entity_type": "keyword_summary",
        "default_metric": "top10",
        "fields": ("top3", "top10", "top20"),
    },
    "facebook-ads": {
        "provider": "meta",
        "asset_type": "facebook_ad_account",
        "entity_type": "ad_account",
        "default_metric": "spend",
        "fields": (
            "spend", "reach", "impressions",
            "clicks", "results",
        ),
    },
    "facebook-content": {
        "provider": "meta",
        "asset_type": "facebook_page",
        "entity_type": "page",
        "default_metric": "reach",
        "fields": (
            "reach", "engagements", "post_count",
        ),
    },
    "tiktok": {
        "provider": "tiktok",
        "asset_type": "tiktok_ad_account",
        "entity_type": "ad_account",
        "default_metric": "spend",
        "fields": (
            "spend", "impressions", "clicks",
            "views", "conversions",
        ),
    },
    "youtube": {
        "provider": "youtube",
        "asset_type": "youtube_channel",
        "entity_type": "channel",
        "default_metric": "views",
        "fields": (
            "views", "watch_time_minutes",
            "subscribers_gained",
        ),
    },
    "gmb": {
        "provider": "gmb",
        "asset_type": "business_location",
        "entity_type": "location",
        "default_metric": "views",
        "fields": (
            "views", "calls", "directions",
            "website_clicks",
        ),
    },
}


def _read_metrics(raw):
    try:
        result = raw if isinstance(raw, dict) else json.loads(raw)
    except (TypeError, ValueError):
        return {}

    return result if isinstance(result, dict) else {}


def _valid_number(value):
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


def load_overview_trend(
    store,
    *,
    client_id=DEFAULT_CLIENT_ID,
    allowed_sources=(),
    days=28,
    end_date=None,
):
    """Return only eligible persisted daily series."""

    if not isinstance(days, int) or isinstance(days, bool):
        raise ValueError("Invalid period.")

    if not 1 <= days <= 180:
        raise ValueError("Period must be between 1 and 180 days.")

    if end_date is None:
        end = datetime.now(ZoneInfo(TZ)).date() - timedelta(days=1)
    elif isinstance(end_date, str):
        end = date.fromisoformat(end_date)
    elif isinstance(end_date, date):
        end = end_date
    else:
        raise ValueError("Invalid end date.")

    start = end - timedelta(days=days - 1)
    start_text = start.isoformat()
    end_text = end.isoformat()

    permitted = set(allowed_sources or ()) & set(SOURCE_SPECS)

    if not permitted:
        return None

    sources = {}
    legacy_daily = {}

    for source_key, spec in SOURCE_SPECS.items():
        if source_key not in permitted:
            continue

        provider = spec["provider"]

        # Do not choose an arbitrary asset if multiple
        # accounts/properties match the same source.
        assets = store.all(
            """
            SELECT id FROM source_assets
            WHERE client_id=?
              AND provider=?
              AND asset_type=?
              AND enabled=1
            ORDER BY id
            """,
            (
                client_id,
                provider,
                spec["asset_type"],
            ),
        )

        if len(assets) != 1:
            continue

        asset_id = assets[0]["id"]

        # The latest overlapping sync must be successful.
        # Do not silently treat an earlier successful sync
        # as the latest valid status after a later failure.
        latest = store.one(
            """
            SELECT status, record_count
            FROM sync_runs
            WHERE client_id=?
              AND asset_id=?
              AND provider=?
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
                client_id, asset_id, provider,
                end_text, start_text,
            ),
        )

        if not latest:
            continue

        if (
            latest["status"] != "succeeded"
            or latest["record_count"] <= 0
        ):
            continue

        rows = store.all(
            """
            SELECT dm.metric_date, dm.metrics
            FROM daily_metrics dm
            JOIN sync_runs sr
              ON sr.id=dm.sync_run_id
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
                provider,
                spec["entity_type"],
                start_text,
                end_text,
            ),
        )

        daily = []

        for row in rows:
            values = _read_metrics(row["metrics"])

            metrics = {
                key: values[key]
                for key in spec["fields"]
                if key in values
                and _valid_number(values[key])
            }

            if not metrics:
                continue

            item = {"date": row["metric_date"], **metrics}
            daily.append(item)

            # Compatibility with Step 7 frontend:
            # GA4 sessions + GSC clicks only.
            if source_key in ("ga4", "gsc"):
                key = spec["default_metric"]
                if key in metrics:
                    legacy_daily.setdefault(
                        row["metric_date"], {}
                    )[key] = metrics[key]

        if not daily:
            continue

        sources[source_key] = {
            "provider": provider,
            "asset_id": asset_id,
            "default_metric": spec["default_metric"],
            "daily": daily,
        }

    if not sources:
        return None

    return {
        "origin": "real",
        "start": start_text,
        "end": end_text,
        "sources": sources,
        "daily": [
            {"date": day, **metrics}
            for day, metrics in sorted(legacy_daily.items())
        ],
    }
