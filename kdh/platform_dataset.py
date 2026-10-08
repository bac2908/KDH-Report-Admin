"""Build Dataset payloads from persisted Google foundation data, without providers.

This repository does not insert a Dataset or change the worker's production flow.
Snapshots retain period aggregates and detail that the upsertable daily table
cannot reproduce. Only explicit sync IDs are read; there is no latest-run lookup.
"""
import copy
import json
import re

from .core import TYPES, Problem, filters, now, pack, parse_day, uid
from .platform_data import _validate_snapshot_payload


SOURCES = {
    'ga4': ('ga4_property', 'Google Analytics 4'),
    'gsc': ('search_console_property', 'Search Console'),
    'keywords': ('keyword_sheet', 'Keyword Tracking'),
}
METRICS = {
    'ga4': {'active_users': 'activeUsers', 'sessions': 'sessions',
            'page_views': 'screenPageViews', 'engagement_rate': 'engagementRate'},
    'gsc': {key: key for key in ('clicks', 'impressions', 'ctr', 'position')},
}
ERRORS = {
    'permission_denied': 'Tài khoản chưa có quyền đọc nguồn dữ liệu.',
    'disconnected': 'Nguồn dữ liệu chưa được kết nối.',
    'revoked': 'Quyền truy cập nguồn dữ liệu đã bị thu hồi.',
    'timeout': 'Lần đồng bộ nguồn dữ liệu đã hết thời gian chờ.',
    'api_error': 'Nguồn dữ liệu trả về lỗi khi đồng bộ.',
    'invalid_data': 'Dữ liệu của lần đồng bộ chưa hợp lệ. Kiểm tra nguồn rồi đồng bộ lại.',
}


def _reject(message, code='invalid_platform_dataset'):
    raise Problem(message, 409, code)


def _safe(value):
    try:
        _validate_snapshot_payload(value)
        pack(value)
    except (ValueError, TypeError, OverflowError, RecursionError):
        _reject('Dữ liệu đã lưu chứa thông tin nhạy cảm hoặc JSON không hợp lệ.')
    return value


def _decode(value, expected):
    try:
        result = json.loads(value)
    except (ValueError, TypeError, RecursionError):
        _reject('Không đọc được cấu trúc dữ liệu đã lưu.')
    if not isinstance(result, expected):
        _reject('Cấu trúc dữ liệu đã lưu không hợp lệ.')
    return _safe(result)


def _notes(value):
    if not isinstance(value, list) or any(not isinstance(note, str) for note in value):
        _reject('Cảnh báo của nguồn dữ liệu không hợp lệ.')
    return value


def _in_period(value, start, end):
    try:
        day = parse_day(value).isoformat()
    except (Problem, TypeError, ValueError):
        _reject('Ngày dữ liệu đã lưu không hợp lệ.')
    if day != value or not start <= day <= end:
        _reject('Dữ liệu đã lưu nằm ngoài kỳ được yêu cầu.', 'dataset_period_mismatch')


