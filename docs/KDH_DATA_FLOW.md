# Luồng dữ liệu và duyệt báo cáo

## Từ provider đến Dataset

1. Admin cấu hình tài sản và kết nối tài khoản có quyền truy cập. Gmail đăng nhập thành công không đồng nghĩa GA4/GSC/Sheets có dữ liệu hoặc đã cấp đủ quyền.
2. Chạy phân tích/đồng bộ cho kỳ chính và kỳ trước. Adapter hiện hỗ trợ GA4, GSC và Keyword Sheet. Worker ghi `sync_runs`, `daily_metrics` và `source_snapshots`.
3. Sau response từ adapter thật, backend ghi receipt mã hóa gắn source, external asset, thông số job, sync ID và hash payload. Fake adapter, job demo, dữ liệu sửa tay, thiếu snapshot hoặc thiếu receipt không được xem là đã xác nhận nguồn.
4. Metric Reader đọc từ storage. Tổng unique users/rates/position lấy đúng tổng kỳ trong snapshot, không cộng các giá trị ngày. Kỳ trước có thể nằm trong cùng sync với kỳ chính nhưng phải khớp chính xác khoảng ngày. Nhiều asset không có quy tắc gộp thì bị chặn.
5. Marketing Dataset Builder chụp Preview, Evidence, Opportunity và metadata. Bản gốc luôn `valid=0`, chưa được xuất bản. Sau thời điểm này, review/builder/preview không gọi API provider.

## Từ review đến publication

| Bước trên `/marketing` | Điều kiện / kết quả |
| --- | --- |
| Tạo Dataset nội bộ | Chọn nguồn, kỳ, tài sản; đọc dữ liệu đã đồng bộ |
| Pending Review / Needs Changes | Chưa đủ dữ liệu hoặc người duyệt yêu cầu chỉnh sửa; tạo snapshot mới khi cần sửa nội dung |
| Approved Internal | Admin ghi ghi chú + hash Dataset; không phải xác nhận provider |
| Release Review | Tạo Candidate mới, tham chiếu Dataset/hash/review gốc |
| Source Check | So khớp client/provider/asset/connection/kỳ/metric/daily rows/snapshot/receipt và review hiện hành |
| Release Approved / Blocked | Quyết định append-only với reviewer, thời gian, ghi chú, checks, hash và danh sách Opportunity được chọn |
| Release Snapshot | Tạo Dataset mới có version, provenance, approval, policy và seal; không ghi đè bản gốc |
| Report Bundle Draft | Chọn một hoặc nhiều Release Snapshot làm section; xác định report ID/revision |
| Publish | Kiểm tra lại toàn bộ chuỗi trước khi công bố; nút publication là thao tác riêng |

`not_configured`, `permission_denied`, `no_data`, `partial`, `stale`, `lineage_consistent`, `provider_origin_confirmed` không đồng nghĩa nhau. Source Check tổng thể giữ `release_blocked` nếu có lỗi; xem `issues` và checks từng Evidence để biết nguyên nhân. `lineage_consistent` nghĩa là liên kết khớp nhưng vẫn thiếu xác nhận từ adapter.

Candidate có hash thay đổi, review/approval bị thay thế, người duyệt phát hành không còn là Admin hoạt động hoặc có lần sync mới hơn trong cùng phạm vi đều có thể chặn publication. Duyệt lại không làm hợp lệ dữ liệu bị sửa; phải tạo chuỗi snapshot mới.

## Chính sách phát hành

- **Draft:** nội bộ; service API dành cho người xem không đọc được.
- **Marketing Provisional:** vẫn cần nguồn đã xác minh, so sánh đủ kỳ, release approval hiện hành và seal hợp lệ. Không cho xuất bản Candidate nội bộ thiếu nguồn.
- **Marketing Final:** cùng các điều kiện trên, cộng guard Final hiện có: toàn bộ section hợp lệ và quality complete. Không hạ tiêu chuẩn Final.
- `complete` ở đây áp dụng dữ liệu/KPI đủ điều kiện trong snapshot, không có nghĩa toàn bộ 211 metric trong Catalog đều có số liệu. KPI thiếu vẫn để trống.
- Bundle legacy vẫn dùng chính sách cũ; không tự nâng provenance thành `provider_origin_confirmed`.

Khi đã công bố, đọc revision chỉ kiểm tra snapshot đóng băng và quyền đọc, không lấy dữ liệu live để sửa số. Muốn cập nhật, tạo Dataset/Release/Bundle revision mới. Thu hồi quyền xem báo cáo qua grants hoặc khóa tài khoản; không sửa nội dung revision cũ.

## Giới hạn kết luận

Opportunity là quy tắc có ngưỡng và bằng chứng, không phải dự báo tăng trưởng. Chỉ Opportunity được chọn khi phê duyệt mới được đưa vào release. Traffic tăng không chứng minh từ khóa lên Top Google. Chưa nhập/duyệt mục tiêu hoặc khối lượng công việc thì hiển thị chưa đủ cơ sở đánh giá cam kết, không tự tạo nhận định.
