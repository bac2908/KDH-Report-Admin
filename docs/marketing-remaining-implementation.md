# Marketing platform — audit và kế hoạch thực hiện

Rà soát working tree ngày 09/10/2026. Không đồng nhất code local, GitHub và Docker.

## Điểm xuất phát

- Admin: `D:\KDH-Report-Admin`, branch `main`, HEAD `d005d2e`; có thay đổi chưa commit ở app, migrations, Publishing Guard và các module/test Marketing Dataset, Review, Release. Giữ lại các thay đổi này.
- New: `D:\KDH-Report-New`, HEAD `028d317`, branch `feat/admin-bundle-repository`; đã có nhiều thay đổi local về repository, mapper, service, route `/published`, template, CSS/JS và tests. Không tạo bản New thứ hai.
- Admin vẫn Flask/Vanilla JS; New vẫn FastAPI/Jinja2/Vanilla JS. New không đọc DB Admin.
- Migrations local 1–5: foundation, bundle snapshots, Meta OAuth, source snapshots, marketing dataset reviews. Chỉ bổ sung migration mới; không sửa lịch sử.
- Catalog có 12 nguồn; danh mục metric không chứng minh adapter/permission/data thực tế.
- Auth Admin có session, CSRF, admin/operator/viewer. Marketing Dataset/Review/Release và draft bundle chỉ Admin. Internal API dùng service credential riêng.

## Thành phần đã có

- Metric Catalog, Reader, Calculator, Reporting API, Evidence, Opportunity, Marketing Preview được đăng ký trong app.
- Marketing Dataset insert-only (`valid=0`), Review gắn hash, Candidate riêng sau internal approval.
- Guard chặn mọi Dataset Marketing nội bộ, kể cả provisional; không được loại bỏ guard này.
- Bundle schema 1.0 chụp snapshot; revision đã xuất bản không sửa nội dung. Internal API chỉ đọc published.
- New có mapper và giao diện responsive cho Bundle, không gọi provider. Baseline: 152 pytest đạt (4 cảnh báo deprecation).

## Lỗi/thiếu đã xác nhận

1. `marketing_source_check.py` chưa có; chưa có provenance từ adapter, source verification và release approval.
2. Candidate chỉ là bản staging nội bộ, chưa có release snapshot/guard contract được phép xuất bản.
3. Metric Reader loại bỏ dòng kỳ trước được lưu trong sync của kỳ hiện tại bởi điều kiện requested_start/end; cần đối chiếu snapshot và phạm vi kỳ trước, không mở rộng vô điều kiện.
4. Marketing Preview chưa chụp đủ daily observations/comparison phục vụ Dashboard và xác minh từng KPI.
5. New có `/published` nhưng production bị đóng, chỉ có Basic Auth preview allowlist; chưa có quyền Viewer theo report/revision.
6. New chưa có contract hiển thị Evidence/Opportunity đã duyệt; nguồn được gắn unverified. Key Facebook giữa Catalog/canonical sections và renderer chưa thống nhất hoàn toàn.
7. `docs/SYSTEM_CONTEXT.md` còn mốc 07–08/10, không phản ánh các module local mới.
8. Tài khoản provider chưa đủ quyền: không được tuyên bố nghiệm thu dữ liệu KinderHealth thật hoặc ghi fixture vào DB runtime.

## Thứ tự triển khai

1. Phase 1: kiểm tra lineage theo tenant/asset/kỳ, provenance do backend ghi nhận ở adapter, release review append-only gắn hash và version review; tests từ DB tách biệt. Succeeded/internal approval không thay thế provenance.
2. Phase 2: release snapshot riêng, policy provisional/final, mở rộng guard chặt chẽ và tương thích bundle 1.0; revalidate chain trước publication, giữ snapshot sau publication.
3. Phase 3: mở rộng mapper/templates New và quyền người xem qua backend; preview nội bộ riêng, không phục vụ draft từ endpoint khách hàng; cập nhật ví dụ môi trường/Compose, không sửa `.env` thật.
4. Phase 4: tests SQLite/PostgreSQL tách biệt, end-to-end Admin → New, UI và syntax; ghi tài liệu bàn giao và phần BLOCKED provider.

File chính dự kiến: Admin `metric_reader.py`, `marketing_preview.py`, module verification/publication mới, `google.py`, `jobs.py`, `migrations.py`, `app.py`, `report_bundles.py`, routes/tests; New repository/service/mapper/published routes/templates/tests. Chỉ sửa những phần cần cho luồng này.

## Nguyên tắc nghiệm thu

- Không tự commit/push, không đổi branch, không sửa secret, không ghi dữ liệu test vào PostgreSQL runtime.
- Mỗi suite phải có tests chạy thực sự; lưu số pass/fail/skip và tách xác minh kỹ thuật bằng fixture khỏi nghiệm thu provider thật.
- Không khẳng định hoàn tất phase cho đến khi kiểm thử phù hợp đạt. Kết quả cuối cập nhật trong `KDH_TEST_RESULTS.md` và `KDH_HANDOVER.md`.
