# KDH Report Admin

Ứng dụng quản trị báo cáo nội bộ KinderHealth, xây từ thiết kế Stitch trong `stitch_kdh_report_admin_frontend/`. Flask phục vụ cả API và frontend tiếng Việt. Docker/local dùng SQLite và worker; Vercel dùng PostgreSQL và tác vụ xử lý trong HTTP request. Không cần chạy một Node backend hay MongoDB riêng.

## Chạy trên Vercel

Làm theo [hướng dẫn Vercel + Neon](DEPLOY_VERCEL.md): tạo database, thêm các biến trong [.env.vercel.example](.env.vercel.example), cập nhật Google OAuth redirect URI rồi deploy code mới. Tài khoản, kết nối Google, kết quả, HTML và Excel được lưu trong PostgreSQL; `/tmp` không dùng làm nơi lưu dữ liệu lâu dài. Admin có thể thêm bộ demo ngay trong **Cài đặt**.

## Demo bằng Docker trên máy này

Image: `kdh-report-admin:demo`. Container: `kdh-report-admin-admin-1`. Truy cập **http://127.0.0.1:8090** bằng tài khoản và mật khẩu admin đã tạo trước đó.

Mở Docker Desktop, sau đó nhấp đúp **`demo.cmd`**. Script chờ container khỏe rồi mở trang ứng dụng. Hoặc chạy:

```powershell
cd D:\KDH-Report-Admin
docker compose up -d --wait
docker compose ps
```

Dữ liệu local hiện tại đã được chuyển sang volume `kdh-report-admin_admin-data`, bao gồm tài khoản, phiên đăng nhập, lịch sử, kết quả và khóa mã hóa. Bản sao trước khi chuyển nằm ở `instance/backups/docker-*`. Bản Python chạy ngoài Docker đã được dừng để nhường cổng 8090. Từ thời điểm này, dữ liệu sử dụng là dữ liệu trong volume Docker; thư mục `instance` trên Windows là bản local trước khi chuyển.

Các lệnh vận hành:

```powershell
docker compose stop
docker compose up -d --wait
docker compose logs --tail 50 admin
# Khi cập nhật mã nguồn:
docker compose up -d --build --wait
```

`stop`, `restart` và `up` giữ dữ liệu. Không dùng `docker compose down -v` nếu cần giữ tài khoản và báo cáo, vì `-v` xóa volume. Cổng demo chỉ mở trên máy này. Google OAuth vẫn cần cấu hình ở `.env` để trình diễn lấy dữ liệu Google thật; việc chạy Docker không tự cấp quyền Google.

Nếu mang sang máy khác: sao chép mã nguồn, cấu hình riêng của máy đó và chuyển volume nếu cần giữ tài khoản/dữ liệu; có thể tạo image bằng `docker compose build` hoặc xuất image bằng `docker save -o kdh-report-admin-demo.tar kdh-report-admin:demo`. Image không chứa tài khoản, mật khẩu, `.env` hay dữ liệu volume. Mount `/legacy` cần trỏ đúng thư mục báo cáo cũ trên máy đích.

## Bộ dữ liệu demo

Sau khi đã tạo tài khoản admin, thêm dữ liệu bằng lệnh sau (chạy lại không sinh bản trùng):

```powershell
docker compose exec -T admin python run.py seed-demo
```

Bộ mẫu gồm 28 ngày và kỳ so sánh trước đó: GA4, GSC, 48 từ khóa, 2 CSV cho 3 cơ sở GMB giả định, 6 báo cáo HTML, 9 tác vụ minh họa và một file Excel tải được. Dữ liệu lưu trong volume Docker, giữ nguyên qua khởi động lại. Không thay đổi tài khoản, mật khẩu, kết nối Google hay bản xuất bản hiện có.

Mở **Tổng quan → Khám phá báo cáo demo**. Trong **Phân tích & Xuất Excel**, giữ chọn **Dữ liệu demo** để đổi kỳ, chạy lại, so sánh, xuất Excel và lưu HTML mà không cần OAuth. Mỗi kết quả và file xuất đều có nhãn DEMO. CSV demo phải dùng chế độ demo và đúng kỳ ngày ghi trên file. Báo cáo demo không thay thế bản xuất bản chính thức.

