"""Read scoped Google period aggregates; never sum unique users or ranks."""
import json
import math

from .platform_data import _validate_snapshot_payload

FIELDS = {
    'ga4': {'sessions': 'sessions', 'active_users': 'activeUsers',
            'page_views': 'screenPageViews', 'engagement_rate': 'engagementRate'},
    'gsc': {key: key for key in ('clicks', 'impressions', 'ctr', 'position')},
    'keywords': {key: key for key in ('top5', 'top10', 'top20', 'top100')},
}


def comparison_range(store, run, payload):
    if payload.get('previous_requested_start') and payload.get('previous_requested_end'):
        return payload['previous_requested_start'], payload['previous_requested_end']
    if run.get('job_id'):
        job = store.one('SELECT params FROM jobs WHERE id=?', (run['job_id'],))
        if job:
            params = json.loads(job['params'])
            if params.get('compare') is True:
                return params.get('previous_start'), params.get('previous_end')
    return None, None


def period_snapshot(store, *, client_id, asset_id, source, start, end, sync_ids=None):
    """Exact provider scope only. Return latest matching attempt, even if failed."""
    args = [client_id, asset_id]
    selector = ''
    if sync_ids is not None:
        if not sync_ids:
            return None
        selector = ' AND sr.id IN (' + ','.join('?' for _ in sync_ids) + ')'
        args.extend(sync_ids)
    rows = store.all('''SELECT sr.*,ss.payload,ss.source_key,ss.client_id AS snapshot_client_id,
        ss.asset_id AS snapshot_asset_id,ss.provider AS snapshot_provider,
        ss.requested_start AS snapshot_start,ss.requested_end AS snapshot_end
        FROM sync_runs sr LEFT JOIN source_snapshots ss ON ss.sync_run_id=sr.id
        WHERE sr.client_id=? AND sr.asset_id=? AND sr.provider='google'
        AND sr.sync_type!='validation' ''' + selector + ' ORDER BY sr.created_at DESC,sr.id DESC', args)
    for run in rows:
        payload = json.loads(run['payload']) if run.get('payload') else {}
        current = (run['requested_start'], run['requested_end']) == (start, end)
        previous = comparison_range(store, run, payload) == (start, end)
        if not current and not previous:
            continue
        _validate_snapshot_payload(payload)
        if payload and (run['source_key'] != source or run['snapshot_client_id'] != client_id
                        or run['snapshot_asset_id'] != asset_id or run['snapshot_provider'] != 'google'
                        or (run['snapshot_start'], run['snapshot_end']) != (run['requested_start'], run['requested_end'])
                        or payload.get('source') != source
                        or (payload.get('requested_start'), payload.get('requested_end')) != (run['requested_start'], run['requested_end'])):
            raise ValueError('Source snapshot lineage does not match the metric scope.')
        return run, payload, previous
    return None


def snapshot_series(store, metric, result):
    source, field = metric['source'], metric['field']
    contract_key = FIELDS.get(source, {}).get(field)
    if contract_key is None:
        return None
    found = period_snapshot(store, client_id=result['client_id'], asset_id=result['asset_id'],
                            source=source, **result['period'])
    if not found:
        return None
    run, payload, previous = found
    if not payload:
        # Legacy daily-only data remains readable, but cannot acquire a receipt
        # or pass release verification without a normalized source snapshot.
        return None
    result['freshness'].update(latest_sync_status=run['status'], latest_sync_at=run['created_at'])
    if run['status'] not in ('succeeded', 'partial') or not payload:
        result.update(status='stale' if payload else 'no_data', reason='Selected sync failed or has no snapshot.')
        return result
    if payload.get('demo'):
        result.update(status='no_data', reason='Demo snapshot is not provider evidence.')
        return result
    totals = (payload.get('previous') if previous else payload.get('totals')) or {}
    rows_key = 'entries' if source == 'keywords' else 'daily'
    rows = payload.get(('previous_' if previous else '') + rows_key, [])
    if not isinstance(totals, dict) or not isinstance(rows, list):
        raise ValueError('Source snapshot does not contain normalized reporting data.')
    series = []
    for row in rows:
        if not isinstance(row, dict) or not result['period']['start'] <= row.get('date', '') <= result['period']['end']:
            raise ValueError('Source snapshot row is outside the selected period.')
        value = row.get(contract_key)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            series.append({'date': row['date'], 'value': value, 'sync_run_id': run['id'], 'fetched_at': payload.get('fetched_at')})
    latest = (payload.get('previous_date') or payload.get('previous_latest_available_date')
              or max((r['date'] for r in rows), default=None)) if previous else payload.get('latest_available_date')
    value = totals.get(contract_key)
    number = type(value) in (int, float) and math.isfinite(value) and value >= 0
    if source == 'keywords' and number and latest:
        series = [{'date': latest, 'value': value, 'sync_run_id': run['id'], 'fetched_at': payload.get('fetched_at')}]
        coverage = result['summary']['expected_days'] if latest == result['period']['end'] else 0
    else:
        coverage = len({r['date'] for r in rows})
    complete = coverage == result['summary']['expected_days'] and latest == result['period']['end']
    result['series'] = series
    result['summary'].update(value=value if number and complete else None, coverage_days=coverage)
    result['freshness'].update(latest_available_date=latest, last_metric_date=latest)
    result['warnings'] = list(payload.get('warnings', []))
    result['status'] = 'available' if number and complete and payload.get('status') in ('ready', 'delayed') else ('partial' if rows else 'no_data')
    result['reason'] = None if result['status'] == 'available' else 'Missing metric or incomplete snapshot coverage.'
    result['snapshot_sync_run_id'] = run['id']
    return result
