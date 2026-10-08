"""Metric definitions for KDH's multi-platform marketing reports.

This module is a registry, NOT a data provider, KPI calculator or permission layer.
A registered metric is not evidence that the account/API supplies its value.
All actual reporting must be backed by persisted data, audited sync lineage,
source-specific permissions, and explicit calculation/aggregation rules.
"""

from __future__ import annotations

from copy import deepcopy

CATALOG_VERSION = "1.0"

# 'integration' describes verified application implementation, not user access.
# 'planned' source schemas are contracts to implement in future adapters.
SOURCES = {
    "ga4": {"label": "Google Analytics 4", "provider": "google", "asset_type": "ga4_property", "entity_type": "website", "integration": "adapter_present", "dimensions": ["date", "channel", "source_medium", "landing_page", "device", "country", "city"]},
    "gsc": {"label": "Google Search Console", "provider": "google", "asset_type": "search_console_property", "entity_type": "website", "integration": "adapter_present", "dimensions": ["date", "query", "page", "device", "country", "search_type"]},
    "keywords": {"label": "Keyword Ranking", "provider": "google", "asset_type": "keyword_sheet", "entity_type": "keyword", "integration": "detail_rows_present", "dimensions": ["snapshot_date", "keyword", "landing_url", "device", "location"]},
    "google_ads": {"label": "Google Ads", "provider": "google", "asset_type": "google_ads_customer", "entity_type": "ad_account", "integration": "planned", "dimensions": ["date", "campaign", "ad_group", "ad", "keyword", "device", "location"]},
    "facebook_ads": {"label": "Meta / Facebook & Instagram Ads", "provider": "meta", "asset_type": "facebook_ad_account", "entity_type": "ad_account", "integration": "oauth_only", "dimensions": ["date", "campaign", "ad_set", "ad", "placement", "device", "age", "gender"]},
    "facebook_content": {"label": "Facebook Page Content", "provider": "meta", "asset_type": "facebook_page", "entity_type": "page", "integration": "oauth_only", "dimensions": ["date", "post", "content_type", "topic"]},
    "instagram": {"label": "Instagram Organic", "provider": "meta", "asset_type": "instagram_business_account", "entity_type": "profile", "integration": "planned", "dimensions": ["date", "media", "content_type", "topic"]},
    "tiktok_ads": {"label": "TikTok Ads", "provider": "tiktok", "asset_type": "tiktok_ad_account", "entity_type": "ad_account", "integration": "planned", "dimensions": ["date", "campaign", "ad_group", "ad", "placement", "device"]},
    "tiktok_organic": {"label": "TikTok Organic", "provider": "tiktok", "asset_type": "tiktok_profile", "entity_type": "profile", "integration": "planned", "dimensions": ["snapshot_date", "video", "topic", "hashtag"]},
    "youtube": {"label": "YouTube Analytics", "provider": "youtube", "asset_type": "youtube_channel", "entity_type": "channel", "integration": "planned", "dimensions": ["date", "video", "content_type", "traffic_source", "device", "country"]},
    "gmb": {"label": "Google Business Profile", "provider": "gmb", "asset_type": "business_location", "entity_type": "location", "integration": "csv_only", "dimensions": ["date", "month", "location", "device", "search_surface"]},
    "crm": {"label": "Leads / CRM / Bookings / Revenue", "provider": "other", "asset_type": "crm_pipeline", "entity_type": "pipeline", "integration": "planned", "dimensions": ["date", "campaign", "lead_source", "location", "status"]},
}

