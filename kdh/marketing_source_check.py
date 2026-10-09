"""Verify a candidate against sealed source snapshots and the current review."""
import copy
import hashlib
import json

from flask import jsonify

from .core import Problem
from .marketing_provenance import is_demo, sha, verify_adapter_receipt
from .marketing_release import _release_state
from .metric_catalog import SOURCES, get_metric
from .metric_snapshot import FIELDS, period_snapshot
from .platform_data import DEFAULT_CLIENT_ID
from .report_bundles import _check_no_credentials


class ReadView:
    """Use the caller's transaction for every lineage lookup."""
    def __init__(self, db):
        self.db = db

    def all(self, query, args=()):
        return [dict(row) for row in self.db.execute(query, args).fetchall()]

    def one(self, query, args=()):
        rows = self.all(query, args)
        return rows[0] if rows else None


def candidate_state(store, db, candidate_id):
    row = db.execute('SELECT * FROM datasets WHERE id=?', (candidate_id,)).fetchone()
    if not row:
        raise Problem('Không tìm thấy Release Candidate.', 404)
    try:
        candidate = json.loads(row['data'])
    except (TypeError, ValueError):
        raise Problem('Release Candidate không hợp lệ.', 409) from None
    if not isinstance(candidate, dict) or candidate.get('client_id') != DEFAULT_CLIENT_ID:
        raise Problem('Không tìm thấy Release Candidate của khách hàng.', 404)
    if candidate.get('dataset_kind') != 'marketing_release_candidate_v1':
        raise Problem('Dataset không phải Release Candidate.', 409)
    _check_no_credentials(candidate)
    release = candidate.get('release_candidate', {})
    if not isinstance(release, dict):
        raise Problem('Release Candidate thiếu thông tin nguồn.', 409)
    origin_row, original, assessment, latest, problems = _release_state(db, release.get('origin_dataset_id'))
    issues = list(problems)
    if latest and release.get('review_id') != latest['id']:
        issues.append('review_superseded')
    if release.get('origin_dataset_sha256') != assessment['dataset_sha256']:
        issues.append('origin_dataset_changed')
    expected = copy.deepcopy(original)
    expected.update(id=candidate_id, created_at=candidate.get('created_at'),
                    dataset_kind='marketing_release_candidate_v1', data_origin='persisted_unverified')
    expected['marketing'].update(review_status='approved_internal', verified=False, publishable=False)
    expected['release_candidate'] = {
        'schema_version': '0.1', 'status': 'staged_internal',
        'origin_dataset_id': origin_row['id'], 'origin_dataset_sha256': assessment['dataset_sha256'],
        'review_id': latest['id'] if latest else None, 'review_decision': 'approved_internal',
        'reviewed_at': latest['created_at'] if latest else None,
        'prepared_at': candidate.get('created_at'), 'provider_verified': False,
        'publishable': False, 'approved_claim_ids': [],
    }
    if sha(expected) != sha(candidate) or row['valid'] != 0 or row['report_type'] != origin_row['report_type']:
        issues.append('candidate_changed')
    if is_demo(candidate):
        issues.append('demo_data')
    return row, candidate, original, latest, assessment, issues


