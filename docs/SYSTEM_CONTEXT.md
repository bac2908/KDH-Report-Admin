# KDH Report — bối cảnh toàn hệ thống

Đối chiếu kiến trúc hai repository ngày **07/10/2026**; cập nhật phần Data Foundation và Docker Admin ngày **08/10/2026**. Nguồn: yêu cầu của chủ dự án, sơ đồ “KDH-Report System Architecture Flow”, code và trạng thái Docker. Đây là tài liệu tiếp nối công việc; trạng thái triển khai và các điểm đang dở phải được kiểm tra lại khi code thay đổi.

## 1. Mục tiêu và các quyết định đã chốt

Một hệ thống báo cáo marketing cho KinderHealth, gồm hai ứng dụng có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Công nghệ hiện tại |
| --- | --- | --- |
| **KDH-Report-Admin** | Kết nối nguồn, đồng bộ, chuẩn hóa, kiểm tra chất lượng, lưu Dataset, tạo và xuất bản Report Bundle; quản lý vận hành | Flask, Vanilla JS, worker, PostgreSQL trong Docker |
| **Kho dữ liệu do Admin quản lý** | Nguồn dữ liệu chuẩn duy nhất; lưu thông tin kết nối, dữ liệu nguồn, snapshot, phiên bản báo cáo | PostgreSQL; token nằm trong bảng secrets được mã hóa |
| **KDH-Report-New** | Backend đọc Bundle đã xuất bản; frontend trình bày cho khách hàng/sếp/người xem | FastAPI, Jinja2, Vanilla JS; Docker riêng |

- Chạy **Docker**, không tiếp tục triển khai Vercel.
- Giao diện phục vụ một khách hàng KinderHealth; giữ `client_id` trong kiến trúc, chưa mở rộng UI thành SaaS nhiều khách hàng.
- Giữ kiến trúc của từng repository; không gộp hai backend, không chuyển Admin sang React/Vue.
- Luồng HTML/Excel, báo cáo cũ, auth, OAuth và jobs hiện có vẫn phải hoạt động.
- Report Builder và Preview chỉ đọc Dataset snapshot; không gọi provider để lấy số liệu mới.
- Dataset và nội dung revision đã xuất bản phải bất biến. Dữ liệu mới tạo Dataset/revision mới.
- Không điền số liệu mẫu vào báo cáo thật khi nguồn thiếu/lỗi. Số 0 thật khác với không có dữ liệu.
- GA4, GSC và Keywords là nguồn kỹ thuật của SEO, không phải ba mục báo cáo cấp cao.
- Quyết định trước đây về tài khoản: khi triển khai Owner, chọn **admin đang hoạt động được tạo đầu tiên**. Đây là quyết định đã nhận, chưa phải tính năng đã có trong code hiện tại.

## 2. Cách đọc sơ đồ kiến trúc

Luồng mục tiêu:

```text
Google / Meta / TikTok / YouTube / GMB hoặc CSV
  -> Admin: kết nối + sync + chuẩn hóa + kiểm tra chất lượng
  -> Admin DB: daily_metrics + source_snapshots + nhật ký sync
  -> tạo immutable Dataset từ dữ liệu đã lưu
  -> Report Builder: chọn Dataset, kỳ, section, thứ tự
  -> Preview -> publish Report Bundle revision
  -> Admin Internal API (chỉ đọc, service token)
  -> Report-New: AdminBundleRepository
  -> BundleViewMapper + section resolver
  -> giao diện chỉ hiện các section đã xuất bản
```

“Kho dữ liệu chung” là nguồn sự thật chung về nghiệp vụ. **Report-New đọc qua Internal API của Admin**, không được đọc toàn bộ database hay nhận OAuth token. Admin ghi database qua lớp lưu trữ của mình; Internal Report API hiện tại chỉ phục vụ đọc Bundle.