# Each row: storage metric field | display label | unit | aggregation | granularity
# The field is the proposed normalized field stored in daily_metrics.metrics.
# Granularity defaults to 'day'; 'snapshot' is a cumulative/lifetime reading.
# Aggregation:
#   sum          - additive for compatible, disjoint periods/dimensions
#   distinct     - cannot sum daily unique people/reach
#   recalculate  - calculate at report scope from verified numerator/denominator
#   weighted     - needs source-specific weight / provider aggregate
#   latest       - most recent snapshot; not sum of snapshots
#   non_additive - do not sum/average blindly; use provider/scoped aggregation
# Note: these are semantics for the NEXT calculation engine, not executable math.
_METRIC_ROWS = {
    "ga4": """
        sessions|Phiên truy cập|count|sum
        active_users|Người dùng hoạt động|count|distinct
        total_users|Tổng người dùng|count|distinct
        new_users|Người dùng mới|count|distinct
        returning_users|Người dùng quay lại|count|distinct
        engaged_sessions|Phiên tương tác|count|sum
        engagement_rate|Tỷ lệ tương tác|ratio|recalculate
        bounce_rate|Tỷ lệ thoát|ratio|recalculate
        page_views|Lượt xem trang|count|sum
        average_session_duration|Thời gian phiên TB|seconds|weighted
        average_engagement_time|Thời gian tương tác TB|seconds|weighted
        event_count|Tổng sự kiện|count|sum
        form_starts|Bắt đầu điền form|count|sum
        form_submissions|Gửi form|count|sum
        key_events|Sự kiện chính|count|sum
        session_key_event_rate|Tỷ lệ phiên có sự kiện chính|ratio|recalculate
        transactions|Giao dịch|count|sum
        purchase_revenue|Doanh thu mua hàng|currency|sum
    """,
    "gsc": """
        clicks|Nhấp từ Google Search|count|sum
        impressions|Lượt xuất hiện tìm kiếm|count|sum
        ctr|CTR tìm kiếm|ratio|recalculate
        position|Vị trí trung bình|rank|non_additive
        branded_clicks|Clicks thương hiệu|count|sum
        nonbranded_clicks|Clicks phi thương hiệu|count|sum
        mobile_clicks|Clicks mobile|count|sum
        desktop_clicks|Clicks desktop|count|sum
        organic_pages|Số URL có clicks|count|distinct
        organic_queries|Số truy vấn có clicks|count|distinct
    """,
    "keywords": """
        tracked_keywords|Từ khóa được theo dõi|count|latest|snapshot
        ranked_keywords|Từ khóa có thứ hạng|count|latest|snapshot
        top1|Từ khóa Top 1|count|latest|snapshot
        top3|Từ khóa Top 3|count|latest|snapshot
        top5|Từ khóa Top 5|count|latest|snapshot
        top10|Từ khóa Top 10|count|latest|snapshot
        top20|Từ khóa Top 20|count|latest|snapshot
        top50|Từ khóa Top 50|count|latest|snapshot
        top100|Từ khóa Top 100|count|latest|snapshot
        improved_keywords|Từ khóa tăng hạng|count|latest|snapshot
        declined_keywords|Từ khóa giảm hạng|count|latest|snapshot
        new_rankings|Từ khóa mới có thứ hạng|count|latest|snapshot
        lost_rankings|Từ khóa mất thứ hạng|count|latest|snapshot
        current_rank|Hạng từ khóa hiện tại|rank|latest|snapshot
        previous_rank|Hạng từ khóa kỳ trước|rank|latest|snapshot
        search_volume|Lượng tìm kiếm ước tính|count|non_additive|snapshot
        keyword_difficulty|Độ khó từ khóa|score|non_additive|snapshot
    """,
    "google_ads": """
        spend|Chi phí quảng cáo|currency|sum
        budget|Ngân sách chiến dịch|currency|latest|snapshot
        impressions|Lượt hiển thị|count|sum
        clicks|Lượt nhấp|count|sum
        interactions|Lượt tương tác quảng cáo|count|sum
        ctr|CTR|ratio|recalculate
        average_cpc|CPC trung bình|currency|recalculate
        cpm|CPM|currency|recalculate
        conversions|Chuyển đổi được quy gán|count|sum
        conversion_rate|Tỷ lệ chuyển đổi|ratio|recalculate
        cost_per_conversion|Chi phí trên chuyển đổi|currency|recalculate
        conversion_value|Giá trị chuyển đổi|currency|sum
        roas|ROAS|number|recalculate
        video_views|Lượt xem video Ads|count|sum
        view_rate|Tỷ lệ xem video Ads|ratio|recalculate
        search_impression_share|Tỷ lệ hiển thị tìm kiếm|ratio|non_additive
        lost_impression_share_budget|Mất hiển thị do ngân sách|ratio|non_additive
        lost_impression_share_rank|Mất hiển thị do thứ hạng Ads|ratio|non_additive
    """,
    "facebook_ads": """
        spend|Chi phí quảng cáo Meta|currency|sum
        budget|Ngân sách|currency|latest|snapshot
        impressions|Lượt hiển thị|count|sum
        reach|Tiếp cận duy nhất|count|distinct
        frequency|Tần suất hiển thị|number|non_additive
        clicks|Tất cả lượt nhấp|count|sum
        link_clicks|Nhấp liên kết|count|sum
        outbound_clicks|Nhấp ra ngoài|count|sum
        landing_page_views|Lượt xem landing page|count|sum
        ctr|CTR tất cả lượt nhấp|ratio|recalculate
        link_ctr|CTR liên kết|ratio|recalculate
        cpc|CPC|currency|recalculate
        cpm|CPM|currency|recalculate
        leads|Lead được Meta quy gán|count|sum
        website_leads|Website Leads|count|sum
        instant_form_leads|Lead Form Meta|count|sum
        messaging_conversations|Cuộc trò chuyện từ Ads|count|sum
        results|Kết quả theo mục tiêu|count|sum
        cost_per_result|Chi phí trên kết quả|currency|recalculate
        cpl|Chi phí trên Lead|currency|recalculate
        conversions|Chuyển đổi được quy gán|count|sum
        purchases|Lượt mua được quy gán|count|sum
        conversion_value|Giá trị chuyển đổi|currency|sum
        roas|ROAS|number|recalculate
        video_3s_views|Lượt xem video 3 giây|count|sum
        thruplays|ThruPlay|count|sum
        video_25_percent|Xem đến 25% video|count|sum
        video_50_percent|Xem đến 50% video|count|sum
        video_75_percent|Xem đến 75% video|count|sum
        video_95_percent|Xem đến 95% video|count|sum
        video_100_percent|Xem hết video|count|sum
    """,
    "facebook_content": """
        posts_published|Bài đăng mới|count|sum
        views|Lượt xem nội dung|count|sum
        reach|Tiếp cận duy nhất|count|distinct
        reactions|Lượt bày tỏ cảm xúc|count|sum
        comments|Bình luận|count|sum
        shares|Lượt chia sẻ|count|sum
        saves|Lượt lưu|count|sum
        post_clicks|Lượt nhấp bài đăng|count|sum
        engagements|Tổng tương tác|count|sum
        engagement_rate|Tỷ lệ tương tác|ratio|recalculate
        video_views|Lượt xem video|count|sum
        followers_total|Tổng người theo dõi|count|latest|snapshot
        followers_gained|Người theo dõi mới|count|sum
        followers_lost|Người bỏ theo dõi|count|sum
    """,
    "instagram": """
        media_published|Bài/Reels/Story mới|count|sum
        views|Lượt xem nội dung|count|sum
        reach|Tiếp cận duy nhất|count|distinct
        likes|Lượt thích|count|sum
        comments|Bình luận|count|sum
        shares|Chia sẻ|count|sum
        saves|Lưu bài|count|sum
        engagements|Tổng tương tác|count|sum
        engagement_rate|Tỷ lệ tương tác|ratio|recalculate
        reels_views|Lượt xem Reels|count|sum
        watch_time_minutes|Thời gian xem|minutes|sum
        profile_visits|Lượt vào hồ sơ|count|sum
        website_clicks|Nhấp website từ hồ sơ|count|sum
        followers_total|Tổng followers|count|latest|snapshot
        followers_gained|Followers mới|count|sum
    """,
    "tiktok_ads": """
        spend|Chi phí TikTok Ads|currency|sum
        budget|Ngân sách|currency|latest|snapshot
        impressions|Lượt hiển thị|count|sum
        reach|Tiếp cận duy nhất|count|distinct
        clicks|Nhấp quảng cáo|count|sum
        ctr|CTR|ratio|recalculate
        cpc|CPC|currency|recalculate
        cpm|CPM|currency|recalculate
        conversions|Chuyển đổi|count|sum
        conversion_rate|Tỷ lệ chuyển đổi|ratio|recalculate
        cost_per_conversion|Chi phí trên chuyển đổi|currency|recalculate
        conversion_value|Giá trị chuyển đổi|currency|sum
        roas|ROAS|number|recalculate
        video_views|Lượt xem video Ads|count|sum
        video_2s_views|Video views 2 giây|count|sum
        video_6s_views|Video views 6 giây|count|sum
        video_25_percent|Xem đến 25%|count|sum
        video_50_percent|Xem đến 50%|count|sum
        video_75_percent|Xem đến 75%|count|sum
        video_100_percent|Xem hết video|count|sum
        average_play_time|Thời gian xem TB|seconds|weighted
        leads|Lead quảng cáo|count|sum
    """,
    "tiktok_organic": """
        videos_published|Video mới|count|sum
        video_views|Tổng lượt xem video tích lũy|count|latest|snapshot
        likes|Lượt thích tích lũy|count|latest|snapshot
        comments|Bình luận tích lũy|count|latest|snapshot
        shares|Lượt chia sẻ tích lũy|count|latest|snapshot
        followers_total|Tổng người theo dõi|count|latest|snapshot
        followers_gained|Người theo dõi tăng|count|sum
        profile_views|Lượt xem hồ sơ|count|sum
        average_watch_time|Thời gian xem TB|seconds|non_additive
        completion_rate|Tỷ lệ xem hết video|ratio|non_additive
    """,
    "youtube": """
        views|Lượt xem YouTube|count|sum
        engaged_views|Lượt xem tương tác|count|sum
        watch_time_minutes|Thời gian xem (phút)|minutes|sum
        average_view_duration|Thời gian xem TB|seconds|weighted
        average_view_percentage|Phần trăm xem TB|ratio|weighted
        subscribers_gained|Người đăng ký tăng|count|sum
        subscribers_lost|Người đăng ký giảm|count|sum
        likes|Lượt thích|count|sum
        comments|Bình luận|count|sum
        shares|Lượt chia sẻ|count|sum
        impressions|Lượt hiển thị thumbnail|count|sum
        impressions_ctr|CTR thumbnail|ratio|recalculate
        playlist_starts|Bắt đầu xem playlist|count|sum
        views_from_search|Views từ YouTube Search|count|sum
        views_from_suggested|Views từ video gợi ý|count|sum
        estimated_revenue|Doanh thu YouTube ước tính|currency|sum
        peak_concurrent_viewers|Người xem trực tiếp cao nhất|count|non_additive
    """,
    "gmb": """
        search_desktop_impressions|Hiển thị Search Desktop|count|sum
        search_mobile_impressions|Hiển thị Search Mobile|count|sum
        maps_desktop_impressions|Hiển thị Maps Desktop|count|sum
        maps_mobile_impressions|Hiển thị Maps Mobile|count|sum
        call_clicks|Nhấp gọi điện|count|sum
        direction_requests|Yêu cầu chỉ đường|count|sum
        website_clicks|Nhấp vào website|count|sum
        review_count|Tổng đánh giá|count|latest|snapshot
        average_rating|Điểm đánh giá TB|score|non_additive
        new_reviews|Đánh giá mới|count|sum
        search_keyword_impressions|Hiển thị theo truy vấn địa phương|count|sum|month
        location_count|Số địa điểm kinh doanh|count|latest|snapshot
    """,
    "crm": """
        form_submissions|Biểu mẫu đã gửi|count|sum
        leads|Leads từ CRM|count|sum
        unique_leads|Leads không trùng|count|distinct
        qualified_leads|Leads chất lượng|count|sum
        invalid_leads|Leads không hợp lệ|count|sum
        contacted_leads|Leads đã liên hệ|count|sum
        calls_received|Cuộc gọi nhận được|count|sum
        calls_answered|Cuộc gọi được nghe|count|sum
        appointments_booked|Lịch hẹn đã đặt|count|sum
        appointments_attended|Lịch hẹn thực hiện|count|sum
        new_customers|Khách hàng mới|count|distinct
        customers_returning|Khách hàng quay lại|count|distinct
        orders|Đơn hàng|count|sum
        invoices|Hóa đơn|count|sum
        revenue|Doanh thu ghi nhận|currency|sum
        attributed_revenue|Doanh thu được quy gán Marketing|currency|sum
    """,
}

