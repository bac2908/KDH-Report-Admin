
"""Authenticated read-only Metric Reporting API."""

from flask import g, jsonify, request

from .core import TYPES, Problem, allowed
from .metric_catalog import (
    CATALOG_VERSION,
    SOURCES,
    get_metric,
    list_metrics,
)
from .metric_reader import read_metric_series
from .metric_calculator import calculate_metric
from .evidence_engine import build_metric_evidence
from .opportunity_engine import build_opportunities
from .platform_data import DEFAULT_CLIENT_ID


# Existing Admin report permissions mapped to
# normalized Metric Catalog source IDs.
#
# New sources without an existing permission
# remain admin-only until roles are extended.
SOURCE_REPORT_PERMISSIONS = {
    "ga4": ("seo", "ga4"),
    "gsc": ("seo", "gsc"),
    "keywords": ("seo", "keywords"),
    "gmb": ("gmb",),
    "facebook_ads": ("facebook-ads",),
    "facebook_content": (
        "facebook-content",
        "facebook-content-30d",
        "facebook-content-6m",
    ),
    "tiktok_ads": ("tiktok",),
}


def permitted_metric_sources(user):
    """Derive permissions from the authenticated user."""
    if user["role"] == "admin":
        return set(SOURCES)

    return {
        source
        for source, report_types in SOURCE_REPORT_PERMISSIONS.items()
        if source in SOURCES
        and any(
            report_type in TYPES
            and allowed(user, report_type)
            for report_type in report_types
        )
    }


def _validate_query(accepted, required=()):
    """Reject unknown or repeated query parameters."""
    if set(request.args) - set(accepted):
        raise Problem(
            "Tham số truy vấn không được hỗ trợ.",
            400,
            "invalid_query",
        )

    if any(
        len(request.args.getlist(key)) != 1
        for key in request.args
    ):
        raise Problem(
            "Không được truyền trùng tham số.",
            400,
            "invalid_query",
        )

    if any(
        not request.args.get(key, "").strip()
        for key in required
    ):
        raise Problem(
            "Thiếu tham số bắt buộc.",
            400,
            "invalid_query",
        )


def register_metric_routes(app, store, require):
    """Register authenticated Metric Reporting endpoints."""

    # =============================================
    # GET /api/metrics/catalog
    # =============================================

    @app.get("/api/metrics/catalog")
    @require()
    def api_metric_catalog():
        _validate_query({"source"})

        permitted = permitted_metric_sources(g.user)
        selected = request.args.get("source")

        if selected is not None:
            if selected not in SOURCES:
                raise Problem(
                    "Nguồn dữ liệu không tồn tại.",
                    400,
                    "invalid_source",
                )

            if selected not in permitted:
                raise Problem(
                    "Bạn không có quyền xem nguồn này.",
                    403,
                    "forbidden_source",
                )

            visible = {selected}
        else:
            visible = permitted

        metrics = [
            item
            for item in list_metrics()
            if item["source"] in visible
        ]

        return jsonify(
            version=CATALOG_VERSION,
            sources={
                key: SOURCES[key]
                for key in sorted(visible)
            },
            metrics=metrics,
            count=len(metrics),
            note=(
                "Danh mục KPI không chứng minh "
                "nguồn đã có dữ liệu thật."
            ),
        )

    # =============================================
    # GET /api/metrics/series
    # =============================================

    @app.get("/api/metrics/series")
    @require()
    def api_metric_series():
        _validate_query(
            {
                "metric_id",
                "start",
                "end",
                "asset_id",
            },
            required=(
                "metric_id",
                "start",
                "end",
            ),
        )

        metric_id = request.args["metric_id"]
        metric = get_metric(metric_id)

        if metric is None:
            raise Problem(
                "Chỉ số không tồn tại.",
                404,
                "metric_not_found",
            )

        permitted = permitted_metric_sources(g.user)

        if metric["source"] not in permitted:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            )

        try:
            result = read_metric_series(
                store,
                metric_id=metric_id,
                client_id=DEFAULT_CLIENT_ID,
                allowed_sources=permitted,
                start=request.args["start"],
                end=request.args["end"],
                asset_id=request.args.get("asset_id"),
            )

        except PermissionError:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_metric_query",
            ) from None

        return jsonify(result)
    
    @app.get("/api/metrics/calculate")
    @require()
    def api_metric_calculate():
        _validate_query(
            {"metric_id", "start", "end", "asset_id"},
            required=("metric_id", "start", "end"),
        )

        metric_id = request.args["metric_id"]
        metric = get_metric(metric_id)

        if metric is None:
            raise Problem(
                "Chỉ số không tồn tại.",
                404,
                "metric_not_found",
            )

        permitted = permitted_metric_sources(g.user)

        if metric["source"] not in permitted:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            )

        try:
            output = calculate_metric(
                store,
                metric_id=metric_id,
                client_id=DEFAULT_CLIENT_ID,
                allowed_sources=permitted,
                start=request.args["start"],
                end=request.args["end"],
                asset_id=request.args.get("asset_id"),
            )

        except PermissionError:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_metric_query",
            ) from None

        return jsonify(output)
    
    # =============================================
    # GET /api/metrics/evidence
    # =============================================

    @app.get("/api/metrics/evidence")
    @require()
    def api_metric_evidence():
        _validate_query(
            {
                "metric_id",
                "start",
                "end",
                "asset_id",
                "compare_start",
                "compare_end",
            },
            required=(
                "metric_id",
                "start",
                "end",
            ),
        )

        metric_id = request.args["metric_id"]
        metric = get_metric(metric_id)

        if metric is None:
            raise Problem(
                "Chỉ số không tồn tại.",
                404,
                "metric_not_found",
            )

        permitted = permitted_metric_sources(g.user)

        if metric["source"] not in permitted:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            )

        try:
            result = build_metric_evidence(
                store,
                metric_id=metric_id,
                client_id=DEFAULT_CLIENT_ID,
                allowed_sources=permitted,
                start=request.args["start"],
                end=request.args["end"],
                asset_id=request.args.get("asset_id"),
                compare_start=request.args.get(
                    "compare_start"
                ),
                compare_end=request.args.get(
                    "compare_end"
                ),
            )

        except PermissionError:
            raise Problem(
                "Bạn không có quyền xem chỉ số này.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_evidence_query",
            ) from None

        return jsonify(result)
    
    # ==========================================
    # GET /api/metrics/opportunities
    # ==========================================

    @app.get("/api/metrics/opportunities")
    @require("admin", "operator")
    def api_metric_opportunities():
        _validate_query(
            {
                "source",
                "start",
                "end",
                "compare_start",
                "compare_end",
                "asset_id",
            },
            required=("start", "end"),
        )

        permitted = permitted_metric_sources(g.user)

        try:
            result = build_opportunities(
                store,
                client_id=DEFAULT_CLIENT_ID,
                allowed_sources=permitted,
                source=request.args.get("source"),
                start=request.args["start"],
                end=request.args["end"],
                compare_start=request.args.get(
                    "compare_start"
                ),
                compare_end=request.args.get(
                    "compare_end"
                ),
                asset_id=request.args.get("asset_id"),
            )

        except PermissionError:
            raise Problem(
                "Ban khong co quyen xem nguon nay.",
                403,
                "forbidden_source",
            ) from None

        except ValueError as exc:
            raise Problem(
                str(exc),
                400,
                "invalid_opportunity_query",
            ) from None

        return jsonify(result)
