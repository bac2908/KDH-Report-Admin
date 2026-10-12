# Bàn giao KDH Marketing Reporting Platform

Cập nhật 10/10/2026. Đây là trạng thái **code local và kiểm thử**, không khẳng định runtime/GitHub tự nhận thay đổi.

## Đã hoàn thiện trong phạm vi Marketing

| Phase | Kết quả |
| --- | --- |
| 0 — Audit | Đọc cả hai working trees, giữ kiến trúc Flask/Vanilla JS và FastAPI/Jinja2; ghi [audit](marketing-remaining-implementation.md) |
| 1 — Verification/Approval | Receipt từ adapter, đối chiếu lineage/asset/kỳ/daily/snapshot; review/approval append-only gắn hash, block dữ liệu chưa đủ |
| 2 — Publication | Release Snapshot riêng có version/seal; guard giữ chặn Candidate; provisional/final qua policy; published revision bất biến |
| 3 — Admin/New | `/marketing` để vận hành duyệt, `/login` và `/reports` trên New, quyền user/report/revision, preview riêng cho Admin, KPI/Evidence/Opportunity đã duyệt |
| 4 — Tests/Handover | 295 tests Admin, 69 UI, 184 New; HTTP E2E, Chromium workflow/responsive và Docker smoke tách biệt; các tài liệu bên dưới |

New vẫn chỉ đọc HTTP từ Admin; không có database báo cáo thứ hai và không nhận token Google/Meta. Không thêm React/Vue, không tắt Publishing Guard, không ghi fixture vào DB KinderHealth.

## Tài liệu để vận hành

1. [Kiến trúc](KDH_ARCHITECTURE.md)
2. [Luồng dữ liệu, review và chính sách publish](KDH_DATA_FLOW.md)
3. [Report Bundle contract](KDH_REPORT_BUNDLE_CONTRACT.md)
4. [API, login và quyền Viewer](KDH_API_INTEGRATION.md)
5. [Provider đã hỗ trợ và phần BLOCKED](KDH_PROVIDER_STATUS.md)
6. [Kết quả kiểm thử và cách chạy lại](KDH_TEST_RESULTS.md)
7. [Chạy/nâng cấp Docker](KDH_DEPLOYMENT_GUIDE.md)

## Điểm vào sử dụng

- Admin → **Duyệt & phát hành** (`/marketing`): chọn snapshot đã lưu hoặc tạo mới, duyệt nội bộ, tạo Candidate, kiểm tra nguồn, chọn đề xuất, duyệt release, tạo Bundle, bấm publish, cấp quyền Viewer.
- New → `/login` → `/reports`: đăng nhập tài khoản ứng dụng đã được cấp quyền; link pin revision. Không dùng OAuth Google để đăng nhập người xem.
- Khi nguồn thiếu quyền: Source Check giải thích lý do block. Admin có thể mở `/internal-preview/{candidate_id}` trên New, vẫn chưa xuất bản.

## Triển khai và Git

- Admin HEAD được kiểm tra lúc tiếp tục: `5c3d657`, nhánh `main`; New HEAD `028d317`, nhánh `feat/admin-bundle-repository`. Có thay đổi local chưa commit. Không tự commit/push/merge/đổi branch trong đợt này.
- Migrations hiện tới **7**. Cần backup PostgreSQL và giữ nguyên ENCRYPTION_KEY trước khi nâng cấp ứng dụng.
- Đã tạo image Admin `marketing-qa-20261009`, New `marketing-qa-20261010` và smoke trong container tách biệt. Không tự thay thế ứng dụng tại cổng 8090/8080; làm theo deployment guide để cập nhật bản đang dùng.
- `.env` thật, volume runtime và cấu hình provider thật được giữ nguyên. `.env.example`/Compose được mở rộng cho URL New; chưa tự điền secret.
- Máy hiện có bind mount demo từ các thao tác trước; bản production mới đóng các route mock/DEMO của New. Dùng môi trường preview riêng khi cần minh họa.

## Phần còn chờ có điều kiện

1. **Provider thật:** cấp quyền và cấu hình GA4/GSC/Sheet, sync lại để có receipt; đối chiếu KPI với giao diện nguồn trước nghiệm thu dữ liệu kinh doanh.
2. **Các adapter chưa có:** Meta hiện OAuth-only, TikTok/YouTube/Google Ads/Instagram/CRM chưa có luồng xác minh này. Catalog không thay thế adapter. GMB CSV giữ luồng cũ, chưa phải provider-origin-confirmed.
3. **Ngoài phạm vi đợt này:** Owner/2FA, invitation/recovery qua email, quản lý công việc/targets của Agency và reverse proxy/domain public. Không hiển thị phần chưa có dữ liệu như đã đạt cam kết.

Kiểm tra trình duyệt đã thực hiện bằng Chromium headless có sẵn, trên DB tạm: tạo Dataset → duyệt → publish → grant → New render → revoke. Đã xem ảnh desktop/tablet/mobile và kiểm tra không tràn ngang. Lỗi đăng nhập do `Origin: null`, nút đăng xuất bị bỏ qua khi dùng bàn phím và nhãn trục tỷ lệ bị làm tròn trùng đã được sửa; CSRF và kiểm tra Origin vẫn giữ nguyên.

Receipt là xác nhận của backend được tin cậy, không phải kiểm toán độc lập của provider. Nhân viên duyệt nội dung không thể biến dữ liệu demo/thủ công thành chứng cứ provider bằng một checkbox.
