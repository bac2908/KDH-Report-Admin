# Mở báo cáo Admin → New

Luồng hiện hành chỉ đăng nhập tại Admin. New bỏ form/API đăng nhập và danh sách riêng;
root, bookmark `/login` và `/reports` chuyển về Admin `/viewer/reports` để đăng nhập
và chọn báo cáo tại `/marketing`. Phiên xem hết hạn tự bắt đầu handoff cho đúng
report/revision; chỉ Admin hiển thị yêu cầu mật khẩu nếu phiên gốc hết hạn.

Sửa giao diện 14/10: `/viewer/reports` và `/viewer/authorize` khi chưa có phiên đều
dùng **trang đăng nhập Admin gốc** (`index.html` + `loginView` + CSS hiện có).
Đã bỏ form phụ `handoff_login.html` và script riêng. Không thay thiết kế đăng nhập,
không thay dashboard. Sau đăng nhập, đường chọn báo cáo đi tới `/marketing`; đường
handoff tải lại đúng transaction để backend kiểm tra và mở đúng report/revision.
Không nhận URL `next` tùy ý.

Cập nhật 14/10/2026. Phần handoff sử dụng migration 8 (`viewer_handoffs` và
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

Kiểm thử đợt bỏ đăng nhập riêng New: **338 Admin Python, 225 New pytest, 69 Admin UI,
1 HTTP E2E đều PASS, không skip**. Admin chạy cả SQLite và PostgreSQL riêng.
Chrome fixture PASS luồng chọn/click đúng revision, hết phiên/thu hồi, xung đột tài khoản,
preview, chart/filter/export và responsive 1440/768/390; không có lỗi JavaScript.
Log `test-results/admin-only-full-python.txt`, `admin-only-ui.txt`, `admin-only-http.txt`,
`admin-only-browser.txt`; kết quả browser `test-results/dashboard-binding/admin-only-result.json`.
Browser/scripts dùng DB tạm, không tạo báo cáo/quyền trên runtime khách hàng.

Ngày 14/10 đã build và cập nhật hai container local bằng `up -d --no-deps admin` /
`up -d --no-deps app`; Admin 8090, New 8080 và PostgreSQL đều healthy.
Backup trước triển khai: `test-results/backups/postgres-before-admin-only-20261014-082514.dump`
(1.116.320 byte, 171 archive entries); đã đọc toàn bộ payload bằng `pg_restore --file=/dev/null`.
Giữ nguyên `.env`, ENCRYPTION_KEY, service token, volume và thay đổi Meta đã stage.
Số tài khoản/Dataset/Bundle/source snapshot/daily metric trước và sau bằng nhau;
migration 1–8 vẫn đầy đủ. Lưu image cũ với tag `before-admin-only-20261014-082514`.

Kiểm tra HTTP runtime PASS: root/login/list về Admin, POST login New trả 405,
handoff/callback hiện diện, phiên hết hạn giữ report/revision, Internal API cần xác thực,
mock production trả 404. Hash file trong hai container khớp working tree.
Bằng chứng: `test-results/admin-only-deploy-before.json`, `admin-only-deploy-after.json`,
`admin-only-runtime-smoke.json`. Kiểm thử click đầy đủ ở trên chạy bằng Chrome với
fixture tách biệt; không sử dụng phiên Admin của người dùng hoặc nghiệm thu provider thật.

Lượt sửa giao diện đã rebuild riêng Admin ngày 14/10. Backup mới đã đọc đầy đủ:
`test-results/backups/postgres-before-restored-login-20261014-085150.dump`.
Đối chiếu `restored-login-deploy-before.json` / `restored-login-deploy-after.json`
giữ nguyên dữ liệu, volume, `.env`, file Meta đã stage và image New.
Chrome kiểm tra trực tiếp runtime 8090/8080 ở 1440 và 390px: form/geometry/style của
trang mở từ New bằng trang login Admin gốc, không gửi mật khẩu hoặc POST vào DB thật.
Log `test-results/restored-login-runtime-browser.txt`, kết quả và ảnh trong
`test-results/dashboard-binding/restored-login-runtime-result.json` và
`runtime-restored-admin-login-{1440,390}.png`. HTTP/hash container cũng PASS tại
`test-results/restored-login-runtime-smoke.json`. Chrome fixture đã chạy lại và PASS
luồng đăng nhập/mở báo cáo/hết phiên/thu hồi/409 qua chính trang đăng nhập gốc.
Kiểm thử lại sau sửa giao diện: **338 Python PASS / 0 FAIL / 0 SKIP** trên SQLite
và PostgreSQL (675,427 giây), **69 UI PASS**, **1 HTTP E2E PASS**. Log mới:
`test-results/restored-login-python.txt`, `restored-login-ui.txt`,
`restored-login-http.txt`, `restored-login-browser.txt`. JS syntax và diff check đạt.
