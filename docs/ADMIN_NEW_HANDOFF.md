# Mở báo cáo Admin → New

Cập nhật 13/10/2026. Phần handoff sử dụng migration 8 (`viewer_handoffs` và
`delegated_viewer_sessions`), router `kdh/viewer_handoff.py`, kiểm tra quyền chung
`authorized_bundle()` trong `kdh/viewer_access.py`, và nút mở đúng report/revision
trên `/marketing`. Không thay Published Guard, immutable Dataset/Bundle hoặc luồng
review/release. Preview chỉ cho Admin, không tạo grant/publication.

Tài liệu liên repo, bản đồ component, cấu hình, giới hạn, ảnh và lệnh rebuild:
[ADMIN_HANDOFF_DASHBOARD.md](../../KDH-Report-New/docs/ADMIN_HANDOFF_DASHBOARD.md).

Luồng: New tạo transaction với state/PKCE S256 và cookie ràng buộc trình duyệt →
Admin kiểm tra phiên + scope + ACL + guard → mã một lần 60 giây → callback New →
đổi mã qua Internal API có Bearer → phiên Viewer riêng → URL sạch đúng report/revision.
Mã chỉ lưu hash; redeem transaction nguyên tử. Không chia sẻ raw cookie Admin qua JS.
Token Viewer chỉ có đúng target/revision/mode; không dùng được để đăng nhập Admin.

Phiên gốc hết hạn/bị thu hồi, user khóa/mất role/grant làm request tiếp theo bị chặn.
New có tài khoản khác trả 409 và giữ nguyên tài khoản. Cùng trình duyệt còn phiên Admin
thì không cần mật khẩu; hết phiên thì login ở Admin và quay lại đúng giao dịch.

`APP_URL` của Admin phải khớp `REPORT_ADMIN_PUBLIC_URL` New.
`REPORT_NEW_BASE_URL` của Admin phải khớp `REPORT_NEW_PUBLIC_URL` New.
`REPORT_ADMIN_BASE_URL` New là URL backend Docker, không phải địa chỉ trình duyệt.
Không thay `.env`, khóa mã hóa hoặc provider/service credential trong đợt này.

Kiểm thử mới: `tests/test_viewer_handoff.py` chạy cùng cases trên SQLite và PostgreSQL
riêng; log đầy đủ `test-results/handoff-full-python-current.txt`. Browser/scripts dùng
DB tạm và tài khoản tổng hợp riêng, không tạo báo cáo/quyền trên runtime khách hàng.
Các thay đổi Meta xuất hiện trong working tree được giữ nguyên, không nằm trong việc
triển khai handoff này. Chưa nâng cấp container runtime; xem tài liệu liên repo trước
khi chạy `docker compose up -d --build admin` và New service `app`.
