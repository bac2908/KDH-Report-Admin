
"""Create internal Marketing Datasets from the verified code path.

The input comes from authenticated server-side preview logic.
Dataset creation is insert-only. No provider calls, mock
fallback, report publication or legacy dataset mutation.
"""

from __future__ import annotations

import hashlib

from flask import g, jsonify

from .core import TYPES, Problem, now, pack, uid
from .marketing_preview import build_marketing_preview
from .metric_catalog import SOURCES
from .metric_routes import permitted_metric_sources
from .platform_data import DEFAULT_CLIENT_ID
from .report_bundles import _check_no_credentials


# Map normalized Marketing sources to EXISTING report types.
# Other sources will be enabled when their report types,
# access rules and bundle mappings are introduced.
SOURCE_REPORT_TYPES = {
    "ga4": "ga4",
    "gsc": "gsc",
    "keywords": "keywords",
    "facebook_ads": "facebook-ads",
    "facebook_content": "facebook-content",
    "tiktok_ads": "tiktok",
    "gmb": "gmb",
}

MAX_DATASET_BYTES = 1024 * 1024

ALLOWED_FIELDS = {
    "source",
    "start",
    "end",
    "compare_start",
    "compare_end",
    "asset_id",
}


def _validate_input(payload):
    if not isinstance(payload, dict):
        raise Problem(
            "Dataset input must be a JSON object.",
            400,
            "invalid_dataset_input",
        )

    if set(payload) - ALLOWED_FIELDS:
        raise Problem(
            "Unsupported Dataset input fields.",
            400,
            "invalid_dataset_input",
        )

    for key in ("source", "start", "end"):
        value = payload.get(key)

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise Problem(
                f"Missing or invalid field: {key}",
                400,
                "invalid_dataset_input",
            )

    for key in (
        "compare_start",
        "compare_end",
        "asset_id",
    ):
        if key in payload:
            value = payload[key]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise Problem(
                    f"Invalid field: {key}",
                    400,
                    "invalid_dataset_input",
                )

    if (
        ("compare_start" in payload)
        != ("compare_end" in payload)
    ):
        raise Problem(
            "Both comparison dates are required.",
            400,
            "invalid_dataset_input",
        )

    return payload


def _validate_internal_preview(
    preview,
    *,
    client_id,
    source,
):
    """Fail closed if preview stops being internal-only."""

    if not isinstance(preview, dict):
        raise Problem(
            "Invalid Marketing Preview.",
            409,
            "unsafe_marketing_preview",
        )

    quality = preview.get("quality")

    if not isinstance(quality, dict):
        raise Problem(
            "Marketing Preview lacks quality metadata.",
            409,
            "unsafe_marketing_preview",
        )

    safe = (
        preview.get("preview_schema_version") == "0.1"
        and preview.get("kind")
        == "marketing_internal_preview"
        and preview.get("client_id") == client_id
        and preview.get("source_filter") == source
        and preview.get("sources") == [source]
        and preview.get("publishable") is False
        and preview.get("not_a_report_bundle") is True
        and quality.get("independently_verified")
        is False
        and quality.get("ready_for_customer_claims")
        is False
    )

    if not safe:
        raise Problem(
            "Preview is not eligible for an "
            "internal-only Dataset.",
            409,
            "unsafe_marketing_preview",
        )

    period = preview.get("period")
    comparison = preview.get("comparison")

    if (
        not isinstance(period, dict)
        or not isinstance(comparison, dict)
        or not all(
            isinstance(period.get(key), str)
            for key in ("start", "end")
        )
        or not all(
            isinstance(comparison.get(key), str)
            for key in ("start", "end")
        )
    ):
        raise Problem(
            "Invalid Preview periods.",
            409,
            "unsafe_marketing_preview",
        )