Service token xác thực **backend New với backend Admin**. Nó không thay thế đăng nhập/phân quyền người xem cuối, và không được đưa xuống trình duyệt.

Ví dụ mục tiêu: người vận hành chọn Dataset SEO tháng 9, tạo Bundle gồm `overview` và `seo`, xem trước rồi xuất bản revision 1. Người xem mở New chỉ thấy hai mục đó. Nếu đồng bộ lại có dữ liệu khác, revision 1 giữ nguyên; cần Dataset mới và revision 2. Mở lại revision 1 phải thấy đúng số liệu đã xuất bản trước đó.

## 3. Phân biệt các lớp dữ liệu

| Lớp | Ý nghĩa và giới hạn |
| --- | --- |
| `connections`, `source_assets` | Tài khoản/kết nối và tài sản cụ thể: GA4 property, GSC site, Sheet, Page, Ad Account… Kết nối thành công chưa có nghĩa đã đồng bộ được dữ liệu. |
| `sync_runs`, `sync_watermarks` | Lịch sử chạy, kỳ yêu cầu, lỗi, ngày dữ liệu thật mới nhất; không dùng thời điểm job kết thúc thay cho độ mới dữ liệu. |
| `daily_metrics` | Số liệu chuẩn hóa theo ngày, được upsert khi provider điều chỉnh dữ liệu. Không phải snapshot báo cáo bất biến. |
| `source_snapshots` | Payload nguồn đã chuẩn hóa theo lần sync, giữ chi tiết như channels/pages/queries/keywords mà daily metrics chưa diễn tả đủ. Không phải raw HTTP response chứa credential. Code hiện upsert theo `sync_run_id`; không đồng nhất tính bất biến của lớp này với Dataset. |
| `datasets` | Snapshot dữ liệu phục vụ kiểm tra/phân tích, xuất file và làm đầu vào Builder. |
| `report_bundles`, `report_bundle_sections` | Gói báo cáo: client, kỳ, revision, chất lượng, branding, navigation và dữ liệu section đã chụp lại. |
| View model của New | Chuyển dữ liệu Bundle thành cấu trúc template/chart; không gọi provider, không tạo KPI kinh doanh còn thiếu hoặc áp dụng tỷ lệ mô phỏng từ mock. |

## 4. Code Admin hiện có và phần đang dở

Mốc đối chiếu: branch `feat/postgres-primary-store`, HEAD `ea84bb245d387daecede9302a97df4cf17108acf`, **có thay đổi chưa commit** về PostgreSQL và đồng bộ Google/source snapshots. Không được reset hoặc ghi đè chúng.

| Phần | Trạng thái quan sát được |
| --- | --- |
| Auth và quyền | Có session, băm mật khẩu, CSRF, role admin/operator/viewer, giới hạn theo loại báo cáo; cập nhật tài khoản thu hồi phiên. Chưa có Owner, bộ quyền xem/chạy/xuất/publish tách riêng, vòng đời mời/reset/2FA đầy đủ. |
| Google | OAuth và adapter GA4/GSC/Sheets thật; lưu tình trạng nguồn riêng. Quyền tài khoản trên từng tài sản vẫn phải hợp lệ. |
| Meta | Có OAuth và quản lý kết nối; chưa có luồng đồng bộ dữ liệu Page/Ads hoàn chỉnh. |
| TikTok/YouTube | Có vị trí trong kiến trúc/UI; chưa có reporting adapter vận hành trong Admin. |
| GMB | Luồng CSV hiện có; không coi việc có màn hình GMB là đã tích hợp API Business Profile. |
| Data Foundation | Có clients, connections, assets, sync runs, watermarks, daily metrics. Một số màn hình chỉ đọc/tổng hợp từ API hiện có, thao tác chưa có backend được khóa. |
| Google persistence | Đã triển khai daily metrics và source snapshots lên Docker ngày 08/10/2026. Sync thành công/partial lưu kết quả chuẩn hóa; lỗi provider không được biến thành dữ liệu thành công. |
| Tạo Dataset | Luồng analysis hiện vẫn lấy nguồn rồi lưu Dataset. Chưa có `PlatformDatasetRepository` để xây Dataset hoàn toàn từ Data Foundation đã lưu. |
| Builder/Preview | Tạo draft, chọn Dataset, cấu hình section/thứ tự/trang mặc định, preview snapshot. Chưa hoàn thiện publish/revision trong UI Builder. |
| Bundle backend | Có tạo/sửa draft, revision mới, publish provisional/final và Internal API đọc snapshot. |
| HTML/Excel | Luồng xuất file/lưu HTML/xuất bản cũ vẫn tồn tại song song; không xóa khi nối New. |

