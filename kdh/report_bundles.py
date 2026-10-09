"""Versioned report snapshots. This service never calls a provider or rewrites datasets."""
import copy
import json
import re
from urllib.parse import parse_qsl, urlsplit

from .core import TYPES, Problem, now, pack, parse_day, uid
from .platform_data import DEFAULT_CLIENT_ID


FIELDS = {'client_id', 'name', 'start_date', 'end_date', 'compare_start_date',
          'compare_end_date', 'default_section', 'sections', 'branding'}
PUBLISHED = ('provisional', 'final')
FAILED_SOURCES = {'failed', 'empty', 'disconnected', 'permission_denied', 'api_error',
                  'invalid_data', 'revoked', 'timeout'}


def _guard_marketing_snapshot(payload, store=None, db=None, publication=False):
    """Block internal Marketing datasets from customer publication.

    Checks captured snapshot data, not mutable Dataset rows.
    Legacy Report Bundles without Marketing markers are unchanged.

    All Marketing datasets remain internal-only until a separate,
    audited review/publishing contract is implemented.
    """
    sections = (
        payload.get("sections")
        if isinstance(payload, dict)
        else None
    )

    if not isinstance(sections, dict) or not sections:
        raise Problem(
            "Report Bundle snapshot khong hop le.",
            409,
            "invalid_report_snapshot",
        )

    for section_key, section in sections.items():
        if not isinstance(section, dict):
            raise Problem(
                "Report Bundle section khong hop le.",
                409,
                "invalid_report_snapshot",
            )

        data = section.get("data")

        if not isinstance(data, dict):
            raise Problem(
                "Report Bundle section thieu Dataset.",
                409,
                "invalid_report_snapshot",
            )

        dataset_kind = data.get("dataset_kind")

        # The Dataset Builder introduced in 8.8.2 uses
        # both dataset_kind and marketing metadata.
        # Block if either marker is present, even if someone
        # changes valid=1 or publishable=True in the payload.
        is_marketing_dataset = (
            (
                isinstance(dataset_kind, str)
                and dataset_kind.startswith("marketing_")
            )
            or "marketing" in data
        )

        if is_marketing_dataset:
            if dataset_kind == 'marketing_release_snapshot_v1':
                from .marketing_publication import validate_release_snapshot
                validate_release_snapshot(data, store, db, publication)
                continue
            raise Problem(
                "Section '" + str(section_key) + "' "
                "chua du dieu kien xuat ban. "
                "Dataset Marketing chi duoc xem truoc noi bo; "
                "can quy trinh xac minh va phe duyet rieng.",
                409,
                "marketing_review_required",
            )

def _secret_key(key):
    normalized = re.sub(r'[^a-z0-9]', '', key.lower())
    return any(word in normalized for word in ('token', 'secret', 'password', 'credential',
                                               'authorization', 'cookie', 'privatekey', 'apikey'))


