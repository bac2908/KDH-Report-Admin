# Trạng thái provider và KPI

Kiểm tra code local 10/10/2026. Catalog: **12 nguồn, 211 định nghĩa**. Không đồng nghĩa 211 KPI đã có adapter hay dữ liệu.

| Nguồn Catalog | Code hiện có | Bản Marketing release mới |
| --- | --- | --- |
| `ga4` | OAuth + Data API; totals/daily/channels/pages | Xác minh 4 KPI snapshot: sessions, active_users, page_views, engagement_rate |
| `gsc` | OAuth + Search Analytics; totals/daily/queries | Xác minh clicks, impressions, ctr, position |
| `keywords` | OAuth + Google Sheets; entries theo ngày | Xác minh top5/top10/top20/top100 từ snapshot Sheet |
| `google_ads` | Catalog / planned | Chặn thiếu adapter/provenance |
| `facebook_ads` | Meta OAuth hiện có; chưa hoàn chỉnh sync số liệu | Chặn thiếu adapter/provenance |
| `facebook_content` | Meta OAuth hiện có; chưa hoàn chỉnh sync số liệu | Chặn thiếu adapter/provenance |
| `instagram` | Planned | Chưa hỗ trợ |
| `tiktok_ads` | Planned | Chưa hỗ trợ |
| `tiktok_organic` | Planned | Chưa hỗ trợ |
| `youtube` | Planned | Chưa hỗ trợ |
| `gmb` | Luồng upload CSV cũ | Không tự biến CSV thành provider-origin-confirmed |
| `crm` | Planned | Chưa hỗ trợ |

## BLOCKED — xác nhận dữ liệu KinderHealth thật

Chưa nghiệm thu tài khoản/provider permission thật trong đợt này. Các ca thành công dùng response tổng hợp độc lập trong database test. Receipt khi chạy test chỉ chứng minh adapter/guard hoạt động trong test, không xác nhận chiến dịch KinderHealth.

Khi được cấp quyền Google:

1. Quản trị hệ thống đặt OAuth Web client ID/secret và callback trong cấu hình backend Admin.
2. Nhập đúng `GA4_PROPERTY_ID`, `GSC_PROPERTY`, `KEYWORD_SPREADSHEET_ID`, `KEYWORD_SHEET` (và năm tracking nếu Sheet dùng ngày thiếu năm).
3. Tài khoản Google kết nối phải có quyền đọc đúng property/site/Sheet. Người dùng ứng dụng và tài khoản Google là hai khái niệm riêng.
4. Kết nối Google trong Admin, kiểm tra từng nguồn, chạy đồng bộ kỳ chính và kỳ trước. Không nhập token vào New.
5. Xem trạng thái/lỗi sync, ngày dữ liệu, asset và snapshot. Nếu kết nối thành công nhưng không có dữ liệu, không nâng status thủ công.
6. Tạo Dataset mới trong `/marketing`, kiểm tra nguồn và duyệt theo [luồng dữ liệu](KDH_DATA_FLOW.md).

Snapshot/sync cũ chưa có receipt theo contract mới cần đồng bộ lại. Không có endpoint ký bù receipt cho dữ liệu nhập tay. Với Google Sheets, provenance chỉ xác nhận đã đọc đúng Sheet qua API; không chứng minh thứ hạng trong Sheet được Google Search xác thực độc lập.

Meta/TikTok/YouTube/Google Ads/CRM cần bổ sung adapter chuẩn hóa và receipt trước khi dùng cùng luồng release. Nhập ID/token cho nguồn chưa có adapter sẽ không tự tạo ra hỗ trợ. Giữ empty state và trạng thái blocked đến khi có triển khai và kiểm thử tương ứng.
