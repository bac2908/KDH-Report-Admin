# Chạy KDH Report Admin bằng Docker

Compose chạy Flask/Waitress và worker nền trong service `admin`. SQLite, báo cáo, dữ liệu và khóa mã hóa nằm trong volume `kdh-report-admin_admin-data`, gắn tại `/app/instance`. Frontend và API dùng chung **http://localhost:8090**.

## Chuẩn bị và khởi động

1. Mở Docker Desktop, dùng Linux containers.
2. Nếu chưa có `.env`, sao chép `.env.example` thành `.env`. Giữ file cấu hình hiện có nếu đang dùng dữ liệu cũ.
3. Đặt `LEGACY_REPORT_DIR` thành thư mục báo cáo HTML cũ trên máy. Nếu chưa có báo cáo cũ, tạo một thư mục rỗng và dùng đường dẫn đó. Thư mục được mount chỉ đọc.
4. Chạy trong thư mục dự án:

```powershell
docker compose up -d --build --wait
docker compose ps
```

Mở **http://localhost:8090**. Endpoint `/health` trả `{"status":"ok"}` khi database hoạt động.

Nếu là volume mới chưa có tài khoản, tạo Admin qua terminal; lệnh hỏi mật khẩu và không ghi mật khẩu vào lịch sử lệnh:

```powershell
docker compose exec admin python run.py create-admin --email admin@example.com
```

Thay email minh họa bằng email của bạn. Volume cũ tiếp tục dùng tài khoản cũ, không cần tạo lại. Muốn có dữ liệu trình diễn, vào **Cài đặt → Thêm dữ liệu demo** hoặc chạy:

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

Để backend Report-New đọc bundle, tạo `REPORT_SERVICE_TOKEN` ngẫu nhiên, điền cùng giá trị ở `.env` của Admin và môi trường backend Report-New. Compose đã truyền biến này vào container. Không đưa token vào JavaScript trình duyệt.

Compose cố định `JOB_MODE=worker` và `DATA_DIR=/app/instance`. Lịch tự động chạy bằng worker khi container hoạt động; không cần dịch vụ cron bên ngoài. Máy tắt/ngủ hoặc container dừng thì lịch cũng dừng, các lịch đến hạn được kiểm tra khi ứng dụng hoạt động lại.

Compose hiện dùng SQLite và khóa ở `/app/instance/encryption.key`; `DATABASE_URL` và `ENCRYPTION_KEY` trong `.env` không được tự truyền vào container. Muốn dùng PostgreSQL cần cấu hình container riêng và kế hoạch chuyển dữ liệu. Không thay khóa mã hóa của database đang dùng.

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

Không dùng `docker compose down -v` khi cần giữ dữ liệu: tùy chọn `-v` xóa volume. Image không chứa database hoặc secret. Trước khi nâng cấp, sao lưu cả volume (gồm database và `encryption.key`) khi container đã dừng; giữ cùng project name `kdh-report-admin` để tiếp tục dùng volume cũ.

Cổng chỉ mở trên localhost. Nếu triển khai trên máy chủ cho người khác truy cập, cần cấu hình HTTPS qua reverse proxy, `APP_URL`, `COOKIE_SECURE=1` và Google callback theo tên miền thực tế.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd test
.\.venv\Scripts\python.exe tests/run_http_smoke.py
```

Test PostgreSQL cần `TEST_DATABASE_URL` trỏ vào database kiểm thử riêng. Mỗi test tạo schema ngẫu nhiên rồi tự dọn; không dùng database thật. Nếu không có biến này, các test PostgreSQL được đánh dấu bỏ qua. SQLite, HTTP smoke và test UI dùng dữ liệu riêng, không sửa volume đang vận hành.