Phần source snapshots đã hoàn tất ngày **08/10/2026**:

- Migration **4 — source_snapshots** đã áp dụng lên PostgreSQL Docker. Migration 1–3 được đối chiếu bằng AST với HEAD và giữ nguyên; không thay schema Dataset/Report Bundle.
- Đã sửa regression tại `Worker._google_platform_refs`: lấy đúng mapping do cấu hình Google hiện tại trả về, không chọn lẫn tài sản cũ. Chưa có kết nối vẫn tạo kết quả lỗi từng nguồn trong job/Dataset, không tạo tài khoản hoặc số liệu giả.
- Chỉ cấu hình GA4 vẫn chạy được GA4. Khi chạy SEO mà thiếu cấu hình GSC/Sheets, nguồn thiếu được ghi `invalid_data`; các nguồn hợp lệ vẫn được xử lý. Cấu hình nguồn trống bị chặn trước request Google.
- Provider lỗi không ghi daily metrics/source snapshot mới cho nguồn đó. Lỗi persistence ghi `persistence_error`, trả kết quả `invalid_data` với thông báo an toàn. Ghi daily metrics, snapshot và kết thúc sync vẫn qua các thao tác storage riêng; không được mô tả là giao dịch nguyên tử cho toàn bộ sync.
- Kiểm thử: **py_compile đạt; platform data 12/12; Google success/failure 8/8; toàn bộ Python 135/135 (SQLite và PostgreSQL, không skip); UI 65/65; JS syntax, HTTP smoke và git diff --check đều đạt**. Provider được giả lập trong tests; chưa xác nhận lấy số liệu từ tài khoản provider thật.
- Đã sao lưu PostgreSQL trước khi nâng cấp, kiểm tra archive đọc được, rebuild Docker và xác nhận Admin/PostgreSQL healthy. Số tài khoản/Dataset/Bundle giữ nguyên.

Log cục bộ, không đưa vào Git: `test-results/foundation-full-tests.txt`, `foundation-platform-tests.txt`, `foundation-google-tests.txt`, `foundation-readiness-app-tests.txt`, `foundation-readiness-ui-tests.txt`, `foundation-http-smoke.txt`. Backup trước migration: `test-results/backups/postgres-before-source-snapshots-20261008-a3e7a9da.dump` (nội bộ, không đưa vào Git hoặc image).

## 5. GitHub và working tree của Report-New khác nhau

