# Chạy và nâng cấp bằng Docker

Cập nhật 10/10/2026. Admin ở `D:\KDH-Report-Admin`, New ở `D:\KDH-Report-New`. Không dùng Vercel cho luồng này.

## 1. Chuẩn bị cấu hình

Giữ nguyên `.env` và `ENCRYPTION_KEY` đang dùng. Chỉ tạo `.env` từ `.env.example` khi cài đặt mới; không chép đè cấu hình hiện tại.

| Ứng dụng | Biến | Giá trị / cách dùng |
| --- | --- | --- |
| Admin | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Thông tin PostgreSQL hiện có; Compose tạo DATABASE_URL trỏ `postgres:5432` |
| Admin | `ENCRYPTION_KEY` | Khóa Fernet cố định, lưu cùng kế hoạch backup; cần cho OAuth và kiểm tra release seal |
| Admin | `APP_URL` | URL trình duyệt mở Admin, local `http://localhost:8090` |
| Admin | `COOKIE_SECURE` | `0` ở HTTP localhost; `1` khi triển khai HTTPS |
| Admin | `JOB_MODE` | Compose dùng `worker` |
| Cả hai | `REPORT_SERVICE_TOKEN` | Cùng một chuỗi ngẫu nhiên riêng cho HTTP giữa hai backend |
| Admin | `REPORT_NEW_BASE_URL` | URL trình duyệt mở New, local `http://localhost:8080` |
| New | `APP_ENV` | Compose mặc định `production`: chỉ đường báo cáo có quyền, đóng mock routes |
| New | `DEBUG` | Compose đặt `false` |
| New | `REPORT_ADMIN_BASE_URL` | Compose hiện đặt `http://admin:8090` qua network chung |
| New | `REPORT_REQUEST_TIMEOUT_SECONDS` | Mặc định `5`; giới hạn cấu hình đến 30 giây |

New không cần DATABASE_URL của Admin. Các biến Google còn trong `.env.example` New dành cho script cũ; luồng báo cáo mới không sử dụng chúng. Chỉ cấu hình provider thật ở Admin theo [KDH_PROVIDER_STATUS.md](KDH_PROVIDER_STATUS.md).

Với **cài mới hoàn toàn**, có thể tạo giá trị ngẫu nhiên tại máy, rồi dán trực tiếp vào file cấu hình bảo mật:

```powershell
Set-Location D:\KDH-Report-Admin
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Dòng đầu là ENCRYPTION_KEY, dòng sau là REPORT_SERVICE_TOKEN. Không thay khóa mã hóa cũ bằng khóa mới để thử: token OAuth và các release cũ sẽ không giải mã/xác minh được. Không đưa giá trị vào Git, tài liệu hoặc chat.

Compose Admin hiện có bind mount báo cáo cũ và data pack demo từ cấu hình trước. `LEGACY_REPORT_DIR` và `KDH_DEMO_PACK_DIR` phải trỏ tới thư mục đang tồn tại nếu dùng Compose này; data pack đó không tham gia kiểm tra nguồn Marketing mới. Không đặt fixture vào dữ liệu KinderHealth để vượt guard.

## 2. Backup trước khi nâng cấp dữ liệu đang dùng

Lưu PostgreSQL dump và bản sao khóa mã hóa/cấu hình ở nơi riêng, không commit. Ví dụ tạo dump bên trong container rồi copy, tránh redirect dữ liệu nhị phân qua PowerShell:

```powershell
Set-Location D:\KDH-Report-Admin
New-Item -ItemType Directory -Force test-results\backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/kdh-before-marketing.dump'
docker compose cp postgres:/tmp/kdh-before-marketing.dump .\test-results\backups\kdh-before-marketing.dump
docker compose exec -T postgres pg_restore --list /tmp/kdh-before-marketing.dump
```

Dùng tên dump mới cho mỗi lần backup nếu đã có file cùng tên. Không xóa volume, reset migration hoặc restore đè database đang vận hành để thử nghiệm.

## 3. Build và khởi động

```powershell
Set-Location D:\KDH-Report-Admin
docker compose config --quiet
docker compose up -d --build
docker compose ps