# Formula-based metrics: operands MUST be available for the same scope, currency,
# attribution model, timezone, and reporting period. Math is intentionally not
# executed here. Ratios with denominator=0 are unavailable, not zero.
# Format: source, field, label, unit, operation, numerator ID, denominator ID.
_DERIVED = [
    ("ga4", "views_per_session", "Lượt xem trên phiên", "number", "divide", "ga4.page_views", "ga4.sessions"),
    ("ga4", "form_completion_rate", "Tỷ lệ hoàn thành form", "ratio", "divide", "ga4.form_submissions", "ga4.form_starts"),
    ("gsc", "recalculated_ctr", "CTR được tính lại", "ratio", "divide", "gsc.clicks", "gsc.impressions"),
    ("google_ads", "calculated_cpa", "CPA Google Ads", "currency", "divide", "google_ads.spend", "google_ads.conversions"),
    ("facebook_ads", "calculated_cpl", "CPL Meta Ads được tính lại", "currency", "divide", "facebook_ads.spend", "facebook_ads.leads"),
    ("facebook_ads", "calculated_roas", "ROAS Meta Ads được tính lại", "number", "divide", "facebook_ads.conversion_value", "facebook_ads.spend"),
    ("tiktok_ads", "calculated_cpc", "CPC TikTok tính lại", "currency", "divide", "tiktok_ads.spend", "tiktok_ads.clicks"),
    ("tiktok_ads", "calculated_roas", "ROAS TikTok Ads được tính lại", "number", "divide", "tiktok_ads.conversion_value", "tiktok_ads.spend"),
    ("crm", "show_up_rate", "Tỷ lệ đến hẹn", "ratio", "divide", "crm.appointments_attended", "crm.appointments_booked"),
    ("crm", "lead_to_customer_rate", "Tỷ lệ Lead thành khách hàng", "ratio", "divide", "crm.new_customers", "crm.unique_leads"),
    ("crm", "qualified_lead_rate", "Tỷ lệ Lead hợp lệ", "ratio", "divide", "crm.qualified_leads", "crm.unique_leads"),
]