def _check_no_credentials(value, depth=0):
    """Fail closed on credential-bearing input, including nested metadata and URLs."""
    if depth > 40:
        raise Problem('Cấu trúc dữ liệu báo cáo lồng nhau quá sâu.')
    if isinstance(value, dict):
        for key, child in value.items():
            if _secret_key(key):
                raise Problem('Không nhận credential trong cấu hình hoặc dữ liệu báo cáo.', 400, 'unsafe_report_data')
            _check_no_credentials(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_no_credentials(child, depth + 1)
    elif isinstance(value, str):
        if re.search(r'\bBearer\s+\S+', value, flags=re.I):
            raise Problem('Dữ liệu báo cáo chứa thông tin xác thực.', 400, 'unsafe_report_data')
        if value.startswith(('https://', 'http://')):
            try:
                url = urlsplit(value)
                unsafe = url.username or url.password or any(_secret_key(k) for k, _ in parse_qsl(url.query) + parse_qsl(url.fragment))
            except ValueError:
                unsafe = True
            if unsafe:
                raise Problem('URL trong báo cáo chứa thông tin xác thực.', 400, 'unsafe_report_data')


def _input(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise Problem('Trường cấu hình report bundle không hợp lệ.')
    _check_no_credentials(data)
    return copy.deepcopy(data)


def _dates(start, end):
    first, last = parse_day(start), parse_day(end)
    if first > last:
        raise Problem('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
    return first.isoformat(), last.isoformat()


def _metadata(db, data):
    client_id = data.get('client_id')
    if not isinstance(client_id, str):
        raise Problem('Cần chọn khách hàng cho báo cáo.')
    client = db.execute('SELECT id,name,slug,timezone FROM clients WHERE id=?', (client_id,)).fetchone()
    if not client:
        raise Problem('Không tìm thấy khách hàng.', 400, 'client_not_found')
    name = data.get('name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        raise Problem('Tên báo cáo cần từ 1–200 ký tự.')
    start, end = _dates(data.get('start_date'), data.get('end_date'))
    previous_start, previous_end = data.get('compare_start_date'), data.get('compare_end_date')
    if previous_start is not None or previous_end is not None:
        previous_start, previous_end = _dates(previous_start, previous_end)
    branding = data.get('branding', {})
    if not isinstance(branding, dict):
        raise Problem('Branding phải là một đối tượng JSON.')
    return dict(client_id=client_id, name=name.strip(), start_date=start, end_date=end,
                compare_start_date=previous_start, compare_end_date=previous_end,
                default_section=data.get('default_section', 'overview'), branding=branding), dict(client)


def _admin(db, actor, session_id=None):
    user = db.execute('SELECT role,active FROM users WHERE id=?', (actor,)).fetchone()
    if not user or not user['active'] or user['role'] != 'admin':
        raise Problem('Chỉ Admin đang hoạt động được quản lý report bundle.', 403)
    if session_id is not None and not db.execute(
            'SELECT id FROM sessions WHERE id=? AND user_id=? AND expires_at>?',
            (session_id, actor, now())).fetchone():
        raise Problem('Phiên đã bị thu hồi. Đăng nhập lại để tiếp tục.', 401)


def _date_known(value):
    if value is None:
        return None
    try:
        return parse_day(value).isoformat()
    except Problem:
        return None


def _quality(row, data, metadata):
    warnings, flags = [], []
    params = data.get('params', {})
    sources = data.get('sources', {})
    if not isinstance(params, dict) or not isinstance(sources, dict):
        raise Problem('Dataset không có cấu trúc params/sources hợp lệ.', 400, 'invalid_dataset')
    if params.get('report_type') not in (None, row['report_type']):
        raise Problem('Loại báo cáo trong dataset không khớp metadata.', 400, 'invalid_dataset')
    owners = [data.get('client_id'), params.get('client_id')]
    owners = [owner for owner in owners if owner is not None]
    if not owners:
        owners = [DEFAULT_CLIENT_ID]  # Legacy datasets belong to the original client only.
    if any(owner != metadata['client_id'] for owner in owners):
        raise Problem('Dataset không thuộc khách hàng đã chọn.', 400, 'dataset_client_mismatch')
    for key, expected in (('start', metadata['start_date']), ('end', metadata['end_date'])):
        if params.get(key) is None:
            flags.append('unknown')
            warnings.append('Dataset thiếu metadata kỳ báo cáo: ' + key + '.')
        elif params[key] != expected:
            raise Problem('Kỳ của dataset không khớp kỳ report bundle.', 400, 'dataset_period_mismatch')
    comparison = metadata['compare_start_date'] is not None
    if comparison:
        if params.get('compare') is not True:
            flags.append('partial')
            warnings.append('Dataset chưa có kỳ so sánh được yêu cầu.')
        else:
            for key, expected in (('previous_start', metadata['compare_start_date']), ('previous_end', metadata['compare_end_date'])):
                if params.get(key) is None:
                    flags.append('unknown')
                    warnings.append('Dataset thiếu metadata kỳ so sánh: ' + key + '.')
                elif params[key] != expected:
                    raise Problem('Kỳ so sánh của dataset không khớp report bundle.', 400, 'dataset_period_mismatch')
    required = TYPES.get(row['report_type'], ('', []))[1] or list(sources)
    if not required:
        flags.append('unknown')
        warnings.append('Dataset chưa có metadata nguồn để xác minh chất lượng.')
    for key in required:
        source = sources.get(key)
        if not isinstance(source, dict):
            flags.append('unknown')
            warnings.append(key + ': thiếu nguồn bắt buộc.')
            continue
        notes = source.get('warnings', [])
        if isinstance(notes, list):
            warnings.extend(key + ': ' + note for note in notes if isinstance(note, str))
        status = source.get('status')
        if status is not None and not isinstance(status, str):
            raise Problem('Trạng thái nguồn trong dataset không hợp lệ.', 400, 'invalid_dataset')
        if status in FAILED_SOURCES:
            flags.append('failed')
            warnings.append(key + ': nguồn không hợp lệ (' + status + ').')
        elif status not in ('ready', 'delayed'):
            flags.append('partial' if status == 'incomplete' else 'unknown')
            warnings.append(key + ': chưa xác nhận nguồn đầy đủ.')
        else:
            flags.append('complete')
        latest = _date_known(source.get('latest_available_date'))
        if latest is None:
            flags.append('unknown')
            warnings.append(key + ': chưa biết ngày dữ liệu mới nhất.')
        elif latest < metadata['end_date']:
            flags.append('partial')
            warnings.append(key + ': dữ liệu chỉ đến ' + latest + ', chưa đủ đến ' + metadata['end_date'] + '.')
        for field, expected in (('requested_start', metadata['start_date']), ('requested_end', metadata['end_date'])):
            if source.get(field) is not None and source[field] != expected:
                flags.append('partial')
                warnings.append(key + ': metadata kỳ nguồn không khớp báo cáo.')
        if comparison:
            if not source.get('previous'):
                flags.append('partial')
                warnings.append(key + ': thiếu dữ liệu so sánh.')
            previous_latest = source.get('previous_latest_available_date') or source.get('previous_date')
            if previous_latest is None and isinstance(source.get('previous_daily'), list):
                dates = [_date_known(r.get('date')) for r in source['previous_daily'] if isinstance(r, dict)]
                previous_latest = max((d for d in dates if d is not None), default=None)
            if previous_latest is not None and (_date_known(previous_latest) is None or previous_latest < metadata['compare_end_date']):
                flags.append('partial')
                warnings.append(key + ': kỳ so sánh chưa đủ ngày yêu cầu.')
    if not row['valid']:
        flags.append('partial')
        warnings.append('Dataset đã được đánh dấu không hợp lệ (valid=0).')
    if params.get('demo'):
        flags.append('partial')
        warnings.append('DEMO: số liệu mô phỏng, không dùng chốt báo cáo FINAL.')
    # Missing metadata never turns a failed source into a successful one.
    source_states = [s.get('status') for s in sources.values() if isinstance(s, dict)]
    if source_states and all(isinstance(s, str) and s in FAILED_SOURCES for s in source_states):
        status = 'failed'
    elif flags and all(f == 'complete' for f in flags):
        status = 'complete'
    elif flags and all(f == 'unknown' for f in flags):
        status = 'unknown'
    else:
        status = 'partial'
    return {'status': status, 'warnings': list(dict.fromkeys(warnings))}


def validate_sections(db, sections, metadata, inherited=None):
    if not isinstance(sections, list) or not 1 <= len(sections) <= 30:
        raise Problem('Report bundle cần từ 1–30 section.')
    seen, result = set(), {}
    inherited = inherited or {}
    for position, section in enumerate(sections):
        if not isinstance(section, dict) or set(section) != {'key', 'dataset_id'}:
            raise Problem('Mỗi section chỉ nhận key và dataset_id; thứ tự theo danh sách gửi lên.')
        key, dataset_id = section['key'], section['dataset_id']
        if not isinstance(key, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key) or key in seen:
            raise Problem('Section key phải hợp lệ và không trùng nhau.')
        seen.add(key)
        if not isinstance(dataset_id, str) or not 1 <= len(dataset_id) <= 128:
            raise Problem('Dataset ID không hợp lệ.')
        old = inherited.get(dataset_id)
        if old:
            # Reusing an ID means reusing its captured contents, even if somebody
            # changed the legacy row outside this service. New data needs a new ID.
            row, data = old, copy.deepcopy(old['data'])
        else:
            row = db.execute('SELECT id,report_type,created_at,valid,data FROM datasets WHERE id=?', (dataset_id,)).fetchone()
            if not row:
                raise Problem('Không tìm thấy dataset của section.', 400, 'dataset_not_found')
            try:
                data = json.loads(row['data'])
            except (ValueError, TypeError):
                raise Problem('Dataset đã lưu không đọc được.', 400, 'invalid_dataset') from None
        if not isinstance(data, dict):
            raise Problem('Dataset phải là một đối tượng JSON.', 400, 'invalid_dataset')
        _check_no_credentials(data)
        quality = _quality(row, data, metadata)
        result[key] = {'dataset_id': dataset_id, 'report_type': row['report_type'],
                       'created_at': row['created_at'], 'valid': bool(row['valid']),
                       'position': position, 'quality': quality, 'data': data}
    if not isinstance(metadata['default_section'], str) or metadata['default_section'] not in result:
        raise Problem('default_section phải nằm trong danh sách sections.')
    return result


def build_bundle_payload(report_id, revision, metadata, client, sections, generated_at):
    states = [s['quality']['status'] for s in sections.values()]
    quality = states[0] if len(set(states)) == 1 else 'partial'
    warnings = [key + ': ' + warning for key, section in sections.items() for warning in section['quality']['warnings']]
    payload = {
        'schema_version': '1.0',
        'report': {'id': report_id, 'revision': revision, 'status': 'draft', 'name': metadata['name']},
        'client': client,
        'period': {'start': metadata['start_date'], 'end': metadata['end_date']},
        'comparison': ({'start': metadata['compare_start_date'], 'end': metadata['compare_end_date']}
                       if metadata['compare_start_date'] is not None else None),
        'freshness': {'generated_at': generated_at, 'published_at': None},
        'quality': {'status': quality, 'warnings': warnings},
        'navigation': {'default_section': metadata['default_section'], 'sections': list(sections)},
        'branding': metadata['branding'], 'sections': sections,
    }
    _check_no_credentials(payload)
    try:
        pack(payload)
    except (ValueError, TypeError, OverflowError):
        raise Problem('Dataset chứa giá trị không hợp lệ cho JSON.', 400, 'invalid_dataset') from None
    return payload


def _audit(db, actor, action, report_id, revision):
    db.execute('INSERT INTO events (id,user_id,action,at,detail) VALUES (?,?,?,?,?)',
               (uid(), actor, action, now(), pack({'report_id': report_id, 'revision': revision})))


def get_latest_revision(store, report_id, published_only=False, db=None):
    if db is None:
        with store.connect() as connection:
            return get_latest_revision(store, report_id, published_only, connection)
    clause = " AND status IN ('provisional','final')" if published_only else ''
    row = db.execute('SELECT * FROM report_bundles WHERE bundle_key=?' + clause + ' ORDER BY revision DESC LIMIT 1', (report_id,)).fetchone()
    if not row:
        raise Problem('Không tìm thấy report bundle.', 404, 'report_not_found')
    return dict(row)


def get_revision(store, report_id, revision, published_only=False, db=None):
    if type(revision) is not int or not 1 <= revision <= 2147483647:
        raise Problem('Revision phải là số nguyên dương.')
    if db is None:
        with store.connect() as connection:
            return get_revision(store, report_id, revision, published_only, connection)
    row = db.execute('SELECT * FROM report_bundles WHERE bundle_key=? AND revision=?', (report_id, revision)).fetchone()
    if not row or (published_only and row['status'] not in PUBLISHED):
        raise Problem('Không tìm thấy revision được phép đọc.', 404, 'report_not_found')
    return dict(row)


def _payload(row):
    if not row['snapshot_payload']:
        raise Problem('Bundle cũ chưa có snapshot. Tạo revision mới trước khi sử dụng.', 409, 'snapshot_required')
    return json.loads(row['snapshot_payload'])



def get_bundle(
    store,
    report_id,
    revision=None,
    published_only=False,
):
    # Read captured snapshot only.
    # Never rebuild a published report from mutable datasets.
    row = (
        get_latest_revision(
            store,
            report_id,
            published_only,
        )
        if revision is None
        else get_revision(
            store,
            report_id,
            revision,
            published_only,
        )
    )

    payload = _payload(row)

    # Admin may preview drafts internally.
    # The internal API used by KDH-Report-New must
    # never serve an unsafe Marketing snapshot.
    if published_only:
        _guard_marketing_snapshot(payload, store)

    return payload



def _write_sections(db, bundle_id, sections):
    for key, section in sections.items():
        db.execute('INSERT INTO report_bundle_sections (bundle_id,section_key,position,dataset_id,config) VALUES (?,?,?,?,?)',
                   (bundle_id, key, section['position'], section['dataset_id'], '{}'))


def _insert(db, actor, data, report_id, revision, parent=None, inherited=None):
    metadata, client = _metadata(db, data)
    sections = validate_sections(db, data.get('sections'), metadata, inherited)
    generated_at, internal_id = now(), uid()
    payload = build_bundle_payload(report_id, revision, metadata, client, sections, generated_at)
    db.execute('''INSERT INTO report_bundles
        (id,bundle_key,revision,parent_id,client_id,name,status,start_date,end_date,
         compare_start_date,compare_end_date,default_section,schema_version,quality_status,
         warnings,branding,created_by,created_at,published_at,snapshot_payload)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (internal_id, report_id, revision, parent, metadata['client_id'], metadata['name'], 'draft',
         metadata['start_date'], metadata['end_date'], metadata['compare_start_date'], metadata['compare_end_date'],
         metadata['default_section'], '1.0', payload['quality']['status'], pack(payload['quality']['warnings']),
         pack(metadata['branding']), actor, generated_at, None, pack(payload)))
    _write_sections(db, internal_id, sections)
    _audit(db, actor, 'create_report_bundle' if revision == 1 else 'create_report_revision', report_id, revision)
    return {'report_id': report_id, 'revision': revision, 'status': 'draft'}


def create_bundle(store, actor, data, session_id=None):
    data = _input(data)
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        return _insert(db, actor, data, 'rpt_' + uid(), 1)


def _revision_input(db, row):
    data = {key: row[key] for key in FIELDS - {'sections', 'branding'}}
    data['branding'] = json.loads(row['branding'])
    sections = db.execute('SELECT section_key,dataset_id FROM report_bundle_sections WHERE bundle_id=? ORDER BY position,section_key', (row['id'],)).fetchall()
    data['sections'] = [{'key': r['section_key'], 'dataset_id': r['dataset_id']} for r in sections]
    inherited = {s['dataset_id']: s for s in _payload(row)['sections'].values()} if row['snapshot_payload'] else {}
    return data, inherited


def create_revision(store, actor, report_id, changes=None, session_id=None):
    changes = _input(changes if changes is not None else {})
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        previous = get_latest_revision(store, report_id, db=db)
        data, inherited = _revision_input(db, previous)
        if 'client_id' in changes and changes['client_id'] != previous['client_id']:
            raise Problem('Không chuyển report_id sang khách hàng khác. Tạo bundle mới.')
        return _insert(db, actor, {**data, **changes}, report_id, previous['revision'] + 1, previous['id'], inherited)


def update_draft(store, actor, report_id, revision, changes, session_id=None):
    changes = _input(changes)
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        row = get_revision(store, report_id, revision, db=db)
        if row['status'] != 'draft':
            raise Problem('Revision đã xuất bản không được sửa. Hãy tạo revision mới.', 409, 'immutable_revision')
        data, inherited = _revision_input(db, row)
        if 'client_id' in changes and changes['client_id'] != row['client_id']:
            raise Problem('Không chuyển report_id sang khách hàng khác.')
        metadata, client = _metadata(db, {**data, **changes})
        sections = validate_sections(db, changes.get('sections', data['sections']), metadata, inherited)
        payload = build_bundle_payload(report_id, revision, metadata, client, sections, now())
        db.execute('''UPDATE report_bundles SET name=?,start_date=?,end_date=?,compare_start_date=?,
            compare_end_date=?,default_section=?,quality_status=?,warnings=?,branding=?,snapshot_payload=? WHERE id=?''',
            (metadata['name'], metadata['start_date'], metadata['end_date'], metadata['compare_start_date'],
             metadata['compare_end_date'], metadata['default_section'], payload['quality']['status'],
             pack(payload['quality']['warnings']), pack(metadata['branding']), pack(payload), row['id']))
        db.execute('DELETE FROM report_bundle_sections WHERE bundle_id=?', (row['id'],))
        _write_sections(db, row['id'], sections)
        _audit(db, actor, 'update_report_draft', report_id, revision)
        return {'report_id': report_id, 'revision': revision, 'status': 'draft'}


def _publish(store, actor, report_id, revision, status, session_id):
    with store.connect(immediate=True) as db:
        _admin(db, actor, session_id)
        row = get_revision(store, report_id, revision, db=db)
        if row['status'] == 'final' and status != 'final':
            raise Problem('Không thể hạ trạng thái FINAL.', 409, 'immutable_revision')
        payload = _payload(row)
        _guard_marketing_snapshot(payload, store, db, publication=row['status'] != status)

        if row['status'] == status:
            return {'report_id': report_id, 'revision': revision, 'status': status}
        if status == 'final' and (payload['quality']['status'] != 'complete' or
                                 not all(s['valid'] and s['quality']['status'] == 'complete' for s in payload['sections'].values())):
            raise Problem('Chưa thể FINAL: các section phải có dataset hợp lệ và đủ dữ liệu đến hết kỳ.', 409, 'incomplete_report')
        # Only this lifecycle metadata can change on provisional -> final.
        # All source data, generated_at, and original published_at remain frozen.
        payload['report']['status'] = status
        published_at = row['published_at'] or now()
        payload['freshness']['published_at'] = published_at
        db.execute('UPDATE report_bundles SET status=?,published_at=?,snapshot_payload=? WHERE id=?',
                   (status, published_at, pack(payload), row['id']))
        _audit(db, actor, 'publish_report_' + status, report_id, revision)
        return {'report_id': report_id, 'revision': revision, 'status': status}


def publish_provisional(store, actor, report_id, revision, session_id=None):
    return _publish(store, actor, report_id, revision, 'provisional', session_id)


def publish_final(store, actor, report_id, revision, session_id=None):
    return _publish(store, actor, report_id, revision, 'final', session_id)