def check_candidate(store, db, candidate_id):
    row, candidate, original, latest, assessment, issues = candidate_state(store, db, candidate_id)
    preview = original['marketing']['preview']
    source = original['params']['source']
    spec = SOURCES.get(source)
    checks = []
    reader = ReadView(db)
    evidence = preview.get('evidence_cards', [])
    if not evidence:
        issues.append('no_data')
    if source not in FIELDS:
        issues.append('adapter_origin_not_supported')
    for item in evidence:
        problems = []
        metric = get_metric(item.get('metric_id'))
        asset_id = item.get('asset_id')
        asset = reader.one('SELECT * FROM source_assets WHERE id=?', (asset_id,))
        if (not spec or not asset or not asset['enabled'] or asset['client_id'] != candidate['client_id']
                or asset['provider'] != spec['provider'] or asset['asset_type'] != spec['asset_type']):
            problems.append('asset_scope_mismatch' if asset else 'not_configured')
        connection = reader.one('SELECT * FROM connections WHERE id=?', (asset['connection_id'],)) if asset else None
        if (not connection or connection['client_id'] != candidate['client_id']
                or not spec or connection['provider'] != spec['provider'] or connection['status'] != 'connected'):
            problems.append('not_configured')
        if not metric or metric['source'] != source or item.get('source') != source:
            problems.append('metric_scope_mismatch')
        periods = [(preview['period'], item, False)]
        comparison = item.get('comparison')
        if preview.get('comparison'):
            if not isinstance(comparison, dict) or comparison.get('period') != preview['comparison']:
                problems.append('comparison_missing')
            else:
                periods.append((preview['comparison'], comparison, True))
        witnesses = []
        for period, observation, is_previous in periods:
            ids = observation.get('lineage', {}).get('sync_run_ids', [])
            if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
                problems.append('sync_lineage_missing')
                continue
            found = period_snapshot(reader, client_id=candidate['client_id'], asset_id=asset_id,
                source=source, start=period['start'], end=period['end'], sync_ids=ids)
            if not found:
                problems.append('sync_scope_mismatch')
                continue
            run, payload, previous = found
            if run['error_code'] == 'permission_denied':
                problems.append('permission_denied')
            if run['status'] != 'succeeded' or run['record_count'] <= 0:
                problems.append('sync_failed' if run['status'] == 'failed' else 'partial')
            if not payload:
                problems.append('source_snapshot_missing')
                continue
            if is_demo(payload):
                problems.append('demo_data')
            job = reader.one('SELECT kind,params FROM jobs WHERE id=?', (run['job_id'],)) if run['job_id'] else None
            if not job or job['kind'] != 'analysis' or is_demo(json.loads(job['params'])):
                problems.append('provider_job_not_confirmed')
            if run['connection_id'] != (connection['id'] if connection else None):
                problems.append('connection_scope_mismatch')
            current_attempt = period_snapshot(reader, client_id=candidate['client_id'], asset_id=asset_id,
                                              source=source, **period)
            if current_attempt and current_attempt[0]['id'] != run['id']:
                problems.append('stale')
            key = FIELDS.get(source, {}).get(metric['field']) if metric else None
            totals = (payload.get('previous') if previous else payload.get('totals')) or {}
            expected_value = totals.get(key) if isinstance(totals, dict) and key else None
            value = observation.get('previous_value') if is_previous else observation.get('value')
            if expected_value is None or type(value) not in (int, float) or value != expected_value:
                problems.append('metric_value_mismatch')
            detail_key = ('previous_' if previous else '') + ('entries' if source == 'keywords' else 'daily')
            details = payload.get(detail_key, [])
            dates = {point.get('date') for point in details if isinstance(point, dict)}
            latest_date = max(dates, default=None)
            from datetime import date
            expected_days = (date.fromisoformat(period['end']) - date.fromisoformat(period['start'])).days + 1
            if (latest_date != period['end'] or any(not isinstance(day, str) or not period['start'] <= day <= period['end'] for day in dates)
                    or (source != 'keywords' and len(dates) != expected_days)):
                problems.append('partial')
            normalized_points = ([{'date': latest_date, 'value': expected_value}] if source == 'keywords' else
                                 [{'date': point['date'], 'value': point.get(key)} for point in details])
            if observation.get('daily_observations') != normalized_points:
                problems.append('observations_mismatch')
            snap = reader.one('SELECT * FROM source_snapshots WHERE sync_run_id=?', (run['id'],))
            if not verify_adapter_receipt(db, getattr(store, 'report_cipher', None), run, snap):
                problems.append('provider_origin_unconfirmed')
            witnesses.append({'sync_run_id': run['id'], 'snapshot_sha256': sha(payload), 'period': period,
                              'latest_available_date': latest_date, 'asset_id': asset_id})
        checks.append({'evidence_id': item['evidence_id'], 'metric_id': item['metric_id'],
                       'asset_id': asset_id, 'issues': list(dict.fromkeys(problems)),
                       'status': 'provider_origin_confirmed' if not problems else (
                           'lineage_consistent' if set(problems) == {'provider_origin_unconfirmed'} else
                           next((status for status in ('permission_denied', 'not_configured', 'stale', 'partial') if status in problems), 'release_blocked')),
                       'witnesses': witnesses})
        issues.extend(problems)
    # Only approved, verified KPI observations may be used for claims.
    valued = {item.get('evidence_id') for item in preview.get('widgets', []) if item.get('value') is not None}
    if valued != {item.get('evidence_id') for item in evidence}:
        issues.append('widget_evidence_mismatch')
    issues = list(dict.fromkeys(issues))
    return {
        'schema_version': '1.0', 'candidate_id': candidate_id, 'dataset_id': original['id'],
        'client_id': candidate['client_id'], 'source': source,
        'dataset_sha256': assessment['dataset_sha256'],
        'candidate_sha256': hashlib.sha256(row['data'].encode()).hexdigest(),
        'internal_review_id': latest['id'] if latest else None,
        'state': 'provider_origin_confirmed' if not issues else 'release_blocked',
        'provider_origin_confirmed': not issues, 'checks': checks, 'issues': issues,
        'publishable': False,
    }


def read_source_check(store, candidate_id):
    with store.connect(immediate=True) as db:
        return check_candidate(store, db, candidate_id)


def register_marketing_source_routes(app, store, require):
    @app.get('/api/marketing/release-candidates/<candidate_id>/source-check')
    @require('admin')
    def marketing_source_check(candidate_id):
        return jsonify(read_source_check(store, candidate_id))
