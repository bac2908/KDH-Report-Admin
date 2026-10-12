# Kết quả kiểm thử Marketing platform

Chốt ngày 10/10/2026. Dữ liệu trong tất cả ca thành công dưới đây là fixture độc lập; **không phải nghiệm thu dữ liệu KinderHealth thật**.

| Phạm vi | Kết quả | Bằng chứng cục bộ (Git ignored) |
| --- | --- | --- |
| Toàn bộ Python Admin, SQLite + PostgreSQL 16 | **295 PASS / 0 FAIL / 0 SKIP**, chạy 09/10, 394.606 giây | `test-results/marketing-full-python.txt` |
| Giao diện Admin JSDOM | **69 PASS / 0 FAIL**, gồm 4 ca workflow mới | `test-results/marketing-ui-final.txt` |
| Toàn bộ New pytest | **184 PASS / 0 FAIL**, 4 cảnh báo deprecation thư viện/template | New `.work/pytest-marketing-final.txt` |
| End-to-end qua HTTP thật giữa Flask và FastAPI | **1 PASS**: adapter fixture → release → publish → render → thu hồi quyền → Admin preview | `test-results/marketing-e2e-final.txt` |
| Chromium browser workflow | **PASS**, 7 màn hình × 3 kích thước 1440/768/390; không tràn ngang/lỗi JS; duyệt, publication, login, chart, menu, revoke | `test-results/marketing-browser-final.txt`, ảnh và `result.json` trong `test-results/marketing-browser/` |
| Docker builds Admin và New | Admin 09/10, New rebuild 10/10 thành công; không thay image tag/container runtime | `test-results/marketing-docker-build-admin.txt`, New `.work/marketing-docker-build-new-final.txt` |
| Hai container test gọi nhau | PASS: health, đăng nhập New qua Admin, danh sách có quyền, không lộ service credential | `test-results/marketing-docker-smoke-final.txt` |
| Metric Catalog | VALID: 12 nguồn, 211 định nghĩa | `python -m kdh.metric_catalog` |

## Những nhánh quan trọng đã kiểm tra

- Missing permission, sync failed, missing source snapshot, demo, thiếu kỳ, asset/client khác, snapshot/daily rows bị sửa.
- `succeeded` và human review không đủ xác nhận nguồn. Thiếu receipt, asset external ID thay đổi, review/approval/hash bị thay thế đều không tự hợp lệ.
- GA4 active users lấy tổng kỳ 22 thay vì cộng ngày thành 30 trong fixture. GSC comparison lấy đúng kỳ trước cùng sync. Keyword Top10 đếm từ snapshot vị trí, không cộng vị trí.
- Internal Dataset/Candidate tiếp tục bị chặn publication cả provisional và final. Release hợp lệ có version/seal riêng và không ghi đè bản gốc.
- Các ca legacy Bundle, migration, OAuth, export, worker, concurrent revisions và PostgreSQL vẫn đạt.
- Quyền xem kiểm tra service + phiên user, client, loại báo cáo và khoảng revision. Draft bị ẩn dù đã có grant. Thu hồi grant/session và khóa user có hiệu lực ngay.
- New không fallback mock; kiểm tra schema/metadata release, XSS/URL không an toàn, dữ liệu nhạy cảm, null/zero, missing/unsupported sections và Opportunity chưa duyệt.
- UI workflow gửi đúng hashes/CSRF, không tự xuất bản sau approval, không gọi provider để preview, mặc định pin grant/link vào revision đang xem.
- E2E thực tế dùng hai tiến trình Python và HTTP localhost, không chỉ gọi mapper trực tiếp. Provider transport được giả lập; API nội bộ Admin → New là thật.
- Browser kiểm tra form thật, chart SVG/tooltip, menu mobile/bàn phím, pin revision và revoke. Phát hiện và sửa login bị `Origin: null` do `Referrer-Policy: no-referrer`; policy mới `same-origin` giữ Origin form nội bộ, không gửi referrer sang origin khác. `Origin: null` vẫn bị từ chối, không nới CSRF.
- Nhãn trục biểu đồ tỷ lệ giữ đủ chữ số để phân biệt các mốc; số liệu/tooltip không thay đổi. Nút logout nằm trong vòng focus menu mobile.

## Lệnh chạy lại

Admin:

```powershell
npm.cmd test
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Get-ChildItem static/*.js | ForEach-Object { node --check $_.FullName }
git diff --check
.\.venv\Scripts\python.exe tests/run_marketing_e2e.py --new-root D:\KDH-Report-New
```

Để có PostgreSQL tests, đặt `TEST_DATABASE_URL` trỏ **database test riêng có thể bỏ**, tuyệt đối không trỏ DB runtime. Các test tạo schema UUID riêng rồi dọn schema đó. Đợt chạy 295 ca dùng container PostgreSQL riêng, storage tmpfs, không mount volume khách hàng. Không đặt biến này trong `.env` vận hành.

New:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
Get-ChildItem static/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }
git diff --check
```

Browser QA là runner tùy chọn, không thêm dependency production. Dùng thư mục module Playwright đã cài và Chromium tương ứng:

```powershell
Set-Location D:\KDH-Report-Admin
.\.venv\Scripts\python.exe tests/run_marketing_browser.py --new-root D:\KDH-Report-New --playwright-module C:\duong-dan\node_modules\playwright
```

Runner khởi động hai app ở cổng tạm, sync bằng transport fixture, thực hiện workflow qua browser, chụp ảnh rồi dọn app/DB tạm. Không trỏ vào PostgreSQL hoặc container đang dùng. Báo cáo QA được đặt tên DEMO; ảnh không phải số liệu kinh doanh thật.

## Giới hạn nghiệm thu

- **BLOCKED provider thật:** chưa có bộ tài khoản/quyền/dữ liệu đủ để đối chiếu GA4/GSC/Sheet của KinderHealth. Không đánh dấu PASS cho mục này.
- Browser dùng Chromium headless trên Windows; đã xem ảnh và kiểm tra bố cục ở 1440px, 768px và 390px. Đây không phải kiểm thử mọi loại thiết bị/browser.
- Docker build/smoke không phải nâng cấp container phục vụ tại 8090/8080. Image New kiểm thử ngày 10/10 đã chứa các sửa lỗi browser.
- Bốn cảnh báo deprecation của Starlette/AnyIO/template cũ không gây lỗi test; không tự nâng dependency ngoài phạm vi.