Để lấy dữ liệu thật, bỏ chọn **Dữ liệu demo** rồi chạy lại với kết nối Google đã cấu hình hoặc CSV thật. Lỗi nguồn thật vẫn hiển thị lỗi; không tự chuyển sang số liệu mẫu. Các trạng thái kết nối Google trên Tổng quan và Kết nối Google luôn phản ánh kết nối thật. Lịch sử tạo sẵn được đánh dấu mô phỏng; nút Thử lại chạy một tác vụ demo mới.

## Chạy trên Windows

Yêu cầu Python 3.12 trở lên.

```powershell
cd D:\KDH-Report-Admin
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe run.py
```

Mở **http://127.0.0.1:8090**. Lần đầu, trên chính máy chủ, giao diện cho phép tạo **một tài khoản admin đầu tiên**, sau đó đăng nhập. Không có tài khoản mặc định, mật khẩu cứng hoặc đăng ký công khai. Các lần sau chỉ cần chạy `run.py`. Có thể dùng `powershell -File .\start.ps1` nếu chính sách PowerShell của máy cho phép chạy script.

Sau khi thiết lập, có thể tạo Admin / Người vận hành / Người xem ở màn hình Người dùng. Tài khoản đăng nhập admin và tài khoản Google cấp quyền nguồn là hai loại riêng.

Đặt lại mật khẩu từ máy chủ (mật khẩu nhập ẩn, không truyền trong dòng lệnh):

```powershell
.\.venv\Scripts\python.exe run.py reset-password --email ten@kinderhealth.vn
```

## Kết nối Google thật

Ứng dụng có adapter API thật, bộ dữ liệu demo được chọn riêng và không lấy credential từ dự án cũ. Cần cấu hình OAuth Web client một lần ở backend:

1. Trong Google Cloud project của đơn vị, bật **Google Analytics Data API**, **Google Search Console API**, **Google Sheets API**.
2. Thiết lập màn hình OAuth consent và tài khoản thử nghiệm nếu ứng dụng đang ở chế độ Testing.
3. Tạo OAuth client loại **Web application**, thêm đúng redirect URI `http://127.0.0.1:8090/api/google/callback`.
4. Chép `.env.example` thành `.env`, đặt `GOOGLE_CLIENT_ID` và `GOOGLE_CLIENT_SECRET`. Không gửi secret qua chat, không đưa vào frontend hoặc Git.
5. Khởi động lại ứng dụng, đăng nhập admin, mở **Kết nối Google → Kết nối Google**, cấp các quyền chỉ đọc.

Tài sản mặc định đã được đưa vào cấu hình:

- GA4 property: `484358741`.
- Search Console: `https://kinderhealth.vn/`.
- Google Sheet keyword: ID được đối chiếu từ script cũ, tab `Ranking`.
- Múi giờ báo cáo: `Asia/Ho_Chi_Minh`.

Tài khoản Google cần được chia sẻ quyền riêng trên cả ba tài sản. Trạng thái thiếu quyền / lỗi API / không có dữ liệu được ghi riêng. Kết nối có thể cần cấp lại khi hết hạn hoặc bị thu hồi.

Backend giữ access token và refresh token mã hóa bằng Fernet trong database. Docker/local dùng khóa ở `instance/encryption.key`; PostgreSQL/Vercel dùng biến `ENCRYPTION_KEY` cố định. Cookie đăng nhập là mã phiên ngẫu nhiên HttpOnly; token Google không được gửi xuống trình duyệt, không lưu trong localStorage. Khi ngắt kết nối, backend cố gắng thu hồi ở Google rồi xóa kết nối cục bộ; giao diện báo rõ nếu Google chưa xác nhận.