class PlatformDatasetRepository:
    def __init__(self, store):
        self.store = store

    def build(self, *, client_id, params, sync_runs, organization=None,
              dataset_id=None, created_at=None):
        """Return the current Dataset contract; never write or call a provider.

        Supports SEO and its individual GA4/GSC/Keywords report types. Params use
        core.filters' existing consecutive comparison period. Optional ID/time
        allow the caller to own identity and reproduce the entire payload.
        If omitted, identity/time follow the current worker's uid()/now() policy.
        """
        if not isinstance(client_id, str) or not client_id:
            _reject('Cần chỉ định khách hàng của Dataset.')
        if not isinstance(params, dict) or params.get('report_type') not in ('seo', *SOURCES):
            _reject('Repository hiện chỉ dựng Dataset SEO và các nguồn Google của SEO.')
        _safe(params)
        p = filters(params)
        if p.get('demo') or params.get('client_id', client_id) != client_id:
            _reject('Dataset phải dùng dữ liệu thật của đúng khách hàng.')
        for key in ('previous_start', 'previous_end', 'search_type'):
            if key in params and params[key] != p.get(key):
                _reject('Bộ lọc không khớp kỳ so sánh hoặc loại tìm kiếm hiện hành.')
        required = TYPES[p['report_type']][1]
        if (not isinstance(sync_runs, dict) or set(sync_runs) != set(required)
                or any(not isinstance(value, str) or not value for value in sync_runs.values())
                or len(set(sync_runs.values())) != len(sync_runs)):
            _reject('Cần chỉ định đúng một sync_run_id cho từng nguồn của Dataset.')
        sources = {}
        with self.store.connect() as db:
            # One consistent read view, including during concurrent daily upserts.
            if self.store.postgres:
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            else:
                db.execute('BEGIN')
            if not db.execute('SELECT id FROM clients WHERE id=?', (client_id,)).fetchone():
                _reject('Không tìm thấy khách hàng của Dataset.', 'client_not_found')
            for source in required:
                sources[source] = self._source(db, client_id, p, source, sync_runs[source])
            if organization is None:
                row = db.execute("SELECT value FROM settings WHERE key='organization'").fetchone()
                organization = _decode(row['value'], dict) if row else {'name': 'KinderHealth', 'author': ''}
        if not isinstance(organization, dict):
            _reject('Thông tin đơn vị báo cáo không hợp lệ.')
        dataset = {'id': dataset_id if dataset_id is not None else uid(),
                   'client_id': client_id, 'sync_runs': dict(sync_runs), 'params': p,
                   'created_at': created_at if created_at is not None else now(),
                   'sources': sources, 'organization': copy.deepcopy(organization)}
        return _safe(dataset)

    def _source(self, db, client_id, p, source, sync_id):
        run = db.execute('SELECT * FROM sync_runs WHERE id=?', (sync_id,)).fetchone()
        if not run:
            _reject('Không tìm thấy lần đồng bộ đã chọn.', 'sync_run_not_found')
        if run['client_id'] != client_id or run['provider'] != 'google':
            _reject('Lần đồng bộ không thuộc khách hàng hoặc provider đã chọn.', 'sync_lineage_mismatch')
        if (run['requested_start'], run['requested_end']) != (p['start'], p['end']):
            _reject('Kỳ đồng bộ không khớp kỳ Dataset.', 'dataset_period_mismatch')
        asset = db.execute('SELECT client_id,provider,asset_type FROM source_assets WHERE id=?',
                           (run['asset_id'],)).fetchone()
        if (not asset or asset['client_id'] != client_id or asset['provider'] != 'google'
                or asset['asset_type'] != SOURCES[source][0]):
            _reject('Tài sản của lần đồng bộ không khớp nguồn Dataset.', 'sync_lineage_mismatch')
        if run['status'] not in ('succeeded', 'partial', 'failed'):
            _reject('Lần đồng bộ chưa hoàn tất.', 'sync_run_not_finished')
        # A linked job retains filter choices not separately stored on sync_runs.
        # Standalone syncs still validate canonical comparison dates and every row.
        if run['job_id']:
            job = db.execute('SELECT params FROM jobs WHERE id=?', (run['job_id'],)).fetchone()
            if not job:
                _reject('Thiếu thông tin tác vụ của lần đồng bộ.')
            original = _decode(job['params'], dict)
            keys = ['start', 'end', 'compare']
            if p['compare']:
                keys += ['previous_start', 'previous_end']
            if source == 'gsc':
                keys += ['search_type', 'exclude_products']
            if any(original.get(key) != p.get(key) for key in keys):
                _reject('Bộ lọc Dataset không khớp tác vụ đã đồng bộ.', 'dataset_period_mismatch')
        if run['status'] == 'failed':
            return self._failed(source, run)
        snapshot = db.execute('SELECT * FROM source_snapshots WHERE sync_run_id=?', (sync_id,)).fetchone()
        if not snapshot:
            _reject('Lần đồng bộ thiếu snapshot nguồn; chưa thể dựng Dataset.', 'source_snapshot_missing')
        expected = {'client_id': client_id, 'asset_id': run['asset_id'], 'provider': 'google',
                    'source_key': source, 'requested_start': p['start'], 'requested_end': p['end']}
        if any(snapshot[key] != value for key, value in expected.items()):
            _reject('Snapshot không khớp lineage của lần đồng bộ.', 'sync_lineage_mismatch')
        result = _decode(snapshot['payload'], dict)
        expected = {'source': source, 'requested_start': p['start'], 'requested_end': p['end'],
                    'latest_available_date': run['latest_available_date']}
        if any(key not in result or result[key] != value for key, value in expected.items()):
            _reject('Metadata snapshot không khớp lần đồng bộ.', 'sync_lineage_mismatch')
        statuses = ('ready', 'empty') if run['status'] == 'succeeded' else ('delayed', 'incomplete', 'partial')
        if result.get('status') not in statuses:
            _reject('Trạng thái snapshot không khớp trạng thái đồng bộ.')
        if any(not isinstance(result.get(key), str) for key in ('label', 'fetched_at')):
            _reject('Snapshot thiếu thông tin nguồn hoặc thời điểm lấy dữ liệu.')
        _notes(result.get('warnings'))
        if not isinstance(result.get('totals'), dict) or not isinstance(result.get('previous'), (dict, type(None))):
            _reject('Snapshot thiếu KPI tổng hợp hợp lệ.')
        for key in {'ga4': ('channels', 'pages'), 'gsc': ('queries',), 'keywords': ()}[source]:
            if not isinstance(result.get(key), list):
                _reject('Snapshot thiếu bảng chi tiết của nguồn.')
        if result['latest_available_date'] is not None:
            _in_period(result['latest_available_date'], p['start'], p['end'])
        if p['compare']:
            if not result.get('previous') and result['status'] in ('ready', 'delayed'):
                _reject('Snapshot chưa có dữ liệu kỳ so sánh được yêu cầu.')
            for key in ('previous_latest_available_date', 'previous_date'):
                if result.get(key) is not None:
                    _in_period(result[key], p['previous_start'], p['previous_end'])
        elif result.get('previous') or result.get('previous_date') or result.get('previous_latest_available_date'):
            _reject('Snapshot có kỳ so sánh khác với bộ lọc Dataset.')
        rows = db.execute('SELECT * FROM daily_metrics WHERE sync_run_id=? ORDER BY metric_date,entity_id,dimension_key',
                          (sync_id,)).fetchall()
        self._series(result, source, rows, run, p)
        return result

    @staticmethod
    def _failed(source, run):
        code = run['error_code']
        if not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', code):
            code = 'invalid_data'
        status = code if code in ERRORS else 'invalid_data'
        # Raw persisted exception messages may contain response bodies/credentials.
        # Keep the error code and safe source status, never reflect that raw text.
        return {'source': source, 'label': SOURCES[source][1], 'status': status,
                'error_code': code, 'error': ERRORS[status],
                'requested_start': run['requested_start'], 'requested_end': run['requested_end'],
                'fetched_at': run['fetched_at'], 'latest_available_date': run['latest_available_date'],
                'warnings': _notes(_decode(run['warnings'], list))}

    @staticmethod
    def _series(result, source, rows, run, p):
        fields = ('entries', 'previous_entries') if source == 'keywords' else ('daily', 'previous_daily')
        by_key = {}
        for index, field in enumerate(fields):
            series = result.get(field)
            if not isinstance(series, list):
                _reject('Snapshot thiếu chuỗi dữ liệu của nguồn.')
            if index and series and not p['compare']:
                _reject('Snapshot có chuỗi kỳ so sánh ngoài bộ lọc Dataset.')
            for item in series:
                if not isinstance(item, dict):
                    _reject('Hàng dữ liệu snapshot không hợp lệ.')
                start, end = (p['previous_start'], p['previous_end']) if index else (p['start'], p['end'])
                _in_period(item.get('date'), start, end)
                if source == 'keywords':
                    if any(not isinstance(item.get(key), str) for key in ('keyword', 'url')) or 'position' not in item:
                        _reject('Hàng từ khóa trong snapshot không hợp lệ.')
                    key = (item['date'], item['keyword'].strip(), item['url'].strip())
                else:
                    key = (item['date'], '', '')
                    if key in by_key:
                        _reject('Snapshot có ngày dữ liệu bị trùng.')
                by_key.setdefault(key, []).append(item)
        for row in rows:
            if any(row[key] != run[key] for key in ('client_id', 'asset_id', 'provider')):
                _reject('Số liệu ngày không khớp lineage của lần đồng bộ.', 'sync_lineage_mismatch')
            key = (row['metric_date'], row['entity_id'], row['dimension_key'])
            entries = by_key.get(key)
            if not entries:
                _reject('Số liệu ngày không thuộc chuỗi snapshot của lần đồng bộ.')
            metrics, dimensions = _decode(row['metrics'], dict), _decode(row['dimensions'], dict)
            if source == 'keywords':
                if (row['entity_type'] != 'keyword' or dimensions.get('keyword') != row['entity_id']
                        or dimensions.get('url') != row['dimension_key'] or 'position' not in metrics
                        or not any(item['position'] == metrics['position'] for item in entries)):
                    _reject('Số liệu từ khóa không khớp snapshot.')
                # Keyword rows can collapse duplicate sheet entries on upsert.
                # Keep the complete snapshot, its order, duplicates and metadata.
            else:
                mapping = METRICS[source]
                if row['entity_type'] != 'website' or dimensions or any(key not in metrics for key in mapping):
                    _reject('Cấu trúc số liệu ngày không hợp lệ.')
                mapped = {target: metrics[key] for key, target in mapping.items()}
                if any(entries[0].get(key) != value for key, value in mapped.items()):
                    _reject('Số liệu ngày không khớp snapshot của lần đồng bộ.')
                entries[0].update(mapped)
        # Later syncs can overwrite some/all daily rows and their sync_run_id.
        # Missing rows remain from THIS snapshot, never from another sync.
        # Period totals/rates are never calculated from the daily series.
