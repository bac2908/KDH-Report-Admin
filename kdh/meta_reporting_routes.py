"""Admin-only API for discovery, selection, and queued Meta reporting sync."""
import re
import os

from flask import g, jsonify, request
from .metric_reader import read_metric_series
from .core import Problem
from .jobs import enqueue
from .meta_reporting import MetaReportingReader, SOURCES, validate_range
from .platform_data import PlatformData, DEFAULT_CLIENT_ID
from .marketing_preview import build_marketing_preview

def register_meta_reporting_routes(app, store, require, body, meta):
    platform = PlatformData(store)

    def connection():
        if meta.client_id == DEFAULT_CLIENT_ID and os.getenv('META_REPORTING_ALLOW_PRIMARY_CLIENT') != '1':
            raise Problem('Để tránh trộn tài sản thử nghiệm vào KinderHealth, hãy dùng META_CLIENT_ID=client_meta_sandbox.',
                          403, 'meta_test_scope_required')
        if not meta.info()['connected']:
            raise Problem('Kết nối Meta chưa sẵn sàng. Cần hoàn tất OAuth.', 409, 'meta_reconnect_required')
        token = meta.read() or {}
        row = store.one('''SELECT * FROM connections WHERE client_id=? AND provider='meta'
            AND external_account_id=? AND status='connected' ORDER BY created_at DESC LIMIT 1''',
            (meta.client_id, token.get('account_id')))
        if not row:
            raise Problem('Không tìm thấy kết nối Meta khớp với tài khoản.', 409, 'meta_connection_missing')
        return row

    @app.get('/api/meta/reporting/assets')
    @require('admin')
    def reporting_assets():
        conn = connection()
        discovered = MetaReportingReader(meta).discover()
        selected = store.all('''SELECT id,asset_type,external_id,name,enabled,currency,timezone
            FROM source_assets WHERE client_id=? AND provider='meta' AND connection_id=?
            ORDER BY name''', (meta.client_id, conn['id']))
        return jsonify(client_id=meta.client_id, discovered=discovered, selected=selected)

    @app.post('/api/meta/reporting/assets')
    @require('admin')
    def reporting_select_asset():
        data = body()
        if set(data) != {'source', 'external_id', 'enabled'} or data.get('source') not in SOURCES or type(data.get('enabled')) is not bool:
            raise Problem('Yêu cầu chọn tài sản Meta không hợp lệ.')
        source, external_id = data['source'], data['external_id']
        if not isinstance(external_id, str) or not re.fullmatch(r'act_\d+' if source == 'facebook_ads' else r'\d+', external_id):
            raise Problem('ID tài sản Meta không hợp lệ.')
        conn = connection()
        assets = MetaReportingReader(meta).discover()[source]
        match = next((item for item in assets if item['id'] == external_id), None)
        if not match:
            raise Problem('Tài sản không nằm trong phạm vi Meta đã cấp quyền.', 403, 'meta_asset_not_permitted')
        asset_id = platform.upsert_asset(client_id=meta.client_id, provider='meta',
            asset_type=SOURCES[source][0], external_id=external_id,
            name=str(match.get('name') or external_id)[:160], connection_id=conn['id'],
            currency=match.get('currency') if source == 'facebook_ads' else None,
            timezone=match.get('timezone_name') if source == 'facebook_ads' else 'UTC',
            metadata={'source_key': source, 'data_origin': 'meta_api_unverified'},
            enabled=data['enabled'])
        store.event(g.user['id'], 'meta_asset_selection', {'asset_id': asset_id, 'source': source,
                                                            'enabled': data['enabled']})
        return jsonify(asset_id=asset_id, enabled=data['enabled'])

    @app.post('/api/meta/reporting/sync')
    @require('admin')
    def reporting_sync():
        data = body()
        if set(data) != {'asset_id', 'start', 'end'} or not isinstance(data.get('asset_id'), str):
            raise Problem('Yêu cầu đồng bộ Meta không hợp lệ.')
        first, last = validate_range(data.get('start'), data.get('end'))
        conn = connection()
        asset = store.one('''SELECT * FROM source_assets WHERE id=? AND client_id=? AND provider='meta'
            AND connection_id=? AND enabled=1''', (data['asset_id'], meta.client_id, conn['id']))
        if not asset:
            raise Problem('Tài sản Meta chưa được chọn hoặc không còn quyền.', 403)
        source = next((key for key, (asset_type, _) in SOURCES.items() if asset_type == asset['asset_type']), None)
        if source is None:
            raise Problem('Loại tài sản Meta chưa được hỗ trợ.')
        job_id, created = enqueue(store, g.user['id'], 'meta_sync',
            {'source': source, 'asset_id': asset['id'], 'report_type':
                'facebook-ads' if source == 'facebook_ads' else 'facebook-content',
                'start': first.isoformat(), 'end': last.isoformat(), 'demo': False})
        store.event(g.user['id'], 'meta_sync_queued', {'job_id': job_id, 'asset_id': asset['id']})
        return jsonify(job_id=job_id, created=created), 202

    @app.get('/api/meta/reporting/syncs/<asset_id>')
    @require('admin')
    def reporting_sync_history(asset_id):
        conn = connection()
        asset = store.one('''SELECT id FROM source_assets WHERE id=? AND client_id=? AND provider='meta'
            AND connection_id=?''', (asset_id, meta.client_id, conn['id']))
        if not asset:
            raise Problem('Không tìm thấy tài sản Meta.', 404)
        return jsonify(store.all('''SELECT id,status,record_count,latest_available_date,requested_start,
            requested_end,error_code,created_at,finished_at FROM sync_runs WHERE client_id=?
            AND provider='meta' AND asset_id=? ORDER BY created_at DESC LIMIT 20''',
            (meta.client_id, asset_id)))
    
    @app.get('/api/meta/reporting/kpis/<asset_id>')
    @require('admin')
    def reporting_meta_kpis(asset_id):
        # Chỉ cho phép đúng hai tham số ngày.
        if (
            set(request.args) != {'start', 'end'}
            or any(
                len(request.args.getlist(key)) != 1
                for key in ('start', 'end')
            )
        ):
            raise Problem(
                'Cần truyền start và end hợp lệ.',
                400
            )

        first, last = validate_range(
            request.args['start'],
            request.args['end']
        )

        # Kiểm tra OAuth và kết nối đang hoạt động.
        conn = connection()

        # Chỉ đọc tài sản Meta thuộc client hiện tại.
        asset = store.one(
            """
            SELECT id, asset_type
            FROM source_assets
            WHERE id=?
              AND client_id=?
              AND provider='meta'
              AND connection_id=?
              AND enabled=1
            """,
            (asset_id, meta.client_id, conn['id'])
        )

        if not asset:
            raise Problem(
                'Tài sản Meta không hợp lệ hoặc chưa được chọn.',
                404
            )

        if asset['asset_type'] == 'facebook_ad_account':
            source = 'facebook_ads'
            metric_ids = [
                'facebook_ads.spend',
                'facebook_ads.impressions',
                'facebook_ads.clicks',
                'facebook_ads.leads',
            ]

        elif asset['asset_type'] == 'facebook_page':
            source = 'facebook_content'
            metric_ids = [
                'facebook_content.posts_published',
                'facebook_content.engagements',
            ]

        else:
            raise Problem(
                'Loại tài sản Meta chưa hỗ trợ.',
                400
            )

        metrics = {}

        for metric_id in metric_ids:
            metrics[metric_id] = read_metric_series(
                store,
                metric_id=metric_id,
                client_id=meta.client_id,
                allowed_sources={source},
                start=first.isoformat(),
                end=last.isoformat(),
                asset_id=asset_id,
            )

        return jsonify(
            client_id=meta.client_id,
            asset_id=asset_id,
            source=source,
            period={
                'start': first.isoformat(),
                'end': last.isoformat()
            },
            data_origin='persisted_unverified',
            verified=False,
            publishable=False,
            metrics=metrics,
        )
    
    @app.get('/api/meta/reporting/preview')
    @require('admin')
    def reporting_meta_preview():
        # Chỉ sử dụng tài khoản thử nghiệm Meta.
        if meta.client_id != 'client_meta_sandbox':
            raise Problem(
                'Preview Meta chỉ dành cho Sandbox.',
                403
            )

        # Chỉ chấp nhận 3 tham số cần thiết.
        required = {'asset_id', 'start', 'end'}

        if (
            set(request.args) != required
            or any(
                len(request.args.getlist(key)) != 1
                or not request.args.get(key, '').strip()
                for key in required
            )
        ):
            raise Problem(
                'Cần asset_id, start và end hợp lệ.',
                400
            )

        asset_id = request.args['asset_id']

        # Xác thực khoảng ngày.
        first, last = validate_range(
            request.args['start'],
            request.args['end']
        )

        # Kiểm tra kết nối OAuth hiện tại.
        conn = connection()

        # Chỉ sử dụng tài sản thuộc Sandbox
        # và kết nối Meta hiện tại.
        asset = store.one(
            """
            SELECT id, asset_type
            FROM source_assets
            WHERE id=?
              AND client_id=?
              AND provider='meta'
              AND connection_id=?
              AND enabled=1
            """,
            (
                asset_id,
                meta.client_id,
                conn['id']
            )
        )

        if not asset:
            raise Problem(
                'Tài sản Meta không hợp lệ hoặc chưa được chọn.',
                404
            )

        source_by_type = {
            'facebook_ad_account': 'facebook_ads',
            'facebook_page': 'facebook_content'
        }

        source = source_by_type.get(asset['asset_type'])

        if source is None:
            raise Problem(
                'Loại tài sản Meta chưa được hỗ trợ.',
                400
            )

        # Tái sử dụng bộ xử lý Preview có sẵn.
        # Không ghi dữ liệu, không tạo Dataset.
        preview = build_marketing_preview(
            store,
            client_id=meta.client_id,
            allowed_sources={source},
            source=source,
            asset_id=asset['id'],
            start=first.isoformat(),
            end=last.isoformat()
        )

        # Không trả Preview có trạng thái xuất bản.
        if (
            preview.get('client_id') != meta.client_id
            or preview.get('publishable') is not False
            or preview.get('quality', {}).get(
                'independently_verified'
            ) is not False
        ):
            raise Problem(
                'Trạng thái Marketing Preview không an toàn.',
                409
            )

        return jsonify(preview)
