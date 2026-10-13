"""Backend-authenticated, PKCE-bound handoff. No Admin cookie leaves Admin."""
import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

from flask import g, jsonify, redirect, render_template, request

from .core import Problem, digest, now
from .platform_data import DEFAULT_CLIENT_ID
from .viewer_access import service_identity, viewer_identity, authorized_bundle


def public_origin(value):
    value = str(value).rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment
            or (parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise Problem('URL public chưa được cấu hình hợp lệ.', 503)
    return value


def binding(value):
    return isinstance(value, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{43,128}', value))


def expiry(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def authorize_scope(store, db, user, row):
    if row['client_id'] != DEFAULT_CLIENT_ID:
        raise Problem('Khách hàng không hợp lệ.', 403)
    if row['mode'] == 'published':
        authorized_bundle(store, db, user, row['target_id'], row['revision'])
    else:
        from .report_bundles import _admin
        from .marketing_source_check import candidate_state
        _admin(db, user['id'], user['session_id'])
        _, candidate, _, _, _, _ = candidate_state(store, db, row['target_id'])
        if candidate.get('client_id') != row['client_id']:
            raise Problem('Bản xem trước không thuộc khách hàng.', 403)


def register_handoff_routes(app, store, body):
    def configuration():
        audience = public_origin(app.config['REPORT_NEW_BASE_URL'])
        return public_origin(app.config['APP_URL']), audience, audience + '/auth/handoff/callback'

    @app.post('/api/internal/v1/handoffs')
    def create_handoff():
        service_identity(app)
        data = body()
        admin, audience, callback = configuration()
        expected = {'state', 'challenge', 'client_id', 'target_id', 'revision', 'mode', 'audience', 'callback'}
        if (set(data) != expected or not binding(data['state']) or not binding(data['challenge'])
                or data['audience'] != audience or data['callback'] != callback
                or data['client_id'] != DEFAULT_CLIENT_ID or data['mode'] not in ('published', 'preview')
                or type(data['revision']) is not int or not isinstance(data['target_id'], str)
                or not re.fullmatch(r'rpt_[a-f0-9]{32}' if data['mode'] == 'published' else r'[a-f0-9]{32}', data['target_id'])
                or (data['mode'] == 'published' and not 1 <= data['revision'] <= 999999999)
                or (data['mode'] == 'preview' and data['revision'] != 0)):
            raise Problem('Giao dịch chuyển phiên không hợp lệ.')
        transaction = secrets.token_urlsafe(32)
        with store.connect(immediate=True) as db:
            db.execute('DELETE FROM viewer_handoffs WHERE expires_at<?', (now(),))
            db.execute('DELETE FROM delegated_viewer_sessions WHERE expires_at<?', (now(),))
            db.execute('''INSERT INTO viewer_handoffs
                (id,state,challenge,client_id,target_id,revision,mode,audience,callback,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (transaction, data['state'], data['challenge'], data['client_id'],
                data['target_id'], data['revision'], data['mode'], audience, callback, expiry(600)))
        return jsonify(transaction=transaction, authorize_url=admin + '/viewer/authorize?transaction=' + transaction)

    @app.get('/viewer/authorize')
    def authorize_handoff():
        admin, audience, callback = configuration()
        if set(request.args) != {'transaction'} or len(request.args.getlist('transaction')) != 1:
            raise Problem('Giao dịch chuyển phiên không hợp lệ.')
        transaction = request.args['transaction']
        if not binding(transaction):
            raise Problem('Giao dịch chuyển phiên không hợp lệ.')
        # Canonical public host BEFORE consulting a host-only session cookie.
        if request.host_url.rstrip('/') != admin:
            return redirect(admin + '/viewer/authorize?transaction=' + transaction, 303)
        with store.connect(immediate=True) as db:
            row = db.execute('SELECT * FROM viewer_handoffs WHERE id=? AND expires_at>?', (transaction, now())).fetchone()
            if not row or row['redeemed'] or row['code_hash'] or row['audience'] != audience or row['callback'] != callback:
                raise Problem('Giao dịch đã hết hạn hoặc đã dùng. Mở lại báo cáo từ Admin.', 400)
            if not g.user:
                return render_template('handoff_login.html', transaction=transaction)
            user = {**g.user, 'session_id': g.session_id}
            authorize_scope(store, db, user, row)
            code = secrets.token_urlsafe(48)
            db.execute('''UPDATE viewer_handoffs SET user_id=?,source_session_id=?,code_hash=?,code_expires_at=?
                WHERE id=?''', (user['id'], g.session_id, digest(code), expiry(60), transaction))
        # Fragment is never sent in HTTP requests/access logs or Referer. The
        # local callback script removes it before any other navigation/resource.
        return redirect(callback + '#' + urlencode({'transaction': transaction, 'state': row['state'], 'code': code}), 303)

    @app.post('/api/internal/v1/handoffs/redeem')
    def redeem_handoff():
        service_identity(app)
        data = body()
        _, audience, callback = configuration()
        if set(data) != {'transaction', 'state', 'code', 'verifier', 'audience', 'callback'} or any(
                not binding(data.get(key)) for key in ('transaction', 'state', 'code', 'verifier')):
            raise Problem('Mã chuyển phiên không hợp lệ.')
        challenge = base64.urlsafe_b64encode(hashlib.sha256(data['verifier'].encode()).digest()).decode().rstrip('=')
        with store.connect(immediate=True) as db:
            row = db.execute('''SELECT * FROM viewer_handoffs WHERE id=? AND expires_at>?
                AND code_expires_at>? AND redeemed=0''', (data['transaction'], now(), now())).fetchone()
            if (not row or data['audience'] != audience or data['callback'] != callback
                    or row['audience'] != audience or row['callback'] != callback
                    or not secrets.compare_digest(row['state'], data['state'])
                    or not secrets.compare_digest(row['challenge'], challenge)
                    or not secrets.compare_digest(row['code_hash'] or '', digest(data['code']))):
                raise Problem('Mã đã hết hạn, đã dùng hoặc khác trình duyệt.', 400)
            source = db.execute('''SELECT u.*,s.id AS session_id,s.expires_at AS session_expires
                FROM users u JOIN sessions s ON s.user_id=u.id
                WHERE s.id=? AND u.id=? AND s.expires_at>? AND u.active=1''',
                (row['source_session_id'], row['user_id'], now())).fetchone()
            if not source:
                raise Problem('Phiên Admin đã hết hạn hoặc bị thu hồi.', 401)
            authorize_scope(store, db, dict(source), row)
            if request.headers.get('X-KDH-Viewer-Session'):
                try:
                    existing = viewer_identity(db)
                except Problem as exc:
                    if exc.status != 401:
                        raise
                else:
                    if existing['id'] != source['id']:
                        raise Problem('New đang đăng nhập bằng tài khoản khác. Đăng xuất New rồi mở lại từ Admin.', 409, 'identity_conflict')
                    if existing.get('delegated_id'):
                        db.execute('DELETE FROM delegated_viewer_sessions WHERE id=?', (existing['delegated_id'],))
            changed = db.execute('UPDATE viewer_handoffs SET redeemed=1 WHERE id=? AND redeemed=0', (row['id'],))
            if changed.rowcount != 1:
                raise Problem('Mã đã được sử dụng.', 400)
            session = secrets.token_urlsafe(48)
            db.execute('''INSERT INTO delegated_viewer_sessions
                (id,user_id,source_session_id,client_id,target_id,revision,mode,audience,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?)''', (digest(session), source['id'], source['session_id'], row['client_id'],
                row['target_id'], row['revision'], row['mode'], audience, source['session_expires']))
        return jsonify(session=session, target_id=row['target_id'], revision=row['revision'], mode=row['mode'])
