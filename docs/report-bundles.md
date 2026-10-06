# Report Bundle API · contract 1.0

KDH-Report-Admin giữ dữ liệu và nghiệp vụ. KDH-Report-New chỉ đọc JSON đã lưu từ Internal API để hiển thị dashboard; không cần database riêng, provider token, adapter Google/Meta/TikTok hoặc logic tính lại KPI.

## Lưu trữ và nâng cấp

Migration **2 — `report_bundle_snapshots`** thêm `report_bundles.snapshot_payload` (TEXT) và index tra revision theo `bundle_key/status/revision`. Migration 1 được giữ nguyên. Runner thực thi từng câu DDL trong cùng giao dịch với `schema_migrations`; tránh `sqlite3.executescript` tự commit làm mất tính nguyên tử khi nâng cấp đồng thời.

- `report_bundles.id`: khóa nội bộ, không phải ID công khai.
- `bundle_key`: ID ổn định dạng `rpt_` + 32 ký tự hex.
- `(bundle_key, revision)` là duy nhất; mỗi revision có row riêng, `parent_id` trỏ revision liền trước. Hai request tạo revision đồng thời được tuần tự hóa bằng `BEGIN IMMEDIATE` trên SQLite hoặc advisory transaction lock hiện có trên PostgreSQL.
- Snapshot lưu toàn bộ JSON contract: thông tin client, branding, chất lượng và dữ liệu từng section. GET không join lại bảng dataset/client/settings và không gọi provider.
- `report_bundle_sections` lưu tham chiếu dataset và vị trí `0, 1, 2...` đúng theo thứ tự request. Dataset nguồn không bị sửa.
- Nếu tái sử dụng một dataset ID từ revision cha, nội dung snapshot đã chụp được kế thừa. Dữ liệu mới phải có dataset ID mới và revision mới.
- Bundle có từ trước migration 2 mà chưa có snapshot **không bị viết lại/backfill ngầm**. GET hoặc publish trả `409 snapshot_required`; Admin dùng endpoint tạo revision mới để chụp snapshot từ các dataset được tham chiếu. Các bảng HTML `reports`, `publications` và file cũ không bị thay đổi.

## Trạng thái

| Trạng thái | Sửa nội dung | Internal API | Chuyển tiếp |
| --- | --- | --- | --- |
| `draft` | Có, qua PATCH revision | Không, trả 404 | `provisional` hoặc `final` |
| `provisional` | Không; tạo revision mới nếu thay dữ liệu | Có | `final` khi snapshot đủ điều kiện |
| `final` | Không | Có | Không hạ trạng thái; tạo revision mới |

`provisional → final` chỉ đổi nhãn trạng thái. Dataset, chất lượng, branding, `generated_at` và thời điểm xuất bản đầu tiên giữ nguyên. Gọi lại cùng trạng thái đã đạt là idempotent. Tạo revision mới luôn bắt đầu ở `draft`, giữ nguyên report ID và client.

Mặc định Internal API trả **revision lớn nhất có trạng thái provisional/final**, không phải revision draft mới nhất. `?revision=N` chỉ đọc revision N nếu đã xuất bản. Xuất bản lại một revision cũ không thay thứ tự mặc định.

## Report Builder trong Admin

Report Builder hiện hỗ trợ nhập thông tin báo cáo và chọn một Dataset đã lưu để tạo bản nháp. Dataset có thể chọn được phát hiện từ `dataset_id` trong `/api/jobs` và `/api/reports`, sau đó đọc qua endpoint chi tiết `/api/datasets/{dataset_id}`; không có API liệt kê Dataset. Kỳ báo cáo phải khớp kỳ có trong snapshot. Admin tạo revision đầu tiên bằng `POST /api/report-bundles`; backend gán trạng thái `draft`. Khách hàng `client_kinderhealth` được chọn nội bộ, không qua bộ chọn khách hàng trên giao diện. Cấu hình section nâng cao, xem trước và xuất bản chưa thuộc luồng UI này.

## Xác thực và endpoint

Các endpoint Admin dùng cookie đăng nhập hiện có; mọi mutation cần `X-KDH-Request: 1` và `X-CSRF-Token` lấy từ đăng nhập hoặc `/api/auth/me`. Chỉ role `admin` đang hoạt động được quản lý bundle. Service kiểm tra lại quyền và phiên ngay trong giao dịch ghi.

| Method | Endpoint | Kết quả |
| --- | --- | --- |
| POST | `/api/report-bundles` | Tạo report ID, revision 1 draft; 201 |
| GET | `/api/report-bundles` | 200 revision gần nhất, gồm bản nháp |
| GET | `/api/report-bundles/{report_id}?revision=N` | Admin xem snapshot; bỏ N để xem revision mới nhất, kể cả draft |
| PATCH | `/api/report-bundles/{report_id}/revisions/{N}` | Sửa metadata/sections của draft |
| POST | `/api/report-bundles/{report_id}/revisions` | Tạo revision tiếp theo; 201 |
| POST | `/api/report-bundles/{report_id}/revisions/{N}/publish` | Body `{"status":"provisional"}` hoặc `{"status":"final"}` |
| GET | `/api/internal/v1/report-bundles/{report_id}?revision=N` | Đọc snapshot đã xuất bản bằng service Bearer token |