[Repository GitHub](https://github.com/bac2908/KDH-Report-New), main/HEAD đã đối chiếu bằng `git ls-remote`: **837f655525d4ee061c1e1365d1e47b57bba175f4** (`update layout`). Local `D:\KDH-Report-New` có cùng HEAD, branch `feat/admin-bundle-repository`.

**Bản trên GitHub:** các trang Overview/SEO/Facebook Content/Facebook Ads/TikTok/YouTube dùng `ReportService -> ReportRepository -> integrations.mock`. Sidebar liệt kê các kênh cố định. Có scaffold SQLAlchemy nhưng đường báo cáo hiện tại không sử dụng nó; không có database báo cáo thứ hai đang được nối vào luồng này.

**Bản local bổ sung chưa commit:** `.env.example`, `app/config.py`, `app/repositories/admin_bundle.py`, `tests/test_admin_bundle_repository.py`.

- `AdminBundleRepository` dùng HTTP backend, gửi Bearer token, gọi đúng endpoint Internal API, hỗ trợ revision, phân loại lỗi và kiểm tra contract 1.0/published status/report ID. Không fallback sang mock.
- Repository này **chưa được ReportService/routes sử dụng**. Có file không đồng nghĩa UI đã lấy dữ liệu thật.
- Chưa tìm thấy `BundleViewMapper` hoặc section resolver nối với Bundle. JSON Dataset trong Bundle khác cấu trúc mock mà template/JS đang dùng.
- `app/presentation.py` đã có helper render HTML từng phần để cập nhật giao diện; đây chưa phải mapper đọc Bundle. Các CLI trong `scripts/real_data_tests/` chỉ kiểm tra quyền/provider độc lập, chưa cấp dữ liệu cho UI và không được dùng làm đường provider của New trong kiến trúc đích.
- Chưa có luồng trang theo report ID/revision đã xuất bản và quyền người xem hoàn chỉnh.
- Compose của New chưa truyền `REPORT_ADMIN_BASE_URL`/`REPORT_SERVICE_TOKEN` và chưa khai báo network chung với Admin. Giá trị `127.0.0.1:8090` bên trong container New không chỉ đến container Admin.
- Kiểm thử riêng repository đọc Bundle vừa chạy khi rà soát: **10/10 đạt**, dùng `httpx.MockTransport`. Đây không phải kiểm thử tích hợp thật giữa hai container.

Các file cần đọc khi tiếp tục bên New: `app/repositories/admin_bundle.py`, `app/repositories/reports.py`, `app/services/reports.py`, `app/routes/pages.py`, `app/routes/reports.py`, `app/routes/video.py`, `templates/components/dashboard/navigation.html`, `static/js/pages/`, `compose.yaml`.

## 6. Hợp đồng giữa hai dự án

Chi tiết tại [report-bundles.md](report-bundles.md). Endpoint đã có:

```text
GET /api/internal/v1/report-bundles/{report_id}?revision=N
Authorization: Bearer <backend-only service token>
```

- Schema `1.0`: `report`, `client`, `period`, `comparison`, `freshness`, `quality`, `navigation`, `branding`, `sections`.
- ID `rpt_...` ổn định; mỗi revision là một snapshot riêng.
- Draft không xuất hiện qua Internal API. Bỏ `revision` sẽ lấy revision đã xuất bản lớn nhất (`provisional` hoặc `final`).
- Provisional là bản đã xuất bản tạm; final phải qua kiểm tra chất lượng. Chuyển provisional sang final không được thay nội dung snapshot.
- Section keys chuẩn: `overview`, `seo`, `facebook_content`, `facebook_ads`, `tiktok`, `youtube`, `gmb`.
- **Chênh lệch cần xử lý:** validator Admin hiện chỉ cho chữ thường/số/gạch ngang nên khóa các key Facebook dạng gạch dưới trong UI; New hiện dùng slug URL `facebook-content`, `facebook-ads`, `google-maps`. Cần thống nhất key contract và ánh xạ URL ở lớp trình bày, không tự đổi contract theo slug cũ.
- Chỉ render section mà Bundle có và cho phép; đồng thời kiểm tra khi truy cập URL trực tiếp, không chỉ ẩn menu.
- KPI giao diện New đang có nhưng Dataset thật chưa cung cấp phải hiển thị thiếu dữ liệu phù hợp, không lấy số mẫu để bù. Bộ lọc kỳ chỉ được dùng dữ liệu snapshot thực sự có; không nhân số liệu mẫu theo số ngày.

## 7. Trạng thái Docker đã kiểm tra

Admin và PostgreSQL kiểm tra lại ngày 08/10/2026; Report-New giữ mốc quan sát 07/10/2026:

| Container | Địa chỉ trên máy | Quan sát |
| --- | --- | --- |
| `kdh-report-admin-admin-1` | `http://localhost:8090` | Healthy |
| `kdh-report-admin-postgres-1` | PostgreSQL `localhost:5433` | Healthy; PostgreSQL 16 |
| `kdh-report-new-app-1` | `http://localhost:8080` | Healthy ở lần rà soát 07/10; không khởi động/cập nhật New trong bước 08/10 |

Sau triển khai 08/10, truy vấn kiểm tra xác nhận migrations **1, 2, 3, 4**, **1 user, 0 datasets, 0 report bundles, 0 source snapshots**; số user/Dataset/Bundle khớp trước nâng cấp. `/health` và trang Admin trả HTTP 200. Chưa có snapshot nguồn vì chưa có lần đồng bộ thành công tạo dữ liệu thật; không bù bằng mock. Trạng thái healthy không chứng minh hai ứng dụng đã nối dữ liệu.

Compose Admin hiện dùng `postgres-data` cho PostgreSQL; giữ `admin-data` cho file ứng dụng và dữ liệu SQLite cũ phục vụ rollback. Khóa mã hóa lấy từ `ENCRYPTION_KEY` cố định. Không xóa volume, đổi khóa hoặc tự chuyển dữ liệu SQLite cũ khi chưa có kế hoạch migration.

## 8. Thứ tự tiếp tục theo các phụ thuộc

1. **Đã xong 08/10:** sửa regression Google/Data Foundation và chạy lại các kiểm thử bắt buộc.
2. **Đã xong 08/10:** triển khai và kiểm chứng migration 4/source snapshots trên Docker, giữ dữ liệu cũ.
3. **Bước tiếp theo:** nối lớp tạo Dataset từ dữ liệu sync đã lưu (`PlatformDatasetRepository`); kiểm tra kỳ, nguồn, độ mới, chất lượng và lineage. Chưa tạo lớp này trong bước source snapshots.
4. Hoàn thiện hợp đồng section và luồng review/publish/revision của Admin dựa trên snapshot.
5. Nối New qua repository + mapper + section resolver; cấu hình kết nối giữa container; kiểm tra cùng report ID/revision từ Admin đến giao diện và file xuất. Không mặc định rằng mọi biểu đồ mẫu đã có nguồn dữ liệu thật.
6. Hoàn thiện quyền người xem bên New và phần quản trị tài khoản bên Admin; sau đó mở rộng từng provider có kiểm thử. Các vấn đề quyền phải được xử lý trước khi mở truy cập báo cáo riêng tư cho bên ngoài.

Các mục 3–6 vẫn chưa hoàn tất. Đợt 08/10 chỉ hoàn thiện source snapshots và xử lý regression của Admin, kiểm thử rồi triển khai Docker Admin. Không sửa code New, không commit hoặc push; các thay đổi người dùng đã stage được giữ nguyên.

## 9. Điểm bắt đầu cho lần làm tiếp

Đọc tài liệu này cùng [AGENTS.md](../AGENTS.md), [DATABASE_ARCHITECTURE.md](DATABASE_ARCHITECTURE.md) và [report-bundles.md](report-bundles.md). Kiểm tra `git status` của từng repo trước khi sửa, phân biệt code working tree với image/container đang chạy. Các quyết định đã chốt ở mục 1 không cần hỏi lại; chỉ cần làm rõ khi yêu cầu nghiệp vụ mới thay đổi phạm vi.

Các file Admin chính: `kdh/app.py` (API/auth), `kdh/google.py`, `kdh/meta.py` (provider), `kdh/jobs.py` (worker/sync), `kdh/platform_data.py` (Data Foundation), `kdh/migrations.py`, `kdh/core.py`, `kdh/postgres.py` (storage), `kdh/report_bundles.py`, `kdh/report_bundle_routes.py`, `static/app.js`, `static/views.js`, `compose.yaml`.