Tài liệu API đã đối chiếu: [Google OAuth Web Server](https://developers.google.com/identity/protocols/oauth2/web-server), [GA4 runReport](https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport), [Search Analytics](https://developers.google.com/webmaster-tools/v1/searchanalytics/query), [Sheets values.get](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/get).

## Luồng đã triển khai

| Màn hình | Chức năng |
| --- | --- |
| Đăng nhập | Tạo admin đầu tiên tại localhost, phiên 8 giờ, giới hạn đăng nhập sai, đăng xuất, khôi phục mật khẩu bằng CLI |
| Tổng quan | Trạng thái nguồn, ngày dữ liệu, lần thành công trước đó, báo cáo / tác vụ / xuất Excel gần nhất |
| Phân tích & Xuất Excel | SEO tổng hợp hoặc từng nguồn GA4/GSC/Keyword/GMB, chọn kỳ, so sánh kỳ trước, GSC loại trừ `/san-pham/`, biểu đồ và bảng, cảnh báo độ mới |
| Báo cáo đã lưu | Tạo HTML từ kết quả hợp lệ, nhập HTML cũ, xem trước trong sandbox, mở, tải, phiên bản, xuất bản nội bộ và chọn lại bản trước |
| Kết nối Google | OAuth do backend xử lý, kiểm tra riêng từng nguồn, kết nối lại / ngắt kết nối; chỉ admin |
| Lịch sử | Người chạy, tham số, thời gian, trạng thái từng bước, chạy lại lỗi, ngăn tạo trùng tác vụ đang chạy |
| Dữ liệu đầu vào | CSV UTF-8 đến 5 MB local (request 4 MB trên Vercel), preview, kiểm tra cột / số liệu / mã cơ sở, file trùng và kỳ chồng lấn |
| Lịch tự động | Ngày/tuần/tháng, giờ Việt Nam, 7/28 ngày đến hôm qua hoặc tháng trước, tạo bản nháp hoặc xuất bản nội bộ khi hợp lệ, bật/tắt |
| Người dùng | Ba vai trò, cấp quyền theo loại báo cáo, vô hiệu hóa, đổi mật khẩu và thu hồi phiên cũ |
| Cài đặt | Tên đơn vị và người lập, hiển thị chính sách múi giờ / phiên bản / xuất bản |

Viewer có thể phân tích và xuất Excel trong phạm vi báo cáo đã cấp; không tải CSV, lưu HTML, xuất bản, đổi nguồn hoặc quản lý người dùng. Operator được tải CSV, lưu và xuất bản báo cáo được cấp. Mọi quyền đều kiểm tra tại API, không chỉ ẩn nút.

## Quy tắc dữ liệu

- Tác vụ hoàn tất không đồng nghĩa tất cả nguồn hợp lệ. Kết quả có thể `partial` hoặc `failed`; nguồn thành công vẫn xem được.
- Mỗi nguồn có `requested_start`, `requested_end`, `latest_available_date`, `fetched_at`, `status`. Ngày có dữ liệu cuối cùng là ngày thực sự được nguồn trả về; không suy đoán ngày trễ cố định.
- GA4 KPI tổng được truy vấn riêng; không cộng active users theo ngày thành tổng kỳ. GSC KPI cũng lấy riêng; tổng hàng truy vấn có thể khác KPI.
- GSC dùng `web`, `dataState=final`, tối đa 25.000 hàng truy vấn đầu; cảnh báo nếu đạt giới hạn. Ngày GSC theo múi giờ nguồn `America/Los_Angeles`, được ghi riêng với múi giờ báo cáo.
- Không lấp khoảng ngày thiếu bằng 0; biểu đồ ngắt đoạn khi thiếu ngày.
- Kỳ so sánh là số ngày bằng kỳ hiện tại, kết thúc trước ngày bắt đầu một ngày. Nếu thiếu kỳ so sánh, vẫn xem được dữ liệu hiện tại nhưng phải bỏ so sánh hoặc sửa nguồn trước khi xuất.
- Đổi bộ lọc chưa bấm Xem báo cáo sẽ khóa xuất Excel / lưu HTML. Khoảng ngày ghi bên kết quả luôn là bộ lọc đã áp dụng.
- Mỗi lần phân tích tạo một dataset bất biến. Excel lấy từ dataset đó, không gọi lại API nguồn.
- Excel có metadata, ngày kiểu Excel, chỉ số dạng số, tỷ lệ 0–1 có nhãn đơn vị. Chuỗi từ nguồn được ép kiểu text để tránh công thức trong ô.
- Nguồn lỗi/thiếu không được xuất Excel hoặc tạo bản HTML hợp lệ; không thay bản đã xuất bản trước đó.

### Google Sheets Ranking

Hỗ trợ bảng dài: `Từ khóa, Vị trí, URL, Ngày` (tên tiếng Anh tương đương cũng được). Ngày có năm: `YYYY-MM-DD`, `DD/MM/YYYY`, hoặc `Jul/16/2026`.

Hỗ trợ bảng rộng, mỗi cột là ngày tracking. Nếu header chỉ có `Jul/16` hoặc `7/16`, quản trị backend cần đặt `KEYWORD_TRACKING_YEAR` bằng **năm dữ liệu thật**; ứng dụng không tự gắn năm hiện tại cho dữ liệu cũ. Cột ngày đầy đủ năm vẫn được ưu tiên giữ nguyên. Giá trị ngày/vị trí sai sẽ báo nguồn không hợp lệ, không chuyển sang dữ liệu mẫu.

### CSV Google Business Profile

Hỗ trợ CSV Performance Report của Google, gồm `Store code`, `Business name`, bốn cột lượt xem Search/Maps mobile/desktop, `Calls`, `Directions`, `Website clicks`. Bỏ đúng dòng mô tả cột của Google nếu có. Mã cơ sở vẫn giữ kiểu text kể cả có số 0 đầu.

Cũng hỗ trợ schema đơn giản trong `static/gmb-template.csv`. File mẫu chỉ có tiêu đề, không có số liệu giả.

Người tải chọn kỳ CSV. Nếu tên file có hai ngày thì phải khớp kỳ đã chọn. Cùng cơ sở không được có kỳ chồng lấn. Khi tạo báo cáo, kỳ phải khớp toàn bộ file CSV; ứng dụng không chia tỷ lệ số tổng thành số liệu ngày. So sánh GMB cần hai file khớp hai kỳ và cùng tập mã cơ sở.

## Tích hợp dự án KDH-Report cũ

`LEGACY_REPORT_DIR` mặc định trỏ đến `D:/KDH-Report/KDH-Report`. Admin bấm **Báo cáo đã lưu → Nhập báo cáo cũ** để sao chép nội dung bảy HTML theo danh sách tên file cố định. Thao tác không chạy script, không chỉnh file hoặc credential ở dự án cũ. Nhập nhiều lần không tạo trùng cùng nội dung.

HTML cũ được ghi **chưa kiểm chứng dữ liệu**, không tự suy luận kỳ dữ liệu từ ngày sửa file. Chúng được xem/tải nhưng không được xuất bản lại qua luồng dữ liệu hợp lệ. Đặc biệt, `generate_seo_report.py` cũ có fallback sang số liệu mẫu khi lỗi nguồn, nên ứng dụng này dùng adapter Google riêng. `creator-backend` là backend Node/MongoDB cho nền tảng nội dung, có phạm vi khác; không được ghép làm backend tài khoản thứ hai.

Facebook Ads, Facebook Content 7/30 ngày/6 tháng và TikTok hiện có **thư viện HTML đã lưu**. Tạo mới trực tiếp từ các API này cần adapter riêng kiểm chứng dữ liệu. Không trình bày chúng như đã kết nối bằng Google OAuth.

Xuất bản hiện là **xuất bản nội bộ trong admin**, không public và không đẩy GCS. GCS, chỉnh KPI mục tiêu, upload logo, tự xóa phiên bản và bộ tạo mới Facebook/TikTok nằm ngoài bản chạy đầu này. Không có nút giả báo thao tác đã thành công.

## Vận hành Docker/local

- Một process Waitress và một worker nền. File lock ngăn chạy hai server cùng thư mục dữ liệu. Đây là cấu hình cho một đơn vị, không phải hàng đợi phân tán.
- Tác vụ chờ được lưu SQLite. Tác vụ đang chạy khi server dừng sẽ chuyển `interrupted` ở lần mở lại, có thể thử lại.
- Lịch dùng timezone IANA Việt Nam. Khi mở lại sau thời gian tắt, xử lý một lần bị lỡ rồi tính lần tới; không chạy bù toàn bộ lịch sử.
- Với Docker/local: SQLite ở `instance/kdh.sqlite3`, khóa mã hóa ở `instance/encryption.key`. Excel mới lưu trong database; Excel của bản cũ vẫn đọc từ `instance/exports/`. Dừng server trước khi sao lưu toàn bộ `instance` (hoặc dùng SQLite backup API cho backup khi đang chạy). Giữ khóa mã hóa cùng bản sao lưu trong kho nội bộ hạn chế quyền đọc.
- Không đưa `instance`, `.env`, credential vào Git, thư mục web hoặc bản chia sẻ frontend. Các thư mục này đã được loại trong `.gitignore` / `.dockerignore`.
- Khi triển khai ngoài localhost, đặt HTTPS reverse proxy, `APP_URL` đúng origin, `COOKIE_SECURE=1`, redirect URI HTTPS đúng trong Google Cloud. Cấp quyền đọc/ghi thư mục dữ liệu cho tài khoản dịch vụ, không cho người dùng không liên quan.
- Chỉ expose cổng admin sau lớp mạng nội bộ theo nhu cầu đơn vị. Các API dữ liệu đều yêu cầu đăng nhập.

### Demo Render Free

Để tạo admin đầu tiên khi không có Shell, đặt `INITIAL_ADMIN_EMAIL` và `INITIAL_ADMIN_PASSWORD` trong Environment của Render. Khi database chưa có user, ứng dụng tạo admin với toàn quyền; mật khẩu phải dài 12–200 ký tự. Nếu database đã có user, các biến này không thay đổi tài khoản hiện có. Không commit các giá trị này vào Git. Render Free không có persistent disk, vì vậy database, tài khoản và báo cáo có thể mất khi service được triển khai lại hoặc khởi động lại; chỉ dùng cho demo tạm thời.

Docker là tùy chọn; chưa cần cho bản local:

```powershell
docker compose up -d --build
docker compose exec admin python run.py create-admin --email ten@kinderhealth.vn
```

Compose mount dự án cũ chỉ đọc và volume riêng cho dữ liệu admin. Tạo admin bằng CLI vì kết nối qua Docker không phải loopback của container.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
npm.cmd ci --ignore-scripts
npm.cmd test
.\.venv\Scripts\python.exe tests/run_http_smoke.py
```

Hiện có 36 test Python (gồm 5 bài PostgreSQL cần `TEST_DATABASE_URL` riêng, tự bỏ qua khi chưa cấu hình), cùng 8 test giao diện trong `tests/ui.test.js`. Python dùng `unittest`, Flask test client, SQLite tạm và schema PostgreSQL riêng cho từng bài; giao diện dùng Node test runner và JSDOM với HTTP API giả lập. Các test dùng cấu hình OAuth riêng, không phụ thuộc Client ID/Secret thật trong `.env`. Xem [hướng dẫn kiểm thử PostgreSQL](DEPLOY_VERCEL.md#kiểm-thử-trước-khi-triển-khai).

Test Python kiểm tra auth/CSRF/phân quyền, queue, dữ liệu thiếu/độ trễ, Excel theo snapshot, công thức độc hại, CSV, phiên bản/xuất bản, OAuth state, lịch chạy và chế độ demo. Test DOM kiểm tra đăng nhập, bộ lọc chưa áp dụng, export, điều hướng, chuyển demo/thật và xóa dữ liệu phiên cũ khi hết hạn. Dữ liệu giả trong kiểm thử và bộ demo được chọn riêng; lỗi nguồn thật không tự dùng dữ liệu mẫu.

`tests/run_http_smoke.py` tự mở Waitress cùng worker ở cổng 8091, chạy chuỗi đăng nhập → upload CSV → phân tích → tải Excel → lưu/xem HTML → xuất bản → đăng xuất, rồi dừng server. Mỗi lần chạy dùng một thư mục dữ liệu mới `test-results/http-smoke-*`, giữ các file kiểm thử để kiểm tra lại; không dùng dữ liệu Docker hoặc `instance`. Nếu cổng 8091 đang được dùng, lệnh dừng trước khi gửi yêu cầu. Có thể chạy lặp lại mà không xóa dữ liệu test cũ.

Các bài test tự động này chưa đo tỷ lệ bao phủ code, chưa kiểm tra giao diện bằng trình duyệt thật (Playwright/Selenium), chưa kiểm thử tải và chưa có workflow CI trong repository. Luồng cấp quyền OAuth và số liệu Google thật cần kiểm tra với tài khoản được cấp quyền trên các tài sản của đơn vị; JSDOM và adapter giả lập không xác nhận được những quyền đó.

Để mở máy chủ UI test riêng: `.\.venv\Scripts\python.exe tests/serve_ui.py` tại cổng `8091`. Dữ liệu test nằm ở `test-results/ui-state`, không dùng `instance` của ứng dụng thật.
