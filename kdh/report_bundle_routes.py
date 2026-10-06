"""Thin Flask endpoints. Renderer authentication is separate from admin sessions."""
import re
import secrets

from flask import Response, g, jsonify, request

from .core import Problem, pack
from . import report_bundles as service


def _revision_arg():
    if set(request.args) - {'revision'} or len(request.args.getlist('revision')) > 1:
        raise Problem('Chỉ hỗ trợ một tham số revision.')
    value = request.args.get('revision')
    if value is None:
        return None
    if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
        raise Problem('Revision phải là số nguyên dương.')
    return int(value)


def register_report_bundle_routes(app, store, require, body):
    @app.post('/api/report-bundles')
    @require('admin')
    def create_report_bundle():
        return jsonify(service.create_bundle(store, g.user['id'], body(), g.session_id)), 201

    @app.get('/api/report-bundles')
    @require('admin')
    def list_report_bundles():
        return jsonify(store.all('''SELECT bundle_key AS report_id,revision,parent_id,client_id,name,
            status,start_date,end_date,quality_status,created_at,published_at
            FROM report_bundles ORDER BY created_at DESC,bundle_key,revision DESC LIMIT 200'''))

    @app.get('/api/report-bundles/<report_id>')
    @require('admin')
    def read_report_bundle(report_id):
        return Response(pack(service.get_bundle(store, report_id, _revision_arg())), mimetype='application/json')

    @app.post('/api/report-bundles/<report_id>/revisions')
    @require('admin')
    def create_report_revision(report_id):
        return jsonify(service.create_revision(store, g.user['id'], report_id, body(), g.session_id)), 201

    @app.patch('/api/report-bundles/<report_id>/revisions/<int:revision>')
    @require('admin')
    def update_report_draft(report_id, revision):
        return jsonify(service.update_draft(store, g.user['id'], report_id, revision, body(), g.session_id))

    @app.post('/api/report-bundles/<report_id>/revisions/<int:revision>/publish')
    @require('admin')
    def publish_report_revision(report_id, revision):
        data = body()
        if set(data) != {'status'} or data['status'] not in ('provisional', 'final'):
            raise Problem('Chỉ nhận status provisional hoặc final.')
        publish = service.publish_final if data['status'] == 'final' else service.publish_provisional
        return jsonify(publish(store, g.user['id'], report_id, revision, g.session_id))

    @app.get('/api/internal/v1/report-bundles/<report_id>')
    def internal_report_bundle(report_id):
        configured = app.config.get('REPORT_SERVICE_TOKEN', '')
        supplied = request.headers.get('Authorization', '')
        if not configured or not secrets.compare_digest(supplied.encode('utf-8'), ('Bearer ' + configured).encode('utf-8')):
            response = jsonify(error='Không có quyền đọc Internal Report API.', code='unauthorized')
            response.status_code = 401
            response.headers['WWW-Authenticate'] = 'Bearer'
            return response
        payload = service.get_bundle(store, report_id, _revision_arg(), published_only=True)
        return Response(pack(payload), mimetype='application/json')