Set-Location D:\KDH-Report-New
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Admin phải chạy trước để tạo network `kdh-report-admin_default` mà New dùng. Không đặt `REPORT_ADMIN_BASE_URL=http://localhost:8090` trong container New: localhost trong container là chính New.

Admin tự áp dụng migration còn thiếu khi khởi động, hiện tới version 7. DDL tăng dần; không reset dữ liệu. New không migrate DB Admin. Một worker Admin chạy trong tiến trình `run.py`; không tự tăng số bản worker khi chưa xử lý khóa/điều phối tương ứng.

Kiểm tra health:

```powershell
Invoke-RestMethod http://localhost:8090/health
Invoke-RestMethod http://localhost:8080/api/v1/health
```

Đăng nhập Admin bằng tài khoản hiện có. Với cài mới chưa có Admin, dùng lệnh tương tác hiện có trong container:

```powershell
docker compose exec admin python run.py create-admin --email admin@example.com
```

Lệnh hỏi mật khẩu tại terminal; thay email bằng tài khoản cần tạo. Không dùng lệnh tạo lại một tài khoản đã tồn tại.

## 4. Chạy luồng báo cáo

1. Admin `http://localhost:8090` → kết nối và đồng bộ nguồn đủ kỳ.
2. Vào **Duyệt & phát hành** hoặc `/marketing` → tạo Dataset → duyệt nội bộ → chuyển duyệt phát hành.
3. Đọc các kiểm tra nguồn. Nếu bị chặn, xử lý nguồn rồi tạo Dataset/Candidate mới; không sửa cờ bằng SQL.
4. Chọn từng đề xuất được duyệt → duyệt phát hành → tạo release snapshot.
5. Tạo Bundle và bấm xuất bản tạm/chính thức. Muốn nhiều section, dùng Report Builder với các release snapshots cùng kỳ.
6. Cấp tài khoản quyền loại báo cáo trong mục Người dùng; cấp thêm quyền report/revision ở `/marketing`.
7. Mở link New pin report ID/revision. Người xem đăng nhập tại New bằng tài khoản ứng dụng, không phải Gmail kết nối dữ liệu.

Chưa đủ provider permission vẫn xem được Candidate ở đường **xem trước nội bộ**, dành riêng Admin, nhãn chưa xác minh. Production không tự chuyển sang dashboard mock khi thiếu dữ liệu.

## 5. Preview và triển khai ra ngoài localhost

`compose.preview.yaml` của New là override phát triển riêng, dùng Basic Auth/allowlist cho `/published`. Chỉ dùng với dữ liệu test/demo tách biệt. `ENABLE_DEMO_PREVIEW` không mở được `/demo-bundles` trong production vì middleware vẫn chặn; không dùng override phát triển để phục vụ khách hàng thật.

Compose hiện bind port vào `127.0.0.1`. Khi cần truy cập từ bên ngoài, đặt reverse proxy HTTPS, cập nhật APP_URL/REPORT_NEW_BASE_URL, Google callback và cấu hình forwarded headers theo proxy tin cậy. Không đưa Postgres hoặc Internal service credential ra trình duyệt. Việc public domain/reverse proxy không được thực hiện trong đợt bàn giao code này.

## 6. Chẩn đoán

```powershell
docker compose logs --tail 100 admin
docker compose logs --tail 100 app
```

Chạy mỗi lệnh trong đúng thư mục repository. 401 giữa New/Admin: kiểm tra service token trùng nhau và phiên chưa hết hạn. Danh sách trống: chưa có Bundle đã xuất bản trong grant. 409 publication: đọc Source Check/review, không bypass guard. Docker không kết nối được: mở Docker Desktop trước. Healthy chỉ chứng minh ứng dụng chạy, không chứng minh provider đã có dữ liệu.

Không dùng `docker compose down -v`. Rollback ứng dụng giữ volume/khóa; không tự chạy migration ngược. Nếu cần khôi phục backup, thử trên database riêng trước.