VALID_UNITS = {"count", "currency", "ratio", "rank", "number", "seconds", "minutes", "score"}
VALID_AGGREGATIONS = {"sum", "distinct", "recalculate", "weighted", "latest", "non_additive"}
VALID_GRAINS = {"day", "month", "snapshot"}

# A source metric may not be provided by a particular account, API version, grant,
# report level, tracking setup, or attribution configuration. Catalog != availability.
def _visualizations(unit, grain):
    if grain == "snapshot":
        return ["kpi", "table", "comparison"]
    if grain == "month":
        return ["kpi", "bar", "table", "comparison"]
    if unit == "rank":
        return ["kpi", "line", "table", "comparison"]
    return ["kpi", "line", "bar", "table", "comparison"]


def _build_metrics():
    result = {}
    for source, multiline in _METRIC_ROWS.items():
        for raw_line in multiline.strip().splitlines():
            cells = [piece.strip() for piece in raw_line.split("|")]
            if len(cells) not in (4, 5):
                raise ValueError(f"Invalid metric definition: {source} {raw_line}")
            field, label, unit, aggregation = cells[:4]
            grain = cells[4] if len(cells) == 5 else "day"
            metric_id = f"{source}.{field}"
            if metric_id in result:
                raise ValueError(f"Duplicate metric: {metric_id}")
            result[metric_id] = {
                "id": metric_id,
                "source": source,
                "field": field,
                "label": label,
                "unit": unit,
                "aggregation": aggregation,
                "grain": grain,
                "kind": "source",
                "requires": [],
                "operation": None,
                "visualizations": _visualizations(unit, grain),
            }
    for source, field, label, unit, operation, numerator, denominator in _DERIVED:
        metric_id = f"{source}.{field}"
        if metric_id in result:
            raise ValueError(f"Duplicate metric: {metric_id}")
        result[metric_id] = {
            "id": metric_id,
            "source": source,
            "field": field,
            "label": label,
            "unit": unit,
            "aggregation": "recalculate",
            "grain": "day",
            "kind": "derived",
            "requires": [numerator, denominator],
            "operation": operation,
            "visualizations": ["kpi", "line", "table", "comparison"],
        }
    return result


