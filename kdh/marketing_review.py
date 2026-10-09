
"""Admin-only review of internal Marketing Datasets.

Internal approval does not verify provider authenticity
or authorize publication to KDH-Report-New.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re

from flask import g, jsonify

from .core import Problem, now, pack, uid
from .platform_data import DEFAULT_CLIENT_ID
from .report_bundles import _check_no_credentials


DECISIONS = {"needs_changes", "approved_internal"}


def _dataset(db, dataset_id):
    if (
        not isinstance(dataset_id, str)
        or not re.fullmatch(r"[0-9a-f]{32}", dataset_id)
    ):
        raise Problem(
            "Dataset ID khong hop le.",
            400,
            "invalid_dataset_id",
        )

    row = db.execute(
        """
        SELECT id, user_id, report_type, valid, data
        FROM datasets
        WHERE id=?
        """,
        (dataset_id,),
    ).fetchone()

    if not row:
        raise Problem(
            "Khong tim thay Dataset.",
            404,
            "dataset_not_found",
        )

    try:
        data = json.loads(row["data"])
    except (TypeError, ValueError):
        raise Problem(
            "Dataset JSON khong hop le.",
            409,
            "invalid_review_snapshot",
        ) from None

    if (
        not isinstance(data, dict)
        or data.get("dataset_kind")
        != "marketing_internal_preview_v1"
    ):
        raise Problem(
            "Dataset khong thuoc luong Marketing Review.",
            409,
            "not_marketing_dataset",
        )

    if data.get("client_id") != DEFAULT_CLIENT_ID:
        raise Problem(
            "Dataset khong thuoc khach hang hien tai.",
            404,
            "dataset_not_found",
        )

    _check_no_credentials(data)
    return row, data


def _assess(row, data):
    """Check stored snapshot without modifying it."""
    issues = []

    def check(condition, code):
        if not condition:
            issues.append(code)

    marketing = data.get("marketing")
    marketing = marketing if isinstance(marketing, dict) else {}

    preview = marketing.get("preview")
    preview = preview if isinstance(preview, dict) else {}

    params = data.get("params")
    params = params if isinstance(params, dict) else {}

    sources = data.get("sources")
    sources = sources if isinstance(sources, dict) else {}

    summary = preview.get("summary")
    summary = summary if isinstance(summary, dict) else {}

    quality = preview.get("quality")
    quality = quality if isinstance(quality, dict) else {}

    source = params.get("source")
    source_data = (
        sources.get(source)
        if isinstance(source, str)
        else None
    )

    period = {
        "start": params.get("start"),
        "end": params.get("end"),
    }

    comparison = {
        "start": params.get("previous_start"),
        "end": params.get("previous_end"),
    }

    # Dataset must remain the internal snapshot
    # created by Step 8.8.2.
    check(row["valid"] == 0, "dataset_not_internal")
    check(
        data.get("data_origin") == "persisted_unverified",
        "untrusted_origin",
    )
    check(params.get("compare") is True, "comparison_required")
    check(params.get("demo") is not True, "demo_data")
    check(
        params.get("report_type") == row["report_type"],
        "report_type_mismatch",
    )

    check(isinstance(source_data, dict), "source_missing")

    if isinstance(source_data, dict):
        check(
            source_data.get("status") == "incomplete",
            "invalid_source_status",
        )
        check(
            source_data.get("requested_start") == period["start"],
            "source_period_mismatch",
        )
        check(
            source_data.get("requested_end") == period["end"],
            "source_period_mismatch",
        )

    check(
        marketing.get("kind") == "internal_review_snapshot",
        "invalid_marketing_metadata",
    )
    check(
        marketing.get("review_status") == "pending",
        "invalid_marketing_metadata",
    )
    check(
        marketing.get("verified") is False,
        "unsafe_verified_flag",
    )
    check(
        marketing.get("publishable") is False,
        "unsafe_publish_flag",
    )

    # Check Preview contract and its scope.
    check(
        preview.get("preview_schema_version") == "0.1",
        "preview_schema_mismatch",
    )
    check(
        preview.get("kind") == "marketing_internal_preview",
        "invalid_preview",
    )
    check(
        preview.get("client_id") == DEFAULT_CLIENT_ID,
        "client_mismatch",
    )
    check(
        preview.get("source_filter") == source,
        "source_mismatch",
    )
    check(
        preview.get("sources") == [source],
        "source_mismatch",
    )
    check(preview.get("period") == period, "period_mismatch")
    check(
        preview.get("comparison") == comparison,
        "comparison_mismatch",
    )
    check(
        preview.get("publishable") is False,
        "unsafe_publish_flag",
    )
    check(
        preview.get("not_a_report_bundle") is True,
        "unsafe_preview",
    )
    check(
        quality.get("independently_verified") is False,
        "unsafe_verified_flag",
    )
    check(
        quality.get("ready_for_customer_claims") is False,
        "unsafe_claim_flag",
    )
    check(
        quality.get("is_demo") is not True,
        "demo_data",
    )
    check(
        quality.get("status") in (
            "unverified_with_data",
            "no_eligible_data",
        ),
        "invalid_preview_quality",
    )

    # Detect accidental/tampered changes to Preview.
    actual_preview_hash = hashlib.sha256(
        pack(preview).encode("utf-8")
    ).hexdigest()

    expected_preview_hash = marketing.get("preview_sha256")

    check(
        isinstance(expected_preview_hash, str)
        and hmac.compare_digest(
            expected_preview_hash,
            actual_preview_hash,
        ),
        "preview_hash_mismatch",
    )

    widgets = preview.get("widgets")
    evidence = preview.get("evidence_cards")
    opportunities = preview.get("opportunity_candidates")

    check(isinstance(widgets, list), "invalid_widgets")
    check(isinstance(evidence, list), "invalid_evidence")
    check(
        isinstance(opportunities, list),
        "invalid_opportunities",
    )

    widgets = widgets if isinstance(widgets, list) else []
    evidence = evidence if isinstance(evidence, list) else []
    opportunities = (
        opportunities
        if isinstance(opportunities, list)
        else []
    )

    if any(
        not isinstance(item, dict)
        or item.get("source") != source
        or item.get("verified") is True
        or item.get("publishable") is True
        for item in widgets
    ):
        issues.append("unsafe_widget")

    if any(
        not isinstance(item, dict)
        or item.get("status") != "recorded_unverified"
        or item.get("source") != source
        or item.get("verified") is not False
        or item.get("publishable") is not False
        or not isinstance(item.get("evidence_id"), str)
        or not isinstance(item.get("lineage"), dict)
        or not isinstance(
            item["lineage"].get("sync_run_ids"), list
        )
        or not any(
            isinstance(run, str) and run
            for run in item["lineage"]["sync_run_ids"]
        )
        for item in evidence
    ):
        issues.append("invalid_evidence_lineage")

    if any(
        not isinstance(item, dict)
        or item.get("status") != "candidate_unverified"
        or item.get("source") != source
        or item.get("review_required") is not True
        or item.get("publishable") is not False
        for item in opportunities
    ):
        issues.append("unsafe_opportunity")

    # Counters must agree with actual snapshot content.
    check(
        summary.get("widget_count") == len(widgets),
        "preview_count_mismatch",
    )
    check(
        summary.get("widgets_with_values") == sum(
            isinstance(item, dict)
            and item.get("value") is not None
            for item in widgets
        ),
        "preview_count_mismatch",
    )
    check(
        summary.get("evidence_count") == len(evidence),
        "preview_count_mismatch",
    )
    check(
        summary.get("opportunity_count") == len(opportunities),
        "preview_count_mismatch",
    )

    if (
        evidence
        and quality.get("status") != "unverified_with_data"
    ):
        issues.append("invalid_preview_quality")

    snapshot_hash = hashlib.sha256(
        row["data"].encode("utf-8")
    ).hexdigest()

    unique_issues = list(dict.fromkeys(issues))

    value_count = summary.get("widgets_with_values", 0)

    has_evidence = (
        bool(evidence)
    and type(value_count) is int
    and value_count > 0
    )

    can_approve = not unique_issues and has_evidence

    return {
        "dataset_id": row["id"],
        "client_id": DEFAULT_CLIENT_ID,
        "source": source,
        "dataset_sha256": snapshot_hash,
        "review_status": (
            "invalid_snapshot"
            if unique_issues
            else (
                "awaiting_review"
                if has_evidence
                else "needs_data"
            )
        ),
        "checks": {
            "snapshot_valid": not unique_issues,
            "has_traceable_evidence": has_evidence,
            "can_approve_internal": can_approve,
            "provider_verified": False,
            "can_publish_provisional": False,
            "can_publish_final": False,
        },
        "summary": {
            "widget_count": len(widgets),
            "evidence_count": len(evidence),
            "opportunity_count": len(opportunities),
        },
        "issues": unique_issues,
        "note": (
            "Internal review is not provider verification "
            "or publication approval."
        ),
    }


def read_marketing_review(store, dataset_id):
    """Read current assessment and latest audit decision."""
    with store.connect() as db:
        row, data = _dataset(db, dataset_id)
        result = _assess(row, data)

        latest = db.execute(
            """
            SELECT id, decision, note, reviewer_id,
                   dataset_sha256, created_at
            FROM marketing_dataset_reviews
            WHERE dataset_id=?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (dataset_id,),
        ).fetchone()

    result["latest_review"] = None

    if latest is not None:
        result["latest_review"] = {
            "id": latest["id"],
            "decision": latest["decision"],
            "note": latest["note"],
            "reviewer_id": latest["reviewer_id"],
            "created_at": latest["created_at"],
            "matches_current_snapshot": hmac.compare_digest(
                latest["dataset_sha256"],
                result["dataset_sha256"],
            ),
        }

    return result


