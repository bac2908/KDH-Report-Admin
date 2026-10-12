# API tích hợp và phân quyền

## API dành cho Admin

Các request ghi yêu cầu cookie `kdh_session`, `X-KDH-Request: 1`, `X-CSRF-Token` và Origin hợp lệ nếu gửi. Các endpoint dưới đây yêu cầu vai trò Admin.

| Method | Route | Mục đích |
| --- | --- | --- |
| GET | `/api/marketing/workflow` | Chỉ mục snapshot có thể mở lại, metadata nguồn/tài sản, URL New công khai |
| POST | `/api/marketing/datasets` | Tạo Dataset từ source/start/end, tùy chọn asset_id và kỳ so sánh |
| GET/POST | `/api/marketing/datasets/{id}/review` | Đọc đánh giá; ghi decision/note/expected_sha256 |
| GET | `/api/marketing/datasets/{id}/release-readiness` | Xem điều kiện chuyển Candidate |
| POST | `/api/marketing/datasets/{id}/release-candidates` | Gửi expected_sha256 và expected_review_id |
| GET | `/api/marketing/release-candidates/{id}/source-check` | Kiểm tra nguồn, trả hashes và internal_review_id hiện hành |
| GET/POST | `/api/marketing/release-candidates/{id}/approval` | Đọc/ghi duyệt phát hành |
| POST | `/api/marketing/release-candidates/{id}/release-snapshots` | Tạo release bằng expected_approval_id + expected_candidate_sha256 |
| POST/GET | `/api/report-bundles` | Tạo/liệt kê Bundle |
| GET | `/api/report-bundles/{id}?revision=N` | Admin đọc đúng revision, gồm draft |
| POST | `/api/report-bundles/{id}/revisions` | Tạo revision mới |
| POST | `/api/report-bundles/{id}/revisions/{N}/publish` | Body status=provisional hoặc final |
| GET/POST | `/api/report-bundles/{id}/access` | Đọc/cập nhật quyền Viewer |

Body approval gồm `decision`, `note`, `expected_candidate_sha256`, `expected_dataset_sha256`, `expected_review_id`, tùy chọn `approved_opportunity_ids`. Quyết định là `release_approved` hoặc `release_blocked`. Client không được gửi các cờ `valid`, `provider_verified`, `publishable` để nâng quyền/trạng thái.

Body cấp quyền chính xác: `user_id`, `min_revision` (>=1), `max_revision` (>=min hoặc null), `active` (boolean). `max_revision=null` cấp cả revision tương lai trong báo cáo đó; UI mặc định giới hạn đúng revision đang mở. Grant vẫn giao với quyền loại báo cáo hiện có của user. Cấp grant không cho đọc draft.

## Server-to-server

Admin và New cùng cấu hình một `REPORT_SERVICE_TOKEN` riêng; chỉ backend New gửi `Authorization: Bearer <service token>`. Không dùng Google token làm service token.

| Method | Internal API | Bổ sung |
| --- | --- | --- |
| GET | `/api/internal/v1/report-bundles/{id}?revision=N` | API legacy chỉ dùng cho renderer đáng tin cậy / developer preview được bảo vệ |
| GET | `/api/internal/v1/viewer-session` | Kiểm tra session user |
| DELETE | `/api/internal/v1/viewer-session` | Thu hồi phiên hiện tại |
| GET | `/api/internal/v1/viewer/report-bundles` | Danh sách report/revision được cấp |
| GET | `/api/internal/v1/viewer/report-bundles/{id}?revision=N` | Snapshot đã xuất bản trong phạm vi user |
| GET | `/api/internal/v1/marketing-preview/{candidate_id}` | Chỉ user Admin hoạt động, không publication |

Mọi route trong bảng trừ legacy cần thêm `X-KDH-Viewer-Session: <phiên opaque>`. Backend Admin tra hash session, hạn dùng, trạng thái tài khoản, role/grant/client/revision và quyền loại báo cáo. Thiếu service identity hoặc session bị từ chối; token máy chủ không thay thế quyền của người xem.

New `POST /login` gọi API đăng nhập hiện có của Admin từ backend. Cookie `kdh_viewer_session` ở trình duyệt chứa phiên opaque, HttpOnly, SameSite=Lax; có Secure khi HTTPS. Không lưu service/provider token trong cookie, HTML, JS hoặc localStorage. `POST /logout` có CSRF và thu hồi phiên ở Admin.

## URL dùng trên New

- `/login`: đăng nhập bằng tài khoản ứng dụng do Admin quản lý.
- `/reports`: danh sách được cấp quyền, mỗi link pin revision.
- `/reports/{report_id}?revision=N&section=seo`: trang khách hàng; chỉ section có trong Bundle.
- `/internal-preview/{candidate_id}`: preview riêng, yêu cầu Admin.
- `/published/{report_id}`: developer preview cũ, Basic Auth + allowlist, đóng trong production.
- Các dashboard mock cũ và `/demo-bundles/...` bị đóng trong `APP_ENV=production`.

Danh sách viewer chọn revision mới nhất nằm trong grant. Nếu gọi trực tiếp report mà bỏ revision, API kiểm tra revision published mới nhất toàn report; có thể bị từ chối khi grant chỉ cho revision cũ. Dùng link đã pin từ danh sách để tránh nhầm.

## Lỗi vận hành

401: sai service credential hoặc session hết hạn. 403: sai quyền/CSRF. 404: không có report trong phạm vi hoặc revision chưa công bố. 409: snapshot/review không hợp lệ hoặc publication bị chặn. 502/503/504 tại New: contract hoặc kết nối Admin thất bại. Nội dung lỗi upstream và secret không được đưa vào giao diện.
