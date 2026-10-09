
"""Stage reviewed Marketing Datasets as internal release candidates.

An internal approval is NOT provider verification.
No publication, provider calls, or updates to source datasets.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re

from flask import g, jsonify

from .core import Problem, now, pack, uid
from .marketing_review import _assess, _dataset
from .report_bundles import _check_no_credentials


MAX_RELEASE_BYTES = 1024 * 1024


def _release_state(db, dataset_id):
    """Read dataset assessment and latest internal approval."""

    row, original = _dataset(db, dataset_id)
    assessment = _assess(row, original)

    latest = db.execute(
        """
        SELECT id, decision, reviewer_id,
               dataset_sha256, created_at
        FROM marketing_dataset_reviews
        WHERE dataset_id=?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (dataset_id,),
    ).fetchone()

    latest = dict(latest) if latest else None

    problems = list(assessment["issues"])

    if not assessment["checks"]["can_approve_internal"]:
        problems.append("internal_evidence_not_ready")

    if latest is None:
        problems.append("review_missing")
    else:
        if latest["decision"] != "approved_internal":
            problems.append("review_not_approved")

        if not hmac.compare_digest(
            latest["dataset_sha256"],
            assessment["dataset_sha256"],
        ):
            problems.append("review_snapshot_mismatch")

    problems = list(dict.fromkeys(problems))

    return row, original, assessment, latest, problems


def read_release_readiness(store, dataset_id):
    """Show whether an internal release candidate can be created."""

    with store.connect() as db:
        row, data, assessment, latest, problems = (
            _release_state(db, dataset_id)
        )

    return {
        "dataset_id": dataset_id,
        "client_id": assessment["client_id"],
        "source": assessment["source"],
        "dataset_sha256": assessment["dataset_sha256"],
        "ready_to_stage": not problems,
        "issues": problems,
        "latest_review": (
            {
                "id": latest["id"],
                "decision": latest["decision"],
                "created_at": latest["created_at"],
                "matches_current_snapshot": (
                    hmac.compare_digest(
                        latest["dataset_sha256"],
                        assessment["dataset_sha256"],
                    )
                ),
            }
            if latest else None
        ),
        "provider_verified": False,
        "publishable": False,
        "next_action": (
            "stage_internal_candidate"
            if not problems
            else "review_or_complete_evidence"
        ),
    }


def create_release_candidate(
    store,
    *,
    dataset_id,
    actor_id,
    payload,
):
    """Create a new Dataset from the reviewed immutable snapshot.

    The resulting Dataset remains valid=0 and non-publishable.
    """

    if (
        not isinstance(payload, dict)
        or set(payload) != {
            "expected_sha256",
            "expected_review_id",
        }
    ):
        raise Problem(
            "Release input khong hop le.",
            400,
            "invalid_release_input",
        )

    expected_hash = payload["expected_sha256"]
    expected_review = payload["expected_review_id"]

    if (
        not isinstance(expected_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
        or not isinstance(expected_review, str)
        or not re.fullmatch(r"[0-9a-f]{32}", expected_review)
    ):
        raise Problem(
            "Release identifiers khong hop le.",
            400,
            "invalid_release_input",
        )

    # Authentication, review validation and INSERT operations
    # all run in one database transaction.
    with store.connect(immediate=True) as db:
        actor = db.execute(
            """
            SELECT role, active
            FROM users
            WHERE id=?
            """,
            (actor_id,),
        ).fetchone()

        if (
            not actor
            or actor["role"] != "admin"
            or not actor["active"]
        ):
            raise Problem(
                "Can tai khoan Admin dang hoat dong.",
                403,
                "admin_required",
            )

        row, original, assessment, latest, problems = (
            _release_state(db, dataset_id)
        )

        if not hmac.compare_digest(
            expected_hash,
            assessment["dataset_sha256"],
        ):
            raise Problem(
                "Dataset da thay doi; kiem tra lai.",
                409,
                "stale_release_snapshot",
            )

        if (
            latest is None
            or not hmac.compare_digest(
                expected_review,
                latest["id"],
            )
        ):
            raise Problem(
                "Review khong con la phien ban moi nhat.",
                409,
                "stale_release_review",
            )

        if problems:
            raise Problem(
                "Chua the tao Release Candidate: "
                + ", ".join(problems),
                409,
                "release_not_ready",
            )

        release_id = uid()
        created_at = now()

        # Make a separate snapshot. Never update the original.
        candidate = copy.deepcopy(original)

        candidate["id"] = release_id
        candidate["created_at"] = created_at
        candidate["dataset_kind"] = (
            "marketing_release_candidate_v1"
        )

        # Keep the original preview and its source lineage.
        # Approval changes review metadata, NOT the actual data.
        candidate["marketing"]["review_status"] = (
            "approved_internal"
        )
        candidate["marketing"]["verified"] = False
        candidate["marketing"]["publishable"] = False

        candidate["release_candidate"] = {
            "schema_version": "0.1",
            "status": "staged_internal",
            "origin_dataset_id": dataset_id,
            "origin_dataset_sha256": (
                assessment["dataset_sha256"]
            ),
            "review_id": latest["id"],
            "review_decision": latest["decision"],
            "reviewed_at": latest["created_at"],
            "prepared_at": created_at,
            "provider_verified": False,
            "publishable": False,
            "approved_claim_ids": [],
        }

        # This remains unverified, including all opportunities.
        candidate["data_origin"] = (
            "persisted_unverified"
        )

        _check_no_credentials(candidate)

        serialized = pack(candidate)

        if len(serialized.encode("utf-8")) > MAX_RELEASE_BYTES:
            raise Problem(
                "Release Candidate qua lon.",
                413,
                "release_too_large",
            )

        db.execute(
            """
            INSERT INTO datasets (
                id, user_id, report_type,
                created_at, valid, data
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                release_id,
                actor_id,
                row["report_type"],
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
                "stage_marketing_release_candidate",
                created_at,
                pack({
                    "source_dataset_id": dataset_id,
                    "release_dataset_id": release_id,
                    "review_id": latest["id"],
                }),
            ),
        )

    return {
        "release_dataset_id": release_id,
        "origin_dataset_id": dataset_id,
        "review_id": latest["id"],
        "created_at": created_at,
        "dataset_kind": "marketing_release_candidate_v1",
        "status": "staged_internal",
        "valid": False,
        "provider_verified": False,
        "publishable": False,
        "message": (
            "Da tao Release Candidate noi bo. "
            "Chua duoc phep publish sang KDH-Report-New."
        ),
    }


def register_marketing_release_routes(
    app, store, require, body
):
    @app.get(
        "/api/marketing/datasets/<dataset_id>/release-readiness"
    )
    @require("admin")
    def api_release_readiness(dataset_id):
        return jsonify(
            read_release_readiness(store, dataset_id)
        )

    @app.post(
        "/api/marketing/datasets/<dataset_id>/release-candidates"
    )
    @require("admin")
    def api_release_candidate(dataset_id):
        result = create_release_candidate(
            store,
            dataset_id=dataset_id,
            actor_id=g.user["id"],
            payload=body(),
        )
        return jsonify(result), 201
