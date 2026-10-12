"""Admin workflow entry point and resumable snapshot index; no provider calls."""
import json
from urllib.parse import urlsplit

from flask import g, jsonify, redirect, render_template

from .metric_catalog import SOURCES
from .platform_data import DEFAULT_CLIENT_ID


def register_marketing_console(app, store, require):
    @app.get('/marketing')
    def marketing_console():
        if not g.user:
            return redirect('/')
        if g.user['role'] != 'admin':
            return 'Chỉ quản trị viên được duyệt báo cáo.', 403
        return render_template('marketing.html')

    @app.get('/api/marketing/workflow')
    @require('admin')
    def marketing_workflow():
        snapshots = []
        # Read metadata only; contents remain behind the existing Dataset API.
        for row in store.all('SELECT id,created_at,report_type,data FROM datasets ORDER BY created_at DESC LIMIT 500'):
            data = json.loads(row['data'])
            kind = data.get('dataset_kind', '')
            if data.get('client_id') != DEFAULT_CLIENT_ID or kind not in (
                    'marketing_internal_preview_v1', 'marketing_release_candidate_v1', 'marketing_release_snapshot_v1'):
                continue
            snapshots.append({'id': row['id'], 'kind': kind, 'created_at': row['created_at'],
                              'source': data['params']['source'], 'start': data['params']['start'],
                              'end': data['params']['end']})
        new_url = app.config.get('REPORT_NEW_BASE_URL', 'http://localhost:8080').rstrip('/')
        try:
            parsed = urlsplit(new_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                new_url = ''
        except ValueError:
            new_url = ''
        return jsonify(client_id=DEFAULT_CLIENT_ID, client_name='KinderHealth', new_url=new_url,
                       sources=[{'id': key, 'label': item['label'], 'integration': item['integration']}
                                for key, item in SOURCES.items()], snapshots=snapshots,
                       assets=store.all('''SELECT id,name,asset_type,provider FROM source_assets
                           WHERE client_id=? AND enabled=1 ORDER BY name''', (DEFAULT_CLIENT_ID,)))
