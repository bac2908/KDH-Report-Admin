# Đưa KDH Report Admin lên Vercel + Neon

Bản này hỗ trợ Vercel bằng PostgreSQL: tài khoản, phiên đăng nhập, token Google đã mã hóa, dữ liệu CSV, kết quả phân tích, HTML và Excel đều được lưu trong database. `/tmp/kdh` chỉ là thư mục tạm. Dữ liệu Docker trên máy không tự chuyển lên cloud.

## 1. Tạo Neon trong Vercel

1. Mở dự án **kdh-report-admin** trong Vercel.
2. Chọn **Storage → Create Database**, tìm **Neon / Serverless Postgres**. Nếu không thấy, mở [Neon trong Vercel Marketplace](https://vercel.com/marketplace/neon/neon) và chọn **Install**.
3. Khi được hỏi, chọn **Create New Neon Account** nếu chưa có tài khoản. Chọn gói **Free / $0** nếu được cung cấp; xem lại giới hạn ở màn hình xác nhận.
4. Đặt tên, ví dụ `kdh-report-db`. Chọn khu vực gần nơi chạy Vercel Function; Singapore nếu cả hai dịch vụ đều cung cấp cho dự án của bạn.
5. Chọn **Connect Project → kdh-report-admin → Production**. Chưa dùng chung database thật cho các bản Preview.
6. Mở **Settings → Environment Variables** của dự án, kiểm tra có biến **DATABASE_URL**. Dùng chuỗi kết nối **pooled** do Neon cung cấp (hostname thường có `-pooler`), giữ nguyên các tham số SSL. Nếu tích hợp thêm tiền tố vào tên biến, chép giá trị ấy vào biến đúng tên `DATABASE_URL`.

Ứng dụng tự tạo bảng khi khởi động. Không cần tự viết SQL tạo bảng, cài Node driver hoặc đưa database URL vào mã frontend.

## 2. Thêm cấu hình Production

Trong **Settings → Environment Variables**, thêm các biến dưới đây, áp dụng cho **Production**. File [.env.vercel.example](.env.vercel.example) liệt kê đầy đủ các tên; không điền secret vào file example rồi commit.

| Tên | Giá trị |
| --- | --- |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL pooled từ Neon |
| `ENCRYPTION_KEY` | Khóa Fernet tạo bằng lệnh bên dưới; giữ nguyên qua mọi lần deploy |
| `APP_URL` | `https://kdh-report-admin.vercel.app` |
| `COOKIE_SECURE` | `1` |
| `JOB_MODE` | `request` |
| `DATA_DIR` | `/tmp/kdh` |
| `CRON_SECRET` | Chuỗi ngẫu nhiên tạo bằng lệnh bên dưới |
| `INITIAL_ADMIN_EMAIL` | Email bạn sẽ dùng đăng nhập admin |
| `INITIAL_ADMIN_PASSWORD` | Mật khẩu riêng cho admin, 12–200 ký tự |
| `GOOGLE_CLIENT_ID` | OAuth Web client ID của Google Cloud |
| `GOOGLE_CLIENT_SECRET` | Secret tương ứng của OAuth client |
| `GOOGLE_REDIRECT_URI` | `https://kdh-report-admin.vercel.app/api/google/callback` |
| `GA4_PROPERTY_ID` | `484358741`, hoặc property thực tế của bạn |
| `GSC_PROPERTY` | `https://kinderhealth.vn/`, phải khớp property tài khoản có quyền |
| `KEYWORD_SPREADSHEET_ID` | ID Google Sheet theo dõi từ khóa |
| `KEYWORD_SHEET` | `Ranking`, hoặc tên tab thực tế |
| `KEYWORD_TRACKING_YEAR` | Năm thực tế của file nếu tiêu đề chỉ có tháng/ngày; bỏ trống nếu ngày đã đầy đủ |
| `DASHBOARD_URL` | `https://kdh-report-admin.vercel.app/#reports`, hoặc URL dashboard online của bạn |

Tạo khóa trên PowerShell tại thư mục dự án. Lệnh chép khóa trực tiếp vào clipboard; dán vào **ENCRYPTION_KEY** trong Vercel rồi lưu:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" | Set-Clipboard
```

Sau đó tạo chuỗi riêng cho **CRON_SECRET**, dán và lưu:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))" | Set-Clipboard
```

Không tạo lại `ENCRYPTION_KEY` mỗi lần deploy: đổi khóa sẽ làm token Google cũ không đọc được. Giữ bản sao khóa ở nơi quản lý mật khẩu của bạn. Hai biến `INITIAL_ADMIN_*` chỉ tạo tài khoản khi database chưa có người dùng; thay chúng sau này không đổi mật khẩu tài khoản đã tạo. Đăng nhập thành công rồi có thể bỏ hai biến này khỏi Vercel.

Database mới sẽ có tài khoản admin mới và chưa có dữ liệu báo cáo. Bạn sẽ kết nối Google lại rồi chạy phân tích, hoặc thêm bộ demo ở bước 5. Lịch sử/CSV/báo cáo đang nằm trong Docker vẫn ở máy cũ; chuyển lịch sử cũ là thao tác di chuyển database riêng, không phải upload thư mục `instance` vào Git.

## 3. Cập nhật OAuth cho tên miền online

Trong Google Cloud, vào **Google Auth Platform → Clients → OAuth client loại Web application**:

- Thêm **Authorized redirect URI**: `https://kdh-report-admin.vercel.app/api/google/callback`.
- Giữ URI localhost nếu vẫn dùng bản Docker.
- Nếu ứng dụng OAuth ở chế độ Testing, thêm đúng email sẽ cấp quyền vào **Audience → Test users**.
- Tài khoản Google đó phải có quyền đọc GA4 property, Search Console property và Google Sheet. Đăng nhập Google thành công chưa chứng minh được quyền đọc từng nguồn.

Nếu đã thay secret của client trong Google Cloud, cập nhật giá trị mới ở Vercel. Không chụp hoặc gửi secret qua chat.

## 4. Đưa bản code mới lên và redeploy

Chỉ cập nhật bản Production sau khi hoàn tất các biến bắt buộc ở bước 2. Bản mới sẽ từ chối chạy nếu Vercel thiếu PostgreSQL hoặc khóa mã hóa, tránh âm thầm tạo database tạm.

1. Đưa các thay đổi mã nguồn hiện tại lên branch `main` của repository đã nối với Vercel. Kiểm tra `git diff` trước khi commit; không thêm `.env`, `instance`, backup hoặc secret.
2. Trong Vercel, **Settings → Build and Deployment**, chọn framework **Flask** nếu chưa được nhận diện. Root Directory là gốc repository. Giữ Output Directory mặc định của Flask, không đặt `dist`.
3. `vercel.json` đã đặt build command `python scripts/build_vercel.py` để đưa CSS/JS vào CDN, function `app.py` tối đa 300 giây, và cron hằng ngày. Không cần chạy `run.py` hoặc Docker bên trong Vercel.
4. Nếu việc push chưa tạo deployment mới, vào **Deployments → Redeploy** bản dùng code mới. Chỉ redeploy commit cũ sẽ không có các bản sửa PostgreSQL.
5. Mở `https://kdh-report-admin.vercel.app/health`: cần trả về `{"status":"ok"}`. Sau đó mở website và đăng nhập bằng tài khoản vừa cấu hình.

Vercel cài Python dependencies từ `requirements.txt`. Docker tiếp tục dùng `requirements.lock`. Thay biến môi trường cần deployment mới để ứng dụng nhận giá trị mới.

## 5. Kiểm tra có dữ liệu thực sự

1. **Kết nối nền tảng → Google → Kết nối Google**; cấp quyền bằng tài khoản có dữ liệu.
2. Xem kết quả kiểm tra từng nguồn; xử lý nguồn thiếu quyền hoặc property sai.
3. **Phân tích & Xuất Excel** → bỏ chọn **Dữ liệu demo**, chọn GA4 trước, chọn 7 hoặc 28 ngày đã qua → **Phân tích**.
4. Khi nguồn hợp lệ, thử **Xuất Excel**, **Lưu báo cáo**, mở lại HTML trong **Báo cáo đã lưu**.
5. Refresh, đăng xuất/đăng nhập lại. Sau một lần redeploy, báo cáo đã lưu vẫn phải còn. Kiểm tra Google vẫn kết nối bằng cùng khóa mã hóa.

Muốn có số liệu demo ngay: **Cài đặt → Thêm dữ liệu demo → Thêm bộ demo**. Tạo 6 HTML, dữ liệu GA4/GSC/keyword/GMB mô phỏng và Excel; chạy lại không nhân đôi. Kết nối Google thật được giữ nguyên. Các bản demo có nhãn rõ ràng và không được xuất bản thay báo cáo thật.

## Cách chạy tác vụ và giới hạn

Trình duyệt tạo tác vụ rồi gọi POST `/api/jobs/<id>/process`; API thực hiện công việc trước khi trả về. Hàng đợi, tiến độ và kết quả lưu trong PostgreSQL. Khóa giao dịch ngăn hai function cùng nhận một tác vụ. Không phụ thuộc thread tiếp tục chạy sau khi trả HTTP response.

- Giữ trang mở lúc tạo/phân tích/xuất file. Nếu tác vụ còn **Đang chờ** sau khi đóng trang hoặc mất mạng: vào **Lịch sử hoạt động → Chi tiết → Chạy tác vụ**. Admin hoặc người tạo được chạy tiếp.
- Nếu function bị dừng đột ngột, sau 6 phút lần kiểm tra tiếp theo đánh dấu **Bị gián đoạn**, có nút **Thử lại**. Khởi động một function mới không làm gián đoạn tác vụ đang chạy ở function khác.
- Giới hạn upload ở Vercel là 4 MB cho cả request (CSV nên nhỏ hơn 4 MB), Excel tối đa 4 MB. File lớn hơn cần kho file ngoài như Blob/S3 và luồng tải trực tiếp. Vercel có [giới hạn request/response 4,5 MB](https://vercel.com/docs/functions/limitations).
- Google có ngân sách thời gian trong mỗi lần xử lý. Nguồn chậm có thể trả lỗi timeout hoặc kết quả thiếu một phần; chọn từng nguồn hoặc khoảng ngày ngắn hơn để thử lại. Không tự lấy số liệu demo thay nguồn thật.
- Cron mặc định chạy `0 0 * * *` UTC, tức khoảng **07:00–08:00 Việt Nam**. [Vercel Hobby chỉ cho cron mỗi ngày và không bảo đảm đúng phút](https://vercel.com/docs/cron-jobs/usage-and-pricing). Lịch đặt trong admin được xử lý ở lần cron sau khi đến hạn; lịch 09:00 có thể đợi đến sáng hôm sau. Chọn giờ trước 07:00 để dùng với cấu hình hiện tại.
- Cron xử lý hàng đợi trong ngân sách khoảng 220 giây. Nếu có nhiều tác vụ/chậm, phần còn lại vẫn chờ lần gọi sau hoặc Admin chạy thủ công. Muốn lịch sát giờ hoặc tải lớn cần cron thường xuyên trên gói hỗ trợ, hoặc dịch vụ bên ngoài gọi `/api/cron` với `Authorization: Bearer <CRON_SECRET>`, hoặc worker thường trực.
- Cron chỉ chạy ở deployment Production. `CRON_SECRET` phải được cấu hình; request thiếu/sai secret nhận 401 theo [cơ chế xác thực cron của Vercel](https://vercel.com/docs/cron-jobs/manage-cron-jobs).

## Chẩn đoán nhanh

| Hiện tượng | Kiểm tra |
| --- | --- |
| `/health` lỗi 500 khi vừa deploy | Runtime Logs; có đúng `DATABASE_URL`, `ENCRYPTION_KEY`, `APP_URL` HTTPS, `COOKIE_SECURE=1`, `JOB_MODE=request` không? |
| `redirect_uri_mismatch` | URI ở Google Cloud và `GOOGLE_REDIRECT_URI` phải giống hoàn toàn |
| Đăng nhập được nhưng có 0 báo cáo | Database mới; cần phân tích rồi lưu hoặc thêm bộ demo |
| Google đã kết nối nhưng nguồn báo thiếu quyền | Email Google cần quyền trên từng property/file; bật các API tương ứng |
| Nút thao tác báo nguồn gửi không được phép | Truy cập đúng tên miền khớp `APP_URL`; không dùng URL Preview với cấu hình Production |
| Đang chờ mãi | Kiểm tra đã deploy cả JS mới và `JOB_MODE=request`; mở chi tiết tác vụ → Chạy tác vụ |
| Google lỗi sau khi đổi khóa | Khôi phục đúng `ENCRYPTION_KEY` đã dùng để mã hóa token |
| Cron nhận 401 | Kiểm tra `CRON_SECRET` của Production và redeploy sau khi sửa |

## Kiểm thử trước khi triển khai

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --experimental-vm-modules --test tests/ui.test.js
.\.venv\Scripts\python.exe tests/run_http_smoke.py
```

Kiểm thử PostgreSQL dùng `TEST_DATABASE_URL` trỏ vào **database kiểm thử riêng**. Mỗi bài tự tạo schema tên ngẫu nhiên, kiểm tra rồi xóa schema đó. Không dùng database Production để chạy test. Các bài kiểm tra bao gồm hai function đồng thời, giữ đăng nhập/token giữa hai instance, seed demo, HTML/Excel bền vững và ngăn chạy trùng.

Kiến trúc và cấu hình deployment đối chiếu [tài liệu Flask trên Vercel](https://vercel.com/docs/frameworks/backend/flask) và [Neon Marketplace](https://vercel.com/marketplace/neon/neon). Kiểm thử local không thay thế kiểm tra tài khoản Google và deployment cloud của bạn.
