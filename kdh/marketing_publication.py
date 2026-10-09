"""Create sealed release snapshots; enforce policy without weakening legacy guard."""
import copy
import json

from flask import g, jsonify

from .core import Problem, now, pack, uid
from .marketing_approval import latest_approval
from .marketing_provenance import is_demo, seal, sha, unseal
from .marketing_source_check import ReadView, check_candidate
from .metric_catalog import SOURCES
from .metric_snapshot import period_snapshot
from .report_bundles import _admin, _check_no_credentials


def approved_state(store, db, candidate_id):
    checks = check_candidate(store, db, candidate_id)
    approval = latest_approval(db, candidate_id)
    if not approval or approval['decision'] != 'release_approved':
        raise Problem('Chưa có phê duyệt phát hành hiện hành.', 409, 'release_approval_required')
    for key in ('candidate_sha256', 'dataset_sha256', 'internal_review_id'):
        if approval[key] != checks[key]:
            raise Problem('Phê duyệt đã cũ hoặc dữ liệu thay đổi.', 409, 'stale_release_approval')
    _admin(db, approval['reviewer_id'])
    if not checks['provider_origin_confirmed']:
        raise Problem('Bằng chứng nguồn chưa đủ điều kiện phát hành.', 409, 'release_blocked')
    return checks, approval


def create_release_snapshot(store, actor, candidate_id, data, session_id=None):
    if not isinstance(data, dict) or set(data) != {'expected_approval_id', 'expected_candidate_sha256'}:
        raise Problem('Chỉ nhận mã phê duyệt và hash Candidate đã kiểm tra.')
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        checks, approval = approved_state(store, db, candidate_id)
        if data['expected_approval_id'] != approval['id'] or data['expected_candidate_sha256'] != checks['candidate_sha256']:
            raise Problem('Phê duyệt/Candidate đã thay đổi.', 409, 'stale_release_approval')
        candidate_row = db.execute('SELECT data,report_type FROM datasets WHERE id=?', (candidate_id,)).fetchone()
        candidate = json.loads(candidate_row['data'])
        preview = candidate['marketing']['preview']
        source = checks['source']
        # All eligible cards must refer to a single asset and explicit snapshot.
        witnesses = checks['checks'][0]['witnesses']
        current, previous = witnesses[0], witnesses[1]
        reader = ReadView(db)
        _, payload, current_is_previous = period_snapshot(reader, client_id=checks['client_id'],
            asset_id=current['asset_id'], source=source, **preview['period'], sync_ids=[current['sync_run_id']])
        _, previous_payload, previous_is_previous = period_snapshot(reader, client_id=checks['client_id'],
            asset_id=previous['asset_id'], source=source, **preview['comparison'], sync_ids=[previous['sync_run_id']])
        if current_is_previous:
            raise Problem('Kỳ chính cần snapshot được đồng bộ trực tiếp cho kỳ đó.', 409, 'release_scope_unsupported')
        normalized = copy.deepcopy(payload)
        detail = 'entries' if source == 'keywords' else 'daily'
        normalized['previous'] = copy.deepcopy(previous_payload.get('previous' if previous_is_previous else 'totals'))
        normalized['previous_' + detail] = copy.deepcopy(previous_payload.get(('previous_' if previous_is_previous else '') + detail, []))
        normalized['previous_latest_available_date'] = previous['latest_available_date']
        timestamp, dataset_id = now(), uid()
        version = db.execute('SELECT COALESCE(MAX(version),0)+1 AS n FROM marketing_release_snapshots WHERE candidate_id=?',
                             (candidate_id,)).fetchone()['n']
        widgets = copy.deepcopy(preview['widgets'])
        cards = []
        for card in preview['evidence_cards']:
            widget = next(item for item in widgets if item['evidence_id'] == card['evidence_id'])
            widget.update(verified=True, publishable=True, status='available')
            cards.append({'evidence_id': card['evidence_id'], 'metric_id': card['metric_id'],
                'claim': None, 'metric': widget['label'], 'before': card['comparison']['previous_value'],
                'after': card['value'], 'period': preview['period'], 'source': source,
                'asset_id': card['asset_id'], 'data_date': current['latest_available_date'],
                'verification': 'provider_origin_confirmed', 'review_status': 'approved',
                'lineage': copy.deepcopy(card['lineage']),
                'quality': {'status': 'complete', 'warnings': ['Xác nhận qua adapter của hệ thống; không phải kiểm toán độc lập của Google.']}})
        approved_ids = set(json.loads(approval['approved_opportunity_ids']))
        opportunities = [{'id': item['id'], 'title': item['title'],
            'reason': 'Biến động giữa hai kỳ đã đạt ngưỡng cần xem xét của quy tắc ' + item['rule_id'] + '.',
            'supporting_data': [ref['metric_id'] for ref in item['evidence']],
            'evidence_ids': [ref['id'] for ref in item['evidence']], 'priority': None,
            'action': item['suggested_action'], 'review_status': 'approved',
            'conditions': ['Tín hiệu dữ liệu không chứng minh quan hệ nhân quả hoặc dự đoán tăng trưởng.']}
            for item in preview['opportunity_candidates'] if item['id'] in approved_ids]
        release = {
            'schema_version': '1.0', 'version': version, 'candidate_id': candidate_id,
            'origin_dataset_id': checks['dataset_id'], 'approval_id': approval['id'],
            'internal_review_id': checks['internal_review_id'], 'candidate_sha256': checks['candidate_sha256'],
            'dataset_sha256': checks['dataset_sha256'], 'reviewer_id': approval['reviewer_id'],
            'approved_at': approval['created_at'], 'state': 'release_approved',
            'provider_origin_confirmed': True, 'quality': 'complete', 'checks': checks['checks'],
            'policy': {'provisional': True, 'final': True},
        }
        dataset = {'id': dataset_id, 'client_id': checks['client_id'], 'created_at': timestamp,
            'dataset_kind': 'marketing_release_snapshot_v1', 'data_origin': 'provider_origin_confirmed',
            'params': copy.deepcopy(candidate['params']), 'sources': {source: normalized},
            'marketing': {'schema_version': '1.0', 'kind': 'approved_release', 'widgets': widgets},
            'evidence': cards, 'opportunities': opportunities,
            'executive_summary': {'verified_kpi_count': len(cards),
                'limitations': ['Chỉ kết luận trên KPI có bằng chứng. Lưu lượng tăng không xác nhận từ khóa lên Top Google.',
                               'Chưa có mục tiêu/khối lượng công việc được nhập và duyệt thì chưa đánh giá mức đạt cam kết.']},
            'platforms': {key: {'label': spec['label'], 'integration': spec['integration'],
                'status': 'included' if key == source else 'not_in_report'} for key, spec in SOURCES.items()},
            'release': release,
        }
        _check_no_credentials(dataset)
        release['seal'] = seal(store.report_cipher, 'marketing-release-v1', {'sha256': sha(dataset)})
        serialized = pack(dataset)
        if len(serialized.encode()) > 2 * 1024 * 1024:
            raise Problem('Bản phát hành quá lớn.', 413)
        db.execute('INSERT INTO datasets (id,user_id,report_type,created_at,valid,data) VALUES (?,?,?,?,?,?)',
                   (dataset_id, actor, candidate_row['report_type'], timestamp, 1, serialized))
        db.execute('INSERT INTO marketing_release_snapshots (dataset_id,candidate_id,approval_id,version,content_sha256,created_at) VALUES (?,?,?,?,?,?)',
                   (dataset_id, candidate_id, approval['id'], version, sha(dataset), timestamp))
        db.execute('INSERT INTO events (id,user_id,action,at,detail) VALUES (?,?,?,?,?)',
                   (uid(), actor, 'create_marketing_release_snapshot', timestamp,
                    pack({'dataset_id': dataset_id, 'candidate_id': candidate_id, 'approval_id': approval['id']})))
    return {'dataset_id': dataset_id, 'candidate_id': candidate_id, 'version': version,
            'state': 'release_approved', 'published': False}


