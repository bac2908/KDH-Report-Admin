# Chạy KDH Report Admin bằng Docker

Compose chạy Flask/Waitress và worker nền trong service `admin`, cùng PostgreSQL 16 trong service `postgres`. Database nằm trong volume `kdh-report-admin_postgres-data`; file ứng dụng và SQLite cũ vẫn nằm trong `kdh-report-admin_admin-data`, gắn tại `/app/instance`. Khóa mã hóa lấy từ `ENCRYPTION_KEY`. Frontend và API dùng chung **http://localhost:8090**.

Trạng thái code/container, kết quả kiểm thử và phần còn cần làm được ghi tại [SYSTEM_CONTEXT.md](docs/SYSTEM_CONTEXT.md). Kiểm tra lại các test khi có thay đổi mới trước khi deploy.

## Chuẩn bị và khởi động

1. Mở Docker Desktop, dùng Linux containers.
2. Nếu chưa có `.env`, sao chép `.env.example` thành `.env`. Giữ file cấu hình hiện có nếu đang dùng dữ liệu cũ.
3. Điền `POSTGRES_PASSWORD` và `ENCRYPTION_KEY` cố định theo `.env.example`; giữ đúng khóa của dữ liệu mã hóa đang dùng. Compose tạo `DATABASE_URL` nội bộ tới service `postgres` từ cấu hình PostgreSQL. Đổi kết nối không tự chuyển dữ liệu SQLite cũ.
4. Đặt `LEGACY_REPORT_DIR` thành thư mục báo cáo HTML cũ trên máy. Nếu chưa có báo cáo cũ, tạo một thư mục rỗng và dùng đường dẫn đó. Thư mục được mount chỉ đọc.
5. Sau khi kiểm thử bản code cần triển khai đạt, chạy trong thư mục dự án:

```powershell
docker compose up -d --build --wait
docker compose ps
```

Mở **http://localhost:8090**. Endpoint `/health` trả `{"status":"ok"}` khi database hoạt động.

Nếu database đang kết nối chưa có tài khoản, tạo Admin qua terminal; lệnh hỏi mật khẩu và không ghi mật khẩu vào lịch sử lệnh:

```powershell
docker compose exec admin python run.py create-admin --email admin@example.com
```

Thay email minh họa bằng email của bạn. Nếu database PostgreSQL đã có tài khoản thì tiếp tục dùng tài khoản đó; tài khoản nằm trong SQLite cũ không tự xuất hiện ở PostgreSQL mới. Muốn có dữ liệu trình diễn riêng, vào **Cài đặt → Thêm dữ liệu demo** hoặc chạy:

```powershell
docker compose exec -T admin python run.py seed-demo
```

## Kết nối Google và Report-New

Các giá trị cho bản chạy trên máy:

```dotenv
APP_URL=http://localhost:8090
COOKIE_SECURE=0
GOOGLE_REDIRECT_URI=http://localhost:8090/api/google/callback
```

Điền `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` và các ID GA4/GSC/Sheets trong `.env`. Đăng ký đúng URI callback ở Google Cloud. Sau khi đổi `.env`, chạy `docker compose up -d --wait` để Compose tạo lại container với cấu hình mới.

Để backend Report-New đọc bundle, tạo `REPORT_SERVICE_TOKEN` ngẫu nhiên, điền cùng giá trị ở `.env` của Admin và môi trường backend Report-New. Compose **Admin** đã truyền biến này vào container. Compose New hiện chưa truyền token/base URL hoặc nối network với Admin; còn phải hoàn thiện phần đó và nối repository vào các trang báo cáo. Không đưa token vào JavaScript trình duyệt. Xem [hợp đồng Bundle](docs/report-bundles.md).

Compose cố định `JOB_MODE=worker` và `DATA_DIR=/app/instance`. Lịch tự động chạy bằng worker khi container hoạt động; không cần dịch vụ cron bên ngoài. Máy tắt/ngủ hoặc container dừng thì lịch cũng dừng, các lịch đến hạn được kiểm tra khi ứng dụng hoạt động lại.

Compose hiện dùng PostgreSQL và truyền `ENCRYPTION_KEY` vào container Admin. Cổng PostgreSQL mặc định trên máy là `127.0.0.1:5433`; Admin kết nối qua `postgres:5432` trong network Compose. Local SQLite cũ được giữ để rollback, không phải database chính của Compose. Không thay khóa mã hóa của database đang dùng.

## Vận hành và dữ liệu

```powershell
# Xem log
docker compose logs --tail 50 admin
# Tạm dừng, giữ dữ liệu
docker compose stop
# Khởi động lại
docker compose up -d --wait
# Sau khi cập nhật mã nguồn
docker compose up -d --build --wait
```

Không dùng `docker compose down -v` khi cần giữ dữ liệu: tùy chọn `-v` xóa volume. Image không chứa database hoặc secret. Trước khi nâng cấp, sao lưu PostgreSQL bằng công cụ backup phù hợp (hoặc sao lưu volume khi PostgreSQL đã dừng), giữ bản sao `admin-data` và lưu an toàn khóa `ENCRYPTION_KEY` tương ứng. Giữ cùng project name `kdh-report-admin` để tiếp tục dùng các volume cũ.

Cổng chỉ mở trên localhost. Nếu triển khai trên máy chủ cho người khác truy cập, cần cấu hình HTTPS qua reverse proxy, `APP_URL`, `COOKIE_SECURE=1` và Google callback theo tên miền thực tế.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd test
.\.venv\Scripts\python.exe tests/run_http_smoke.py
```

Test PostgreSQL cần `TEST_DATABASE_URL` trỏ vào database kiểm thử riêng. Mỗi test tạo schema ngẫu nhiên rồi tự dọn; không dùng database thật. Nếu không có biến này, các test PostgreSQL được đánh dấu bỏ qua. SQLite, HTTP smoke và test UI dùng dữ liệu riêng, không sửa volume đang vận hành.
