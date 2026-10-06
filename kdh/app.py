import io
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, g, jsonify, redirect, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .core import ROOT, TYPES, TZ, GOOD, Store, Problem, allowed, digest, filters, load_config, now, pack, public_user, uid
from .google import Google, SourceError, LABELS
from .jobs import Worker, enqueue, job_view, next_run, period_dates
from .reports import import_legacy, publish, save_report, save_upload, valid_dataset
from .report_bundle_routes import register_report_bundle_routes


def _bootstrap_initial_admin(store, email, password):
    if store.one('SELECT id FROM users LIMIT 1'):
        return
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError('Set INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD together.')

    email = email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise RuntimeError('INITIAL_ADMIN_EMAIL must be a valid email address.')
    if not 12 <= len(password) <= 200:
        raise RuntimeError('INITIAL_ADMIN_PASSWORD must be between 12 and 200 characters.')

    password_hash = generate_password_hash(password)
    with store.connect(immediate=True) as db:
        if db.execute('SELECT id FROM users LIMIT 1').fetchone():
            return
        actor = uid()
        db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)',
                   (actor, email, 'Quản trị viên', password_hash, 'admin', pack(list(TYPES)), 1, now()))
    store.event(actor, 'setup')


def create_app(overrides=None):
    app = Flask(__name__, static_folder=str(ROOT / 'static'), template_folder=str(ROOT / 'templates'))
    app.config.update(load_config())
    app.config.update(overrides or {})
    if app.config['JOB_MODE'] not in ('request', 'worker'):
        raise RuntimeError('JOB_MODE must be request or worker.')
    store = Store(app.config['DATA_DIR'], app.config['DATABASE_URL'])
    _bootstrap_initial_admin(store, app.config['INITIAL_ADMIN_EMAIL'], app.config['INITIAL_ADMIN_PASSWORD'])
    google = Google(store, app.config)
    worker = Worker(store, google)
    app.extensions.update(store=store, google=google, worker=worker)
    dummy_hash = generate_password_hash(secrets.token_urlsafe(32))

    def local_setup():
        return (request.remote_addr in ('127.0.0.1', '::1') and
                urlsplit(request.host_url).hostname in ('127.0.0.1', 'localhost', '::1') and
                not request.headers.get('X-Forwarded-For') and not store.one('SELECT id FROM users LIMIT 1'))

    def body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise Problem('Yêu cầu phải là một đối tượng JSON.')
        return value

    def require(*roles):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user:
                    raise Problem('Phiên đã hết hạn. Vui lòng đăng nhập lại.', 401)
                if roles and g.user['role'] not in roles:
                    raise Problem('Bạn không có quyền thực hiện thao tác này.', 403)
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    def check_report(report_type):
        if report_type not in TYPES or not allowed(g.user, report_type):
            raise Problem('Bạn chưa được cấp quyền cho báo cáo này.', 403)

    def get_dataset(dataset_id):
        row = store.one('SELECT * FROM datasets WHERE id=?', (dataset_id,))
        if not row:
            raise Problem('Không tìm thấy kết quả báo cáo.', 404)
        check_report(row['report_type'])
        return json.loads(row['data'])

    def get_report(report_id):
        row = store.one('SELECT * FROM reports WHERE id=?', (report_id,))
        if not row:
            raise Problem('Không tìm thấy phiên bản báo cáo.', 404)
        check_report(row['report_type'])
        return row

    def get_job(job_id):
        row = store.one('SELECT * FROM jobs WHERE id=?', (job_id,))
        if not row:
            raise Problem('Không tìm thấy tác vụ.', 404)
        if row['kind'] == 'connection' and g.user['role'] != 'admin':
            raise Problem('Bạn không có quyền xem tác vụ kết nối.', 403)
        check_report(json.loads(row['params'])['report_type'])
        return job_view(row)

    @app.before_request
    def session_and_csrf():
        g.user = None
        # The renderer uses a backend-only Bearer token. Admin cookies neither
        # grant access nor affect this read-only API.
        if request.path.startswith('/api/internal/'):
            return
        g.session_id = digest(request.cookies.get('kdh_session', ''))
        g.session = store.one('SELECT * FROM sessions WHERE id=? AND expires_at>?', (g.session_id, now()))
        if g.session:
            g.user = store.one('SELECT * FROM users WHERE id=? AND active=1', (g.session['user_id'],))
        if request.path.startswith('/api/') and request.method in ('POST', 'PATCH', 'DELETE', 'PUT'):
            if request.headers.get('X-KDH-Request') != '1':
                raise Problem('Yêu cầu không hợp lệ. Hãy tải lại trang.', 403)
            origin = request.headers.get('Origin')
            if origin and origin != app.config['APP_URL']:
                raise Problem('Nguồn gửi yêu cầu không được phép.', 403)
            if g.user and not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), g.session['csrf']):
                raise Problem('Phiên bảo vệ đã thay đổi. Hãy tải lại trang.', 403)

    @app.after_request
    def response_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers.setdefault('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
        response.headers['Cache-Control'] = 'no-store'
        if app.config['COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.errorhandler(Problem)
    def problem(exc):
        return jsonify(error=exc.message, code=exc.code), exc.status

    @app.errorhandler(SourceError)
    def source_problem(exc):
        return jsonify(error=exc.message, code=exc.status), 502

    @app.errorhandler(HTTPException)
    def http_problem(exc):
        limit = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
        labels = {404: 'Không tìm thấy đường dẫn.', 413: f'File quá lớn. Giới hạn upload là {limit} MB.', 405: 'Phương thức không được hỗ trợ.'}
        return jsonify(error=labels.get(exc.code, 'Yêu cầu không hợp lệ.')), exc.code

    @app.errorhandler(Exception)
    def unexpected(exc):
        if app.testing:
            raise exc
        # Do not log request payloads, provider responses, or credentials.
        app.logger.error('Unhandled application error: %s', type(exc).__name__)
        return jsonify(error='Có lỗi khi xử lý yêu cầu. Dữ liệu trước đó được giữ nguyên.'), 500

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.get('/health')
    def health():
        store.one('SELECT 1')
        return jsonify(status='ok')

    @app.get('/api/cron')
    def cron():
        secret = app.config['CRON_SECRET']
        if not secret or not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + secret):
            raise Problem('Không có quyền chạy lịch.', 401)
        if app.config['JOB_MODE'] != 'request':
            raise Problem('Lịch đang được xử lý bởi worker.', 409)
        worker.expire_stale()
        worker.tick_schedules()
        deadline, processed = time.monotonic() + 220, 0
        # Leave enough budget for a full job. Remaining jobs stay durably queued.
        while deadline - time.monotonic() > 90 and worker.run_one(deadline=deadline):
            processed += 1
        return jsonify(processed=processed,
                       queued=store.one("SELECT COUNT(*) AS n FROM jobs WHERE status='queued'")['n'])

    @app.get('/api/auth/me')
    def me():
        return jsonify(user=public_user(g.user) if g.user else None, csrf=g.session['csrf'] if g.user else None,
                       setup_required=bool(local_setup()), timezone=TZ)

    def user_fields(data, password_required=True):
        email = str(data.get('email', '')).strip().lower()
        name = str(data.get('name', '')).strip()
        password = data.get('password', '')
        role = data.get('role', 'viewer')
        permitted = data.get('allowed', [])
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 254:
            raise Problem('Email không hợp lệ.')
        if not 1 <= len(name) <= 100:
            raise Problem('Tên hiển thị cần từ 1–100 ký tự.')
        if not isinstance(password, str) or (password_required or password) and not 12 <= len(password) <= 200:
            raise Problem('Mật khẩu cần từ 12–200 ký tự.')
        if role not in ('admin', 'operator', 'viewer') or not isinstance(permitted, list) or any(x not in TYPES for x in permitted):
            raise Problem('Vai trò hoặc danh sách báo cáo không hợp lệ.')
        return email, name, password, role, permitted

    @app.post('/api/auth/setup')
    def setup():
        if not local_setup():
            raise Problem('Khởi tạo quản trị chỉ khả dụng trên máy chủ khi chưa có tài khoản.', 403)
        email, name, password, _, _ = user_fields(body())
        with store.connect(immediate=True) as db:
            if db.execute('SELECT id FROM users LIMIT 1').fetchone():
                raise Problem('Ứng dụng đã được khởi tạo.', 409)
            actor = uid()
            db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)', (actor, email, name, generate_password_hash(password), 'admin', pack(list(TYPES)), 1, now()))
        store.event(actor, 'setup')
        return jsonify(message='Đã tạo tài khoản quản trị. Bạn có thể đăng nhập.'), 201

    @app.post('/api/auth/login')
    def login():
        data = body()
        email = str(data.get('email', '')).strip().lower()[:254]
        password = str(data.get('password', ''))[:201]
        key = digest((request.remote_addr or '') + ':' + email)
        attempt = store.one('SELECT * FROM attempts WHERE key=?', (key,))
        if attempt and attempt['until_at'] > now() and attempt['count'] >= 8:
            raise Problem('Đăng nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.', 429)
        user = store.one('SELECT * FROM users WHERE email=?', (email,))
        verified = check_password_hash(user['password'] if user else dummy_hash, password)
        if not user or not user['active'] or not verified:
            count = attempt['count'] + 1 if attempt and attempt['until_at'] > now() else 1
            store.execute('INSERT INTO attempts VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,until_at=excluded.until_at',
                          (key, count, (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()))
            raise Problem('Email hoặc mật khẩu không đúng.', 401)
        store.execute('DELETE FROM attempts WHERE key=?', (key,))
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        store.execute('DELETE FROM sessions WHERE expires_at<? OR id=?', (now(), g.session_id))
        store.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                      (digest(token), user['id'], csrf, (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()))
        result = jsonify(user=public_user(user), csrf=csrf)
        result.set_cookie('kdh_session', token, max_age=8 * 3600, httponly=True, secure=app.config['COOKIE_SECURE'], samesite='Lax', path='/')
        store.event(user['id'], 'login')
        return result

    @app.post('/api/auth/logout')
    @require()
    def logout():
        store.execute('DELETE FROM sessions WHERE id=?', (g.session_id,))
        result = jsonify(message='Đã đăng xuất.')
        result.delete_cookie('kdh_session', path='/')
        return result

    @app.get('/api/overview')
    @require()
    def overview():
        worker.expire_stale()
        visible = [k for k in TYPES if allowed(g.user, k)]
        reports = store.all('SELECT id,report_type,name,version,created_at,valid,origin FROM reports ORDER BY created_at DESC')
        reports = [r for r in reports if r['report_type'] in visible]
        jobs = [job_view(r) for r in store.all('SELECT j.*,u.name AS actor FROM jobs j LEFT JOIN users u ON u.id=j.user_id ORDER BY j.created_at DESC LIMIT 100')
                if json.loads(r['params'])['report_type'] in visible and (r['kind'] != 'connection' or g.user['role'] == 'admin')]
        sources, demo_sources, demo_datasets = {}, {}, {}
        permitted_sources = {s for k in visible for s in TYPES[k][1]}
        for row in store.all('SELECT report_type,data FROM datasets ORDER BY created_at DESC LIMIT 100'):
            if row['report_type'] not in visible:
                continue
            snapshot = json.loads(row['data'])
            target = demo_sources if snapshot['params'].get('demo') else sources
            if snapshot['params'].get('demo') and snapshot.get('id') and valid_dataset(snapshot):
                demo_datasets.setdefault(row['report_type'], snapshot['id'])
            for k, value in snapshot['sources'].items():
                if k not in permitted_sources:
                    continue
                if k not in target:
                    target[k] = {f: value.get(f) for f in ('label','status','error','latest_available_date','fetched_at','warnings','demo','totals')}
                if value['status'] in GOOD and not target[k].get('last_success_at'):
                    target[k]['last_success_at'] = value['fetched_at']
                    target[k]['last_success_data_date'] = value['latest_available_date']
        info = google.info()
        return jsonify(reports=reports[:6], report_count=len(reports), jobs=jobs[:6],
                       job_mode=app.config['JOB_MODE'], upload_limit_mb=app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024),
                       demo_enabled=bool(store.setting('demo_pack')), demo_sources=demo_sources, demo_datasets=demo_datasets,
                       running=sum(j['status'] in ('queued','running') for j in jobs),
                       failed=sum(j['status'] in ('failed','partial','interrupted') for j in jobs),
                       sources=sources, google_connected=info['connected'], types=[{'id': k,'label': TYPES[k][0],'can_generate': bool(TYPES[k][1])} for k in visible],
                       last_export=next((j for j in jobs if j['kind']=='export' and j['status']=='succeeded'), None),
                       dashboard_url=app.config['DASHBOARD_URL'], organization=store.setting('organization', {'name':'KinderHealth','author':''}))

    @app.get('/api/google')
    @require('admin')
    def google_info():
        return jsonify(**google.info(), assets={'ga4': app.config['GA4_PROPERTY_ID'], 'gsc':app.config['GSC_PROPERTY'],
                       'keywords': app.config['KEYWORD_SPREADSHEET_ID'] + ' / ' + app.config['KEYWORD_SHEET']})

    @app.post('/api/google/connect')
    @require('admin')
    def google_connect():
        return jsonify(url=google.authorization_url(g.session_id))

    @app.get('/api/google/callback')
    @require('admin')
    def google_callback():
        if request.args.get('error'):
            return redirect('/#connections?oauth=denied')
        try:
            google.exchange(request.args.get('state',''), request.args.get('code',''), g.session_id)
            start, end = period_dates('last7')
            job_id, _ = enqueue(store, g.user['id'], 'connection', filters({'start':start, 'end':end, 'report_type':'seo'}))
            store.event(g.user['id'], 'google_connect')
        except (Problem, SourceError):
            return redirect('/#connections?oauth=failed')
        return redirect('/#connections/google?oauth=success&job=' + job_id)

    @app.post('/api/google/check')
    @require('admin')
    def google_check():
        start, end = period_dates('last7')
        job_id, created = enqueue(store, g.user['id'], 'connection', filters({'start':start, 'end':end, 'report_type':'seo'}))
        return jsonify(job_id=job_id, created=created), 202

    @app.delete('/api/google')
    @require('admin')
    def google_disconnect():
        if store.one("SELECT id FROM jobs WHERE status IN ('queued','running') AND kind IN ('analysis','connection')"):
            raise Problem('Đợi tác vụ đang chạy hoàn tất trước khi ngắt kết nối.', 409)
        revoked = google.disconnect()
        store.event(g.user['id'], 'google_disconnect', {'revoked_at_provider':revoked})
        return jsonify(message='Đã ngắt kết nối.' if revoked else 'Đã xóa kết nối tại ứng dụng. Google chưa xác nhận thu hồi; bạn có thể thu hồi trong tài khoản Google.')

    @app.post('/api/analyses')
    @require()
    def analysis():
        p = filters(body())
        if p.get('demo') and not store.setting('demo_pack'):
            raise Problem('Bộ dữ liệu demo chưa được cài đặt.', 409)
        check_report(p['report_type'])
        job_id, created = enqueue(store, g.user['id'], 'analysis', p)
        return jsonify(job_id=job_id, created=created), 202

    @app.get('/api/datasets/<dataset_id>')
    @require()
    def dataset(dataset_id):
        data = get_dataset(dataset_id)
        return jsonify(**data, exportable=valid_dataset(data))

    @app.post('/api/datasets/<dataset_id>/export')
    @require()
    def export(dataset_id):
        data = get_dataset(dataset_id)
        if not valid_dataset(data):
            raise Problem('Chưa thể xuất: cần các nguồn bắt buộc và kỳ so sánh hợp lệ.', 409)
        job_id, created = enqueue(store, g.user['id'], 'export', {**data['params'], 'dataset_id': dataset_id})
        return jsonify(job_id=job_id, created=created), 202

    @app.post('/api/datasets/<dataset_id>/save')
    @require('admin','operator')
    def save(dataset_id):
        report_id = save_report(store, g.user['id'], get_dataset(dataset_id))
        store.event(g.user['id'], 'save_report', {'report_id':report_id})
        return jsonify(report_id=report_id), 201

    @app.get('/api/jobs')
    @require()
    def jobs():
        worker.expire_stale()
        rows = store.all('SELECT j.*,u.name AS actor FROM jobs j LEFT JOIN users u ON u.id=j.user_id ORDER BY j.created_at DESC LIMIT 300')
        return jsonify([job_view(r) for r in rows if allowed(g.user, json.loads(r['params'])['report_type']) and (r['kind']!='connection' or g.user['role']=='admin')])

    @app.get('/api/jobs/<job_id>')
    @require()
    def job(job_id):
        worker.expire_stale()
        return jsonify(get_job(job_id))

    @app.post('/api/jobs/<job_id>/process')
    @require()
    def process_job(job_id):
        current = get_job(job_id)
        # A viewer cannot trigger another user's scheduled publication.
        if current['user_id'] != g.user['id'] and g.user['role'] != 'admin':
            raise Problem('Chỉ người tạo hoặc Admin được khởi chạy tác vụ này.', 403)
        if app.config['JOB_MODE'] == 'request':
            worker.run_one(job_id)
        return jsonify(get_job(job_id))

    @app.post('/api/demo/seed')
    @require('admin')
    def install_demo():
        from .demo import seed_demo
        return jsonify(seed_demo(store, g.user['id']))

    @app.post('/api/jobs/<job_id>/retry')
    @require()
    def retry(job_id):
        old = get_job(job_id)
        if old['status'] not in ('failed','partial','interrupted'):
            raise Problem('Chỉ có thể thử lại tác vụ lỗi hoặc gián đoạn.', 409)
        p = old['params']
        # A retry never silently republishes a scheduled report.
        p.pop('auto_publish', None)
        p.pop('schedule_id', None)
        p.pop('simulated_history', None)
        if g.user['role']=='viewer':
            p.pop('save_report', None)
        job_id, created = enqueue(store, g.user['id'], old['kind'], p, old['id'])
        return jsonify(job_id=job_id, created=created), 202

    @app.get('/api/jobs/<job_id>/download')
    @require()
    def download_export(job_id):
        job = get_job(job_id)
        if job['kind'] != 'export' or job['status'] != 'succeeded':
            raise Problem('File Excel chưa sẵn sàng.', 409)
        content = store.artifact(job['id'])
        if content is None:
            raise Problem('File Excel cũ không còn trên máy chủ. Hãy xuất lại từ báo cáo đã lưu.', 409)
        p = job['params']
        prefix = 'DEMO_' if p.get('demo') else ''
        return send_file(io.BytesIO(content), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=f"{prefix}KinderHealth_Report_{p['start']}_{p['end']}.xlsx")

    @app.get('/api/reports')
    @require()
    def reports():
        rows = store.all('SELECT r.id,r.report_type,r.name,r.version,r.dataset_id,r.created_at,r.start_date,r.end_date,r.valid,r.origin,p.published_at FROM reports r LEFT JOIN publications p ON r.id=p.report_id ORDER BY r.created_at DESC')
        return jsonify([r for r in rows if allowed(g.user,r['report_type'])])

    @app.post('/api/reports/import')
    @require('admin')
    def import_reports():
        return jsonify(report_ids=import_legacy(store, app.config, g.user['id']))

    @app.get('/api/reports/<report_id>/html')
    @require()
    def report_html(report_id):
        row = get_report(report_id)
        response = send_file(io.BytesIO(row['html'].encode('utf-8')), mimetype='text/html', as_attachment=request.args.get('download')=='1', download_name=f"{row['report_type']}_v{row['version']}.html")
        response.headers['Content-Security-Policy'] = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://cdn.tailwindcss.com; style-src 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src data: https:; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'self'"
        return response

    @app.post('/api/reports/<report_id>/publish')
    @require('admin','operator')
    def publish_report(report_id):
        get_report(report_id)
        publish(store, g.user['id'], report_id)
        return jsonify(message='Đã xuất bản nội bộ. Đây là phiên bản hiện hành cho người có quyền xem.')

    @app.get('/api/uploads')
    @require()
    def uploads():
        check_report('gmb')
        rows = store.all('SELECT id,name,start_date,end_date,created_at,data FROM uploads ORDER BY created_at DESC')
        for row in rows:
            data = json.loads(row.pop('data'))
            row['demo'] = bool(data.get('demo'))
            row['locations'] = len(data['entries'])
            row['preview'] = data['entries']
        return jsonify(rows)

    @app.post('/api/uploads')
    @require('admin','operator')
    def upload():
        check_report('gmb')
        file = request.files.get('file')
        if not file or not (file.filename or '').lower().endswith('.csv'):
            raise Problem('Chọn một file CSV.')
        upload_id = save_upload(store, g.user['id'], file.filename, file.read(), request.form.get('start'), request.form.get('end'))
        return jsonify(upload_id=upload_id), 201

    @app.get('/api/users')
    @require('admin')
    def users():
        return jsonify([public_user(u) for u in store.all('SELECT * FROM users ORDER BY created_at')])

    @app.post('/api/users')
    @require('admin')
    def create_user():
        email,name,password,role,permitted = user_fields(body())
        actor = uid()
        try:
            store.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,?)', (actor,email,name,generate_password_hash(password),role,pack(permitted),1,now()))
        except sqlite3.IntegrityError:
            raise Problem('Email đã được sử dụng.',409) from None
        store.event(g.user['id'],'create_user',{'user_id':actor,'role':role})
        return jsonify(id=actor),201

    @app.patch('/api/users/<user_id>')
    @require('admin')
    def update_user(user_id):
        old = store.one('SELECT * FROM users WHERE id=?',(user_id,))
        if not old:
            raise Problem('Không tìm thấy người dùng.',404)
        data = {**public_user(old), **body()}
        email,name,password,role,permitted = user_fields(data,False)
        active = data.get('active', True)
        if active not in (True,False,0,1):
            raise Problem('Trạng thái tài khoản không hợp lệ.')
        if user_id==g.user['id'] and (not active or role!='admin'):
            raise Problem('Không thể tự vô hiệu hóa hoặc hạ quyền tài khoản quản trị đang dùng.')
        try:
            with store.connect(immediate=True) as db:
                db.execute('UPDATE users SET email=?,name=?,password=?,role=?,allowed=?,active=? WHERE id=?',
                           (email,name,generate_password_hash(password) if password else old['password'],role,pack(permitted),int(active),user_id))
                db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
        except sqlite3.IntegrityError:
            raise Problem('Email đã được sử dụng.',409) from None
        store.event(g.user['id'],'update_user',{'user_id':user_id,'role':role,'active':bool(active)})
        return jsonify(message='Đã cập nhật người dùng và thu hồi các phiên đăng nhập cũ.')

    @app.get('/api/settings')
    @require('admin')
    def settings():
        return jsonify(organization=store.setting('organization',{'name':'KinderHealth','author':''}),
                       timezone=TZ, publish_mode='internal', versions='Giữ toàn bộ phiên bản',
                       oauth_configured=google.configured(), dashboard_url=app.config['DASHBOARD_URL'],
                       demo_enabled=bool(store.setting('demo_pack')), job_mode=app.config['JOB_MODE'])

    @app.patch('/api/settings')
    @require('admin')
    def update_settings():
        data = body()
        name, author = str(data.get('name','')).strip(), str(data.get('author','')).strip()
        if not 1 <= len(name) <= 100 or len(author)>100:
            raise Problem('Tên đơn vị/người lập không hợp lệ (tối đa 100 ký tự).')
        store.set_setting('organization',{'name':name,'author':author})
        store.event(g.user['id'],'update_settings')
        return jsonify(message='Đã lưu cài đặt.')

    @app.get('/api/events')
    @require('admin')
    def events():
        rows = store.all('SELECT e.*,u.name AS actor FROM events e LEFT JOIN users u ON u.id=e.user_id ORDER BY e.at DESC LIMIT 200')
        for r in rows:
            r['detail']=json.loads(r['detail'])
        return jsonify(rows)

    @app.get('/api/schedules')
    @require('admin')
    def schedules():
        rows=store.all('SELECT * FROM schedules ORDER BY next_run')
        for r in rows:
            r['params']=json.loads(r['params'])
        return jsonify(rows)

    @app.post('/api/schedules')
    @require('admin')
    def create_schedule():
        data=body()
        start,end=period_dates('last7')
        p=filters({**data,'start':start,'end':end})
        if p['report_type']=='gmb':
            raise Problem('Lịch tự động chỉ dành cho nguồn Google; GMB cần chọn CSV theo kỳ.')
        frequency=data.get('frequency','daily')
        run_time=data.get('run_time','07:00')
        period=data.get('period','last28')
        if frequency not in ('daily','weekly','monthly') or period not in ('last7','last28','previous_month'):
            raise Problem('Chu kỳ hoặc kỳ dữ liệu không hợp lệ.')
        if not isinstance(run_time,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',run_time):
            raise Problem('Giờ chạy không hợp lệ.')
        try:
            weekday=int(data.get('weekday',0)); monthday=int(data.get('monthday',1))
        except (ValueError,TypeError):
            raise Problem('Ngày chạy không hợp lệ.') from None
        if not 0<=weekday<=6 or not 1<=monthday<=28:
            raise Problem('Ngày tuần từ 0–6; ngày tháng từ 1–28.')
        name=str(data.get('name','')).strip()
        if not 1<=len(name)<=100:
            raise Problem('Nhập tên lịch (tối đa 100 ký tự).')
        schedule={'frequency':frequency,'run_time':run_time,'weekday':weekday,'monthday':monthday}
        schedule_id=uid()
        store.execute('INSERT INTO schedules VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (schedule_id,name,g.user['id'],pack(p),frequency,run_time,weekday,monthday,period,int(bool(data.get('publish',False))),1,next_run(schedule),None,None))
        store.event(g.user['id'],'create_schedule',{'schedule_id':schedule_id})
        return jsonify(id=schedule_id),201

    @app.patch('/api/schedules/<schedule_id>')
    @require('admin')
    def toggle_schedule(schedule_id):
        row=store.one('SELECT * FROM schedules WHERE id=?',(schedule_id,))
        if not row:
            raise Problem('Không tìm thấy lịch.',404)
        enabled=body().get('enabled')
        if not isinstance(enabled,bool):
            raise Problem('Trạng thái không hợp lệ.')
        store.execute('UPDATE schedules SET enabled=?,next_run=? WHERE id=?',(int(enabled),next_run(row),schedule_id))
        store.event(g.user['id'],'toggle_schedule',{'schedule_id':schedule_id,'enabled':enabled})
        return jsonify(message='Đã cập nhật lịch.')

    register_report_bundle_routes(app, store, require, body)
    return app
