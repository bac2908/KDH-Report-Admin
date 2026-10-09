"""Server-sealed adapter receipts. A successful sync/review is not provenance.

The trust boundary is the configured backend key and the authenticated adapter
code path. This is an application attestation, not a signature issued by Google.
There is deliberately no HTTP endpoint for creating receipts.
"""
import copy
import hashlib
import json

from cryptography.fernet import InvalidToken

from .core import now, pack
from .platform_data import _validate_snapshot_payload


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def is_demo(value):
    if isinstance(value, dict):
        if any(value.get(key) is True for key in ('demo', 'mock', 'is_demo', 'is_mock')):
            return True
        if any(value.get(key) in ('demo', 'mock', 'fixture', 'simulated')
               for key in ('data_origin', 'origin', 'mode') if isinstance(value.get(key), str)):
            return True
        return any(is_demo(child) for child in value.values())
    return isinstance(value, list) and any(is_demo(child) for child in value)


def seal(cipher, kind, value):
    return cipher.encrypt(pack({'kind': kind, 'value': value}).encode()).decode()


def unseal(cipher, kind, envelope):
    if cipher is None or not isinstance(envelope, str):
        return None
    try:
        data = json.loads(cipher.decrypt(envelope.encode()))
        return data['value'] if data['kind'] == kind else None
    except (InvalidToken, ValueError, TypeError, KeyError):
        return None


class AdapterResult(dict):
    """Receipt is an object attribute; never serialized as reporting data."""


def seal_google_result(cipher, source, params, data):
    _validate_snapshot_payload(data)
    result = AdapterResult(copy.deepcopy(data))
    fields = sorted(set(data) - {'warnings'})
    result.receipt = seal(cipher, 'google-adapter-v1', {
        'source': source, 'params': copy.deepcopy(params), 'fields': fields,
        'sha256': sha({key: data[key] for key in fields}),
    })
    return result


def _claims(run, snapshot):
    return {'sync_run_id': run['id'], 'client_id': run['client_id'], 'asset_id': run['asset_id'],
            'connection_id': run['connection_id'], 'provider': run['provider'],
            'source': snapshot['source_key'], 'requested_start': run['requested_start'],
            'requested_end': run['requested_end'], 'status': run['status'],
            'latest_available_date': run['latest_available_date'],
            'payload_sha256': sha(json.loads(snapshot['payload']))}


def record_adapter_receipt(store, cipher, sync_id, result, receipt):
    """Called only after a successful real-adapter fetch and persisted snapshot."""
    proof = unseal(cipher, 'google-adapter-v1', receipt)
    if not proof or is_demo(result) or is_demo(proof['params']):
        return False
    if sha({key: result.get(key) for key in proof['fields']}) != proof['sha256']:
        return False
    with store.connect(immediate=True) as db:
        run = db.execute('SELECT * FROM sync_runs WHERE id=?', (sync_id,)).fetchone()
        snapshot = db.execute('SELECT * FROM source_snapshots WHERE sync_run_id=?', (sync_id,)).fetchone()
        if not run or not snapshot or run['status'] not in ('succeeded', 'partial') or not run['job_id']:
            return False
        job = db.execute('SELECT kind,params FROM jobs WHERE id=?', (run['job_id'],)).fetchone()
        if not job or job['kind'] not in ('analysis', 'connection'):
            return False
        params = json.loads(job['params'])
        if params != proof['params'] or is_demo(params) or snapshot['source_key'] != proof['source']:
            return False
        if (run['requested_start'], run['requested_end']) != (params['start'], params['end']):
            return False
        if sha(json.loads(snapshot['payload'])) != sha(result):
            return False
        claims = _claims(run, snapshot)
        claims['params'] = params
        db.execute('INSERT INTO source_attestations (sync_run_id,claims,seal,created_at) VALUES (?,?,?,?)',
                   (sync_id, pack(claims), seal(cipher, 'source-attestation-v1', claims), now()))
    return True


def verify_adapter_receipt(db, cipher, run, snapshot):
    row = db.execute('SELECT claims,seal FROM source_attestations WHERE sync_run_id=?', (run['id'],)).fetchone()
    if not row:
        return False
    claims = unseal(cipher, 'source-attestation-v1', row['seal'])
    try:
        if not claims or claims != json.loads(row['claims']):
            return False
        if any(claims.get(key) != value for key, value in _claims(run, snapshot).items()):
            return False
        job = db.execute('SELECT params FROM jobs WHERE id=?', (run['job_id'],)).fetchone()
        return bool(job and json.loads(job['params']) == claims.get('params') and not is_demo(claims['params']))
    except (ValueError, TypeError, KeyError):
        return False
