"""Report-specific Viewer ACL. Service identity never replaces end-user identity."""
import json
import secrets

from flask import g, jsonify, request

from .core import Problem, allowed, digest, now, pack, uid
from .platform_data import DEFAULT_CLIENT_ID
from .report_bundles import _admin, _guard_marketing_snapshot, _payload, get_latest_revision, get_revision
from .report_bundle_routes import _revision_arg


def service_identity(app):
    expected = app.config.get('REPORT_SERVICE_TOKEN', '')
    actual = request.headers.get('Authorization', '')
    if not expected or not secrets.compare_digest(actual.encode(), ('Bearer ' + expected).encode()):
        raise Problem('Không có quyền đọc Internal API.', 401, 'unauthorized')


def viewer_identity(db):
    opaque = request.headers.get('X-KDH-Viewer-Session', '')
    row = db.execute('''SELECT u.*,s.id AS session_id FROM users u JOIN sessions s ON s.user_id=u.id
        WHERE s.id=? AND s.expires_at>? AND u.active=1''', (digest(opaque), now())).fetchone()
    if not row:
        raise Problem('Phiên người xem hết hạn hoặc đã bị thu hồi.', 401, 'viewer_unauthorized')
    return dict(row)


def register_viewer_routes(app, store, require, body):
    @app.get('/api/report-bundles/<report_id>/access')
    @require('admin')
    def read_report_access(report_id):
        get_latest_revision(store, report_id)
        return jsonify(store.all('''SELECT a.*,u.email,u.name FROM report_viewer_grants a
            JOIN users u ON u.id=a.user_id WHERE a.report_id=? ORDER BY u.email''', (report_id,)))

    @app.post('/api/report-bundles/<report_id>/access')
    @require('admin')
    def grant_report_access(report_id):
        data = body()
        if (set(data) != {'user_id', 'min_revision', 'max_revision', 'active'}
                or not isinstance(data['user_id'], str) or type(data['min_revision']) is not int
                or data['min_revision'] < 1 or type(data['active']) is not bool
                or (data['max_revision'] is not None and
                    (type(data['max_revision']) is not int or data['max_revision'] < data['min_revision']))):
            raise Problem('Phạm vi quyền xem không hợp lệ.')
        with store.connect(immediate=True) as db:
            _admin(db, g.user['id'], g.session_id)
            report = get_latest_revision(store, report_id, db=db)
            user = db.execute('SELECT id FROM users WHERE id=? AND active=1', (data['user_id'],)).fetchone()
            if not user:
                raise Problem('Tài khoản không tồn tại hoặc đã bị khóa.', 404)
            previous = db.execute('SELECT * FROM report_viewer_grants WHERE report_id=? AND user_id=?',
                                  (report_id, data['user_id'])).fetchone()
            db.execute('''INSERT INTO report_viewer_grants
                (report_id,client_id,user_id,min_revision,max_revision,active,granted_by,updated_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(report_id,user_id) DO UPDATE SET
                min_revision=excluded.min_revision,max_revision=excluded.max_revision,
                active=excluded.active,granted_by=excluded.granted_by,updated_at=excluded.updated_at''',
                (report_id, report['client_id'], data['user_id'], data['min_revision'], data['max_revision'],
                 int(data['active']), g.user['id'], now()))
            db.execute('INSERT INTO events (id,user_id,action,at,detail) VALUES (?,?,?,?,?)',
                (uid(), g.user['id'], 'update_report_viewer_access', now(),
                 pack({'report_id': report_id, 'before': dict(previous) if previous else None, 'after': data})))
        return jsonify(saved=True)

    @app.get('/api/internal/v1/viewer-session')
    def internal_viewer_session():
        service_identity(app)
        with store.connect() as db:
            user = viewer_identity(db)
        return jsonify(user_id=user['id'], name=user['name'], role=user['role'])

    @app.delete('/api/internal/v1/viewer-session')
    def internal_viewer_logout():
        service_identity(app)
        with store.connect(immediate=True) as db:
            user = viewer_identity(db)
            db.execute('DELETE FROM sessions WHERE id=?', (user['session_id'],))
        return jsonify(logged_out=True)

    @app.get('/api/internal/v1/viewer/report-bundles/<report_id>')
    def internal_viewer_bundle(report_id):
        service_identity(app)
        revision = _revision_arg()
        with store.connect(immediate=True) as db:
            user = viewer_identity(db)
            row = (get_latest_revision(store, report_id, True, db=db) if revision is None
                   else get_revision(store, report_id, revision, True, db=db))
            admin_access = user['role'] == 'admin' and row['client_id'] == DEFAULT_CLIENT_ID
            grant = db.execute('''SELECT * FROM report_viewer_grants
                WHERE report_id=? AND client_id=? AND user_id=? AND active=1
                AND min_revision<=? AND (max_revision IS NULL OR max_revision>=?)''',
                (report_id, row['client_id'], user['id'], row['revision'], row['revision'])).fetchone()
            if not admin_access and not grant:
                raise Problem('Báo cáo không nằm trong phạm vi được cấp.', 404, 'report_not_found')
            payload = _payload(row)
            if payload.get('client', {}).get('id') != row['client_id']:
                raise Problem('Phạm vi khách hàng của snapshot không hợp lệ.', 409)
            if not admin_access and any(not allowed(user, item['report_type']) for item in payload['sections'].values()):
                raise Problem('Báo cáo không nằm trong quyền xem được cấp.', 404, 'report_not_found')
            _guard_marketing_snapshot(payload, store)
        return jsonify(payload)

    @app.get('/api/internal/v1/viewer/report-bundles')
    def internal_viewer_reports():
        service_identity(app)
        with store.connect() as db:
            user = viewer_identity(db)
            rows = db.execute("SELECT * FROM report_bundles WHERE status IN ('provisional','final') ORDER BY bundle_key,revision DESC").fetchall()
            reports, selected = [], set()
            for row in rows:
                if row['bundle_key'] in selected:
                    continue
                grant = db.execute('''SELECT 1 FROM report_viewer_grants WHERE report_id=? AND client_id=?
                    AND user_id=? AND active=1 AND min_revision<=? AND (max_revision IS NULL OR max_revision>=?)''',
                    (row['bundle_key'], row['client_id'], user['id'], row['revision'], row['revision'])).fetchone()
                admin_access = user['role'] == 'admin' and row['client_id'] == DEFAULT_CLIENT_ID
                if not grant and not admin_access:
                    continue
                payload = _payload(row)
                if not admin_access and any(not allowed(user, section['report_type']) for section in payload['sections'].values()):
                    continue
                selected.add(row['bundle_key'])
                reports.append({key: row[key] for key in ('revision', 'name', 'status', 'start_date', 'end_date')}
                               | {'report_id': row['bundle_key']})
        return jsonify(reports=reports)

    @app.get('/api/internal/v1/marketing-preview/<candidate_id>')
    def internal_marketing_preview(candidate_id):
        service_identity(app)
        with store.connect(immediate=True) as db:
            user = viewer_identity(db)
            _admin(db, user['id'], user['session_id'])
            from .marketing_source_check import candidate_state
            _, candidate, _, _, _, issues = candidate_state(store, db, candidate_id)
        return jsonify(kind='marketing_internal_preview', publishable=False, candidate=candidate, issues=issues)