METRICS = _build_metrics()

# Evidence fields to capture alongside each real output in later API/Bundle steps.
# These are REQUIRED in the evidence model design, not proof they exist today.
EVIDENCE_CONTRACT = {
    "identity": ["client_id", "source_key", "provider", "asset_id"],
    "lineage": ["sync_run_id", "metric_id", "catalog_version"],
    "context": ["period_start", "period_end", "timezone", "filters", "dimensions"],
    "quality": ["sync_status", "latest_available_date", "fetched_at", "is_demo"],
    "optional": ["source_url", "campaign_id", "post_id", "video_id", "keyword", "rank_device", "rank_location"],
}


def validate_catalog():
    """Raise on broken local registry definitions; return metric count."""
    for key, metric in METRICS.items():
        if metric["id"] != key or metric["source"] not in SOURCES:
            raise ValueError(f"Invalid source/ID in {key}")
        if metric["unit"] not in VALID_UNITS:
            raise ValueError(f"Invalid unit in {key}")
        if metric["aggregation"] not in VALID_AGGREGATIONS:
            raise ValueError(f"Invalid aggregation in {key}")
        if metric["grain"] not in VALID_GRAINS:
            raise ValueError(f"Invalid grain in {key}")
        for required in metric["requires"]:
            if required not in METRICS:
                raise ValueError(f"Unknown prerequisite {required} for {key}")
    for key in SOURCES:
        if not any(m["source"] == key for m in METRICS.values()):
            raise ValueError(f"Source has no metrics: {key}")
    return len(METRICS)


def get_metric(metric_id):
    """Return a defensive copy (or None), not a mutable registry object."""
    found = METRICS.get(metric_id)
    return deepcopy(found) if found is not None else None


def list_metrics(source=None, *, kind=None):
    """Discover the catalog; does not assert real API/data availability."""
    if source is not None and source not in SOURCES:
        return []
    return [deepcopy(metric) for metric in METRICS.values()
            if (source is None or metric["source"] == source)
            and (kind is None or metric["kind"] == kind)]


def get_catalog():
    return {
        "version": CATALOG_VERSION,
        "sources": deepcopy(SOURCES),
        "metrics": list_metrics(),
        "evidence_contract": deepcopy(EVIDENCE_CONTRACT),
    }


if __name__ == "__main__":
    total = validate_catalog()
    print(f"CATALOG VALID: {len(SOURCES)} sources, {total} metrics")
    for source, item in SOURCES.items():
        print(f"  {source:18} {len(list_metrics(source)):>3} metrics  [{item['integration']}]")
    print("NOTE: Catalog definitions are not provider connections or real metrics.")