Không có mutation endpoint cho Report-New. Bearer token không cấp quyền vào API Admin; cookie Admin cũng không thay thế Bearer token ở Internal API.

Thêm `REPORT_SERVICE_TOKEN` vào môi trường backend Admin và backend Report-New, dùng cùng giá trị ngẫu nhiên đủ mạnh. Ví dụ tạo khóa tại máy quản trị:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Điền trực tiếp vào secret/environment của hai backend. Không đưa vào `NEXT_PUBLIC_*`, `VITE_*`, HTML, JavaScript trình duyệt, localStorage hoặc query string. Để trống trên Admin thì Internal API bị khóa (401). Token được so sánh bằng `secrets.compare_digest`; cookie bị bỏ qua hoàn toàn trên `/api/internal/`.

Header từ **server Report-New**:

```http
Authorization: Bearer <REPORT_SERVICE_TOKEN>
```

Thiếu/sai token → 401 kèm `WWW-Authenticate: Bearer`; token đúng nhưng report/revision không tồn tại hoặc chỉ là draft → 404. Revision sai định dạng → 400. Token không xuất hiện trong payload hoặc audit log. Phản hồi dùng `Cache-Control: no-store`; không bật CORS để đọc bằng trình duyệt.

## Ví dụ tạo và xuất bản

Lấy dataset ID từ kết quả phân tích đang có. Không truyền dữ liệu inline; tên section là khóa điều hướng của renderer, còn loại dữ liệu thực tế nằm ở `sections[key].report_type`.

```http
POST /api/report-bundles
Content-Type: application/json
X-KDH-Request: 1
X-CSRF-Token: <csrf_cua_phien_admin>
Cookie: kdh_session=<cookie_dang_nhap>
```

```json
{
  "client_id": "client_kinderhealth",
  "name": "KinderHealth tháng 9/2026",
  "start_date": "2026-09-01",
  "end_date": "2026-09-28",
  "default_section": "overview",
  "sections": [
    {"key": "overview", "dataset_id": "DATASET_GA4_DA_LUU"}
  ]
}
```

```json
{"report_id":"rpt_0123456789abcdef0123456789abcdef","revision":1,"status":"draft"}
```

Thay các ID minh họa bằng ID thực tế. Kỳ report phải khớp metadata dataset; không gắn nhãn tháng 10 lên dataset tháng 9. Có thể thêm `compare_start_date`, `compare_end_date` cùng nhau. Có thể thêm các section `seo`, `facebook-ads` nếu đã có dataset tương ứng; task này không tạo adapter để lấy dữ liệu Facebook.

Xuất bản:

```http
POST /api/report-bundles/rpt_0123456789abcdef0123456789abcdef/revisions/1/publish
```

```json
{"status":"provisional"}
```

Tạo revision mới sử dụng dataset mới, các metadata không gửi sẽ được kế thừa:

```http
POST /api/report-bundles/rpt_0123456789abcdef0123456789abcdef/revisions
```

```json
{"sections":[{"key":"overview","dataset_id":"DATASET_GA4_MOI"}]}
```

Body `{}` sao chép revision hiện tại thành một draft mới. `sections`, nếu gửi, thay cả danh sách; thứ tự danh sách quyết định position. Không nhận trường do server quản lý như `status`, `revision`, `bundle_key`, `parent_id`, dữ liệu dataset inline, token hoặc credential.

## JSON contract

Ví dụ dưới đây **minh họa contract với số liệu kiểm thử**, không phải số liệu kinh doanh thật:

```json
{
  "schema_version": "1.0",
  "report": {
    "id": "rpt_0123456789abcdef0123456789abcdef",
    "revision": 1,
    "status": "provisional",
    "name": "KinderHealth tháng 9/2026"
  },
  "client": {
    "id": "client_kinderhealth",
    "name": "KinderHealth",
    "slug": "kinderhealth",
    "timezone": "Asia/Ho_Chi_Minh"
  },
  "period": {"start": "2026-09-01", "end": "2026-09-28"},
  "comparison": null,
  "freshness": {
    "generated_at": "2026-10-01T02:00:00.000000+00:00",
    "published_at": "2026-10-01T02:10:00.000000+00:00"
  },
  "quality": {"status": "complete", "warnings": []},
  "navigation": {"default_section": "overview", "sections": ["overview"]},
  "branding": {},
  "sections": {
    "overview": {
      "dataset_id": "DATASET_GA4_DA_LUU",
      "report_type": "ga4",
      "created_at": "2026-10-01T01:55:00.000000+00:00",
      "valid": true,
      "position": 0,
      "quality": {"status": "complete", "warnings": []},
      "data": {
        "id": "DATASET_GA4_DA_LUU",
        "created_at": "2026-10-01T01:55:00.000000+00:00",
        "params": {"report_type": "ga4", "start": "2026-09-01", "end": "2026-09-28", "compare": false},
        "sources": {
          "ga4": {
            "source": "ga4",
            "status": "ready",
            "requested_start": "2026-09-01",
            "requested_end": "2026-09-28",
            "latest_available_date": "2026-09-28",
            "totals": {"sessions": 35, "activeUsers": null},
            "daily": [],
            "warnings": []
          }
        }
      }
    }
  }
}
```

