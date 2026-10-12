# Contract Admin → New

Đây là phần mở rộng tương thích của [report-bundles.md](report-bundles.md). Schema ngoài cùng vẫn là **`1.0`**.

## Envelope

| Trường | Ý nghĩa |
| --- | --- |
| `report.id`, `revision`, `status`, `name` | ID ổn định `rpt_<32 hex>`, revision nguyên dương; viewer chỉ nhận provisional/final |
| `client` | Khách hàng của báo cáo; phải khớp Dataset và quyền xem |
| `period`, `comparison` | Khoảng ngày chính/so sánh chụp cùng revision |
| `freshness`, `quality` | Thời điểm tạo/phát hành, trạng thái và cảnh báo |
| `navigation` | Danh sách section đã xuất bản và section mặc định |
| `sections[key]` | Dataset ID/type, valid, quality, vị trí và nội dung `data` đã chụp |
| `branding` | Nhận diện không chứa credential |

Key trình bày chuẩn: `overview`, `seo`, `facebook_content`, `facebook_ads`, `tiktok`, `youtube`, `gmb`. GA4/GSC/Keywords là nhóm nguồn trong SEO. Catalog còn các nhóm kỹ thuật khác; không tự thêm section thiếu dữ liệu vào navigation. New kiểm tra section trong URL trực tiếp, không chỉ ẩn menu.

## Nội dung Marketing release

`sections[key].data.dataset_kind = marketing_release_snapshot_v1`:

| Trường trong `data` | Nội dung |
| --- | --- |
| `id`, `client_id`, `created_at`, `params` | ID, khách hàng, thời gian, source, kỳ chính và kỳ trước |
| `sources` | Dữ liệu provider đã chuẩn hóa: totals/daily/previous/previous_daily hoặc entries, quality, freshness |
| `marketing.kind = approved_release`, `widgets` | Metric ID/label/unit/value, comparison, observations, status, verified/publishable do backend xác định |
| `evidence` | Evidence ID, metric, before/after, period, source, asset, lineage, verification và trạng thái duyệt |
| `opportunities` | Chỉ đề xuất đã được chọn; title/reason/action, supporting_data, evidence_ids, conditions, review_status=approved |
| `executive_summary` | Số KPI đã xác minh và giới hạn kết luận; không tự kết luận đạt mục tiêu |
| `platforms` | Metadata đúng 12 nguồn Catalog, có/không có trong snapshot |
| `release` | Version, origin/candidate IDs và hashes, approval ID, reviewer/time, checks, quality, policy, seal |

Seal là phong bì kiểm tra toàn vẹn bằng khóa chỉ Admin giữ. New không có khóa và không tự xác nhận seal: Admin kiểm tra trước khi trả Internal API, New kiểm tra contract lần nữa. Seal không phải access token hay quyền gọi provider.

## Quy tắc renderer

- Không đổi `null` thành `0`; không cộng KPI hoặc tính lại tỷ lệ từ dữ liệu ngày.
- Chỉ hiển thị kỳ trước/delta khi phạm vi comparison khớp Bundle. Biểu đồ so sánh lấy hai số đã lưu; không suy đoán giá trị.
- Giữ bảng/trend từ source snapshot; nguồn chưa có adapter có empty state.
- Opportunity chưa duyệt bị bỏ khỏi renderer khách hàng. Evidence legacy mang trạng thái chưa xác minh.
- Nội dung Marketing nội bộ/Candidate bị từ chối ở trang khách hàng. Preview nội bộ có contract và endpoint riêng.
- Schema lạ, report ID/revision sai, dữ liệu nhạy cảm, kiểu dữ liệu sai: trả lỗi an toàn, không fallback sang mock.
- Navigation/metric không có trong snapshot không được lấy bổ sung từ nguồn khác.

## Tính bất biến

Snapshot được chụp trong `report_bundles.snapshot_payload`. Revision mới có số mới; không sửa revision đã công bố. Receipt, các review/approval và registry release thuộc Admin, không trở thành API chỉnh sửa của New. Published reads không kiểm tra lại số liệu live để thay nội dung.