def validate_release_snapshot(data, store, db=None, publication=False):
    """Published reads verify the frozen seal, never rebuild from live sources."""
    error = Problem('Bản phát hành Marketing chưa được xác nhận hợp lệ.', 409, 'marketing_review_required')
    if store is None or data.get('dataset_kind') != 'marketing_release_snapshot_v1' or is_demo(data):
        raise error
    copy_data = copy.deepcopy(data)
    release = copy_data.get('release')
    if not isinstance(release, dict):
        raise error
    proof = unseal(getattr(store, 'report_cipher', None), 'marketing-release-v1', release.pop('seal', None))
    if (not proof or proof.get('sha256') != sha(copy_data) or release.get('state') != 'release_approved'
            or release.get('provider_origin_confirmed') is not True or release.get('quality') != 'complete'
            or release.get('policy') != {'provisional': True, 'final': True}):
        raise error
    if publication:
        if db is None:
            raise error
        registry = db.execute('SELECT * FROM marketing_release_snapshots WHERE dataset_id=?', (data['id'],)).fetchone()
        if not registry or registry['content_sha256'] != sha(data) or registry['approval_id'] != release['approval_id']:
            raise error
        _, approval = approved_state(store, db, release['candidate_id'])
        if approval['id'] != release['approval_id']:
            raise Problem('Phê duyệt phát hành đã được thay thế.', 409, 'stale_release_approval')


def register_marketing_publication_routes(app, store, require, body):
    @app.post('/api/marketing/release-candidates/<candidate_id>/release-snapshots')
    @require('admin')
    def release_snapshot_create(candidate_id):
        return jsonify(create_release_snapshot(store, g.user['id'], candidate_id, body(), g.session_id)), 201
