"""Append-only release decisions; human approval never invents provenance."""
import json

from flask import g, jsonify

from .core import Problem, now, pack, uid
from .marketing_source_check import check_candidate
from .report_bundles import _admin, _check_no_credentials


def latest_approval(db, candidate_id):
    row = db.execute('''SELECT * FROM marketing_release_approvals WHERE candidate_id=?
        ORDER BY created_at DESC,id DESC LIMIT 1''', (candidate_id,)).fetchone()
    return dict(row) if row else None


def submit_release_approval(store, actor, candidate_id, data, session_id=None):
    required = {'decision', 'note', 'expected_candidate_sha256', 'expected_dataset_sha256', 'expected_review_id'}
    if (not isinstance(data, dict) or not required <= set(data)
            or set(data) - required - {'approved_opportunity_ids'}
            or data.get('decision') not in ('release_approved', 'release_blocked')
            or not isinstance(data.get('note'), str) or not 10 <= len(data['note'].strip()) <= 1000):
        raise Problem('Quyết định hoặc ghi chú duyệt phát hành không hợp lệ.')
    _check_no_credentials(data)
    ids = data.get('approved_opportunity_ids', [])
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
        raise Problem('Danh sách đề xuất được duyệt không hợp lệ.')
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        checks = check_candidate(store, db, candidate_id)
        for supplied, actual in (('expected_candidate_sha256', 'candidate_sha256'),
                                 ('expected_dataset_sha256', 'dataset_sha256'), ('expected_review_id', 'internal_review_id')):
            if data[supplied] != checks[actual]:
                raise Problem('Dữ liệu hoặc review đã đổi. Kiểm tra lại trước khi duyệt.', 409, 'stale_release_review')
        if data['decision'] == 'release_approved' and not checks['provider_origin_confirmed']:
            raise Problem('Chưa thể duyệt phát hành: ' + ', '.join(checks['issues']), 409, 'release_blocked')
        row = db.execute('SELECT data FROM datasets WHERE id=?', (candidate_id,)).fetchone()
        opportunities = json.loads(row['data'])['marketing']['preview']['opportunity_candidates']
        allowed = {item['id'] for item in opportunities if isinstance(item, dict)}
        if not set(ids) <= allowed:
            raise Problem('Đề xuất không thuộc Candidate đang duyệt.')
        # Opportunities have independent evidence. Until every referenced claim
        # is included in the verified candidate, they cannot be approved.
        verified = {item['evidence_id'] for item in checks['checks'] if not item['issues']}
        for item in opportunities:
            if item.get('id') in ids:
                refs = item.get('evidence', [])
                if not refs or any(not isinstance(ref, dict) or ref.get('id') not in verified for ref in refs):
                    raise Problem('Đề xuất còn bằng chứng chưa được xác minh.', 409, 'opportunity_unverified')
        approval_id, timestamp = uid(), now()
        db.execute('''INSERT INTO marketing_release_approvals
            (id,candidate_id,origin_dataset_id,client_id,reviewer_id,internal_review_id,dataset_sha256,
             candidate_sha256,decision,note,checks,approved_opportunity_ids,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (approval_id, candidate_id, checks['dataset_id'], checks['client_id'], actor, checks['internal_review_id'],
             checks['dataset_sha256'], checks['candidate_sha256'], data['decision'], data['note'].strip(),
             pack(checks), pack(ids), timestamp))
        db.execute('INSERT INTO events (id,user_id,action,at,detail) VALUES (?,?,?,?,?)',
                   (uid(), actor, data['decision'], timestamp, pack({'candidate_id': candidate_id, 'approval_id': approval_id})))
    return {'approval_id': approval_id, 'candidate_id': candidate_id, 'decision': data['decision'],
            'created_at': timestamp, 'publishable': False}


def register_marketing_approval_routes(app, store, require, body):
    @app.get('/api/marketing/release-candidates/<candidate_id>/approval')
    @require('admin')
    def release_approval_get(candidate_id):
        with store.connect(immediate=True) as db:
            checks = check_candidate(store, db, candidate_id)
            latest = latest_approval(db, candidate_id)
        return jsonify(checks=checks, latest_approval=latest, state=(latest['decision'] if latest else 'release_review'))

    @app.post('/api/marketing/release-candidates/<candidate_id>/approval')
    @require('admin')
    def release_approval_post(candidate_id):
        return jsonify(submit_release_approval(store, g.user['id'], candidate_id, body(), g.session_id)), 201