def create_marketing_dataset(
    store,
    *,
    actor_id,
    allowed_sources,
    payload,
    client_id=DEFAULT_CLIENT_ID,
):
    """Insert one new internal-only Dataset snapshot."""

    data = _validate_input(payload)
    source = data["source"]

    if (
        not isinstance(client_id, str)
        or client_id != DEFAULT_CLIENT_ID
    ):
        raise Problem(
            "Client is not supported by this builder.",
            403,
            "client_not_allowed",
        )

    if (
        allowed_sources is None
        or isinstance(allowed_sources, (str, bytes))
    ):
        raise Problem(
            "Invalid source permissions.",
            403,
            "forbidden_source",
        )

    permitted = set(allowed_sources)

    if source not in SOURCES:
        raise Problem(
            "Unknown Marketing source.",
            400,
            "invalid_source",
        )

    if source not in permitted:
        raise Problem(
            "Source is not permitted.",
            403,
            "forbidden_source",
        )

    report_type = SOURCE_REPORT_TYPES.get(source)

    if report_type not in TYPES:
        raise Problem(
            "This source is in the Metric Catalog "
            "but does not have a compatible legacy "
            "Report Type yet.",
            409,
            "report_type_not_ready",
        )

    preview = build_marketing_preview(
        store,
        client_id=client_id,
        allowed_sources={source},
        source=source,
        start=data["start"],
        end=data["end"],
        compare_start=data.get("compare_start"),
        compare_end=data.get("compare_end"),
        asset_id=data.get("asset_id"),
    )

    _validate_internal_preview(
        preview,
        client_id=client_id,
        source=source,
    )

    preview_json = pack(preview)

    if (
        len(preview_json.encode("utf-8"))
        > MAX_DATASET_BYTES
    ):
        raise Problem(
            "Marketing Preview is too large.",
            413,
            "dataset_too_large",
        )

    period = preview["period"]
    previous = preview["comparison"]

    created_at = now()
    dataset_id = uid()

    source_spec = SOURCES[source]

    # Legacy-compatible Dataset shape:
    # id, client_id, params, sources, created_at.
    #
    # Explicitly incomplete and valid=0, regardless
    # of how many internal KPI observations exist.
    dataset = {
        "id": dataset_id,
        "client_id": client_id,
        "created_at": created_at,
        "dataset_kind": (
            "marketing_internal_preview_v1"
        ),
        "data_origin": "persisted_unverified",
        "params": {
            "report_type": report_type,
            "start": period["start"],
            "end": period["end"],
            "compare": True,
            "previous_start": previous["start"],
            "previous_end": previous["end"],
            "source": source,
        },
        "sources": {
            source: {
                "source": source,
                "label": source_spec.get(
                    "label", source
                ),
                "status": "incomplete",
                "requested_start": period["start"],
                "requested_end": period["end"],
                "latest_available_date": None,
                "fetched_at": None,
                "asset": data.get("asset_id"),
                "totals": {},
                "daily": [],
                "previous": None,
                "warnings": [
                    "Internal Dataset: provider "
                    "authenticity is not verified.",
                    "Not approved for FINAL report "
                    "or customer-facing claims.",
                ],
            }
        },
        "marketing": {
            "schema_version": "0.1",
            "kind": "internal_review_snapshot",
            "review_status": "pending",
            "verified": False,
            "publishable": False,
            "preview_sha256": hashlib.sha256(
                preview_json.encode("utf-8")
            ).hexdigest(),
            "preview": preview,
        },
    }

    # Prevent credential-bearing data from entering
    # datasets or future Report Bundle snapshots.
    _check_no_credentials(dataset)

    serialized = pack(dataset)

    if (
        len(serialized.encode("utf-8"))
        > MAX_DATASET_BYTES
    ):
        raise Problem(
            "Marketing Dataset is too large.",
            413,
            "dataset_too_large",
        )

    # Insert and audit atomically.
    # No UPDATE, DELETE or migration.
    with store.connect(immediate=True) as db:
        user = db.execute(
            """
            SELECT role, active
            FROM users
            WHERE id=?
            """,
            (actor_id,),
        ).fetchone()

        if (
            not user
            or not user["active"]
            or user["role"] != "admin"
        ):
            raise Problem(
                "Active Admin account required.",
                403,
                "admin_required",
            )

        client = db.execute(
            """
            SELECT id FROM clients
            WHERE id=? AND active=1
            """,
            (client_id,),
        ).fetchone()

        if not client:
            raise Problem(
                "Client not available.",
                404,
                "client_not_found",
            )

        db.execute(
            """
            INSERT INTO datasets (
                id,
                user_id,
                report_type,
                created_at,
                valid,
                data
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                dataset_id,
                actor_id,
                report_type,
                created_at,
                0,
                serialized,
            ),
        )

        db.execute(
            """
            INSERT INTO events (
                id, user_id, action, at, detail
            ) VALUES (?,?,?,?,?)
            """,
            (
                uid(),
                actor_id,
                "create_marketing_dataset",
                now(),
                pack({
                    "dataset_id": dataset_id,
                    "source": source,
                    "report_type": report_type,
                    "valid": False,
                }),
            ),
        )

    return {
        "dataset_id": dataset_id,
        "client_id": client_id,
        "report_type": report_type,
        "source": source,
        "created_at": created_at,
        "valid": False,
        "exportable": False,
        "publishable": False,
        "review_status": "pending",
        "data_origin": "persisted_unverified",
        "preview_summary": preview.get(
            "summary", {}
        ),
    }


def register_marketing_dataset_routes(
    app, store, require, body
):
    """Register the Admin-only Dataset creation endpoint."""

    @app.post("/api/marketing/datasets")
    @require("admin")
    def api_create_marketing_dataset():
        data = body()

        try:
            result = create_marketing_dataset(
                store,
                actor_id=g.user["id"],
                allowed_sources=(
                    permitted_metric_sources(g.user)
                ),
                payload=data,
            )
        except PermissionError:
            raise Problem(
                "You cannot access this source.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_dataset_input",
            ) from None

        return jsonify(result), 201