- `comparison` luôn có mặt: object `{start,end}` hoặc `null` nếu không yêu cầu so sánh.
- `navigation.sections` là thứ tự hiển thị chuẩn. Mỗi section có `position` tương ứng.
- `sections[key].data` là nguyên dữ liệu JSON dataset đã lưu, không tính lại KPI. Schema con phụ thuộc `report_type`; giữ nguyên `null`, trường thiếu và hàng nguồn. Renderer phải hiển thị thiếu dữ liệu thay vì tự điền 0, đồng thời escape chuỗi nguồn khi dựng HTML.
- `quality` luôn có `status` và `warnings` (mảng chuỗi). Warning tổng có tiền tố section; warning từng section có nguồn khi xác định được.
- Timestamps dùng ISO 8601 UTC; ngày kỳ báo cáo dùng `YYYY-MM-DD`. `published_at` là `null` ở draft (chỉ Admin đọc được).
- Branding mặc định `{}`; không có chức năng upload logo trong task này.

## Chất lượng và điều kiện FINAL

Chất lượng được tính từ metadata **đã chụp**, không đọc lại trạng thái provider ở thời điểm GET/publish:

- `complete`: dataset hợp lệ, đủ nguồn bắt buộc, trạng thái nguồn hợp lệ, có ngày dữ liệu đến hết kỳ và metadata kỳ báo cáo phù hợp.
- `partial`: nguồn/kỳ so sánh còn thiếu, dữ liệu trễ, các section có chất lượng khác nhau, hoặc `datasets.valid=0` nhưng có dữ liệu một phần.
- `failed`: tất cả nguồn được lưu đều có trạng thái lỗi/trống/không kết nối.
- `unknown`: không đủ metadata để đánh giá. Không được coi là complete.

FINAL yêu cầu **mọi section** có `valid=true` và `quality.status=complete`. Nguồn bắt buộc của SEO là GA4/GSC/keywords như `TYPES` hiện có. Với loại dataset chưa có danh sách nguồn trong `TYPES`, tất cả nguồn được lưu trong `sources` được coi là bắt buộc. Mỗi nguồn phải có `latest_available_date >= end_date`. Nếu có ngày mới nhất của kỳ so sánh thì cũng kiểm tra với `compare_end_date`; dữ liệu so sánh không được thiếu. Đây là kiểm tra metadata, không khẳng định nhà cung cấp đã đóng sổ vĩnh viễn hay phát hiện mọi ngày rỗng trong khoảng kỳ.

Dữ liệu demo vẫn có thể tạo PROVISIONAL để kiểm thử, có warning DEMO và không được FINAL. Không tự seed hoặc thay lỗi nguồn bằng demo.

Dataset legacy chưa có `client_id` được coi là thuộc `client_kinderhealth`. Với client khác, dataset phải có `client_id` ở metadata gốc hoặc `params`, và mọi giá trị hiện diện phải khớp. API không cho sửa client của report ID đã tạo. Chưa triển khai phân quyền từng client hay pipeline sync đa khách hàng ở đây.

## Kiểm thử và trước khi merge

```powershell
# TEST_DATABASE_URL phải trỏ PostgreSQL kiểm thử riêng, không dùng Neon Production.
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd test
.\.venv\Scripts\python.exe tests/run_http_smoke.py
```

`tests/test_report_bundles.py` chạy cùng bộ contract trên SQLite và PostgreSQL khi có `TEST_DATABASE_URL`: validation, quyền Admin/CSRF/Bearer, revision đồng thời, snapshot không đổi, mọi trạng thái chất lượng, chuyển trạng thái, chặn credential, và không gọi lại provider. `test_platform_data.py` kiểm tra nâng cấp từ migration 1 giữ nguyên dữ liệu cũ. Bộ legacy vẫn kiểm tra Google/OAuth, Excel/HTML, jobs/schedules/login/demo.

Trước merge/deploy: backup database theo quy trình hiện có, kiểm tra migration 2 trên staging, thêm `REPORT_SERVICE_TOKEN` vào secret của hai backend và triển khai lại cùng code mới. Với Docker Compose, điền token vào `.env` rồi chạy `docker compose up -d --build --wait`. Giữ khóa mã hóa hiện có trong volume; deployment PostgreSQL cần giữ nguyên `ENCRYPTION_KEY`. Snapshot làm tăng kích thước database theo số revision. Token dịch vụ hiện đọc mọi bundle đã xuất bản; Report-New phải tự kiểm soát ai được xem report trước khi gọi server-to-server. Không đưa token tới khách hàng.

Chưa làm: UI tạo bundle (API đã hoạt động), tích hợp code ở repository KDH-Report-New, provider Meta/TikTok/YouTube, email, public share link, cron tạo bundle tự động, tải/lưu trữ ngoài cho bundle lớn, phân quyền service token theo client. Không merge vào main hay sửa database production tự động trong task này.