def submit_marketing_review(
    store,
    *,
    dataset_id,
    reviewer_id,
    body,
):
    """Append an audited INTERNAL decision; never publish."""
    if (
        not isinstance(body, dict)
        or set(body) != {
            "decision",
            "note",
            "expected_sha256",
        }
    ):
        raise Problem(
            "Truong review khong hop le.",
            400,
            "invalid_review_input",
        )

    decision = body["decision"]
    note = body["note"]
    expected_hash = body["expected_sha256"]

    if (
        not isinstance(decision, str) 
        or decision not in DECISIONS
        or not isinstance(note, str)
        or not 10 <= len(note.strip()) <= 500
    ):
        raise Problem(
            "Quyet dinh hoac ghi chu khong hop le.",
            400,
            "invalid_review_input",
        )

    if (
        not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
    ):
        raise Problem(
            "Dataset hash khong hop le.",
            400,
            "invalid_review_input",
        )

    _check_no_credentials({"review_note": note})

    # All checks and writes belong to one transaction.
    with store.connect(immediate=True) as db:
        user = db.execute(
            "SELECT role, active FROM users WHERE id=?",
            (reviewer_id,),
        ).fetchone()

        if (
            not user
            or user["role"] != "admin"
            or not user["active"]
        ):
            raise Problem(
                "Can tai khoan Admin dang hoat dong.",
                403,
                "admin_required",
            )

        row, data = _dataset(db, dataset_id)
        result = _assess(row, data)

        if not hmac.compare_digest(
            expected_hash,
            result["dataset_sha256"],
        ):
            raise Problem(
                "Dataset da thay doi; vui long kiem tra lai.",
                409,
                "stale_review",
            )

        if result["issues"]:
            raise Problem(
                "Dataset metadata khong hop le.",
                409,
                "invalid_review_snapshot",
            )

        if (
            decision == "approved_internal"
            and not result["checks"]["can_approve_internal"]
        ):
            raise Problem(
                "Chua du bang chung de duyet noi bo.",
                409,
                "insufficient_evidence",
            )

        review_id = uid()
        created_at = now()

        db.execute(
            """
            INSERT INTO marketing_dataset_reviews (
                id, dataset_id, client_id, reviewer_id,
                dataset_sha256, decision, note, created_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                review_id,
                dataset_id,
                DEFAULT_CLIENT_ID,
                reviewer_id,
                result["dataset_sha256"],
                decision,
                note.strip(),
                created_at,
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
                reviewer_id,
                "review_marketing_dataset",
                created_at,
                pack({
                    "dataset_id": dataset_id,
                    "review_id": review_id,
                    "decision": decision,
                }),
            ),
        )

    return {
        "review_id": review_id,
        "dataset_id": dataset_id,
        "decision": decision,
        "created_at": created_at,
        "dataset_sha256": result["dataset_sha256"],
        "provider_verified": False,
        "publishable": False,
        "message": (
            "Da luu duyet noi bo; "
            "chua cho phep xuat ban Report Bundle."
        ),
    }


def register_marketing_review_routes(
    app,
    store,
    require,
    body,
):
    @app.get("/api/marketing/datasets/<dataset_id>/review")
    @require("admin")
    def api_marketing_review_get(dataset_id):
        return jsonify(
            read_marketing_review(store, dataset_id)
        )

    @app.post("/api/marketing/datasets/<dataset_id>/review")
    @require("admin")
    def api_marketing_review_submit(dataset_id):
        result = submit_marketing_review(
            store,
            dataset_id=dataset_id,
            reviewer_id=g.user["id"],
            body=body(),
        )
        return jsonify(result), 201
