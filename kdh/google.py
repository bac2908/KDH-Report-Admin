"""Read-only Google adapters. Never substitute samples on source failure."""
import base64
import hashlib
import json
import math
import re
import secrets
import threading
import time
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import requests
from cryptography.fernet import Fernet

from .core import Problem, now, pack, digest

SCOPES = ['openid', 'email', 'https://www.googleapis.com/auth/analytics.readonly',
          'https://www.googleapis.com/auth/webmasters.readonly', 'https://www.googleapis.com/auth/spreadsheets.readonly']
LABELS = {'ga4': 'Google Analytics 4', 'gsc': 'Search Console', 'keywords': 'Keyword Tracking', 'gmb': 'Google Business Profile'}
REQUEST_DEADLINE = ContextVar('google_request_deadline', default=None)


class SourceError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def call(method, url, **kwargs):
    deadline = REQUEST_DEADLINE.get()
    # Reserve a full network timeout and time to persist results before the deadline.
    if deadline is not None and deadline - time.monotonic() < 60:
        raise SourceError('timeout', 'Đã hết thời gian xử lý của lần chạy này. Chọn từng nguồn hoặc khoảng ngày ngắn hơn rồi thử lại.')
    try:
        response = requests.request(method, url, timeout=(10, 45), **kwargs)
    except requests.Timeout:
        raise SourceError('timeout', 'Nguồn phản hồi quá lâu. Vui lòng thử lại.') from None
    except requests.RequestException:
        raise SourceError('api_error', 'Không thể kết nối đến nguồn dữ liệu. Vui lòng thử lại.') from None
    if response.status_code in (401,):
        raise SourceError('revoked', 'Phiên cấp quyền không còn hợp lệ. Admin cần kết nối lại Google.')
    if response.status_code == 403:
        raise SourceError('permission_denied', 'Thiếu quyền truy cập hoặc API chưa được bật. Liên hệ quản trị tài sản để cấp quyền cho tài khoản Google đã kết nối.')
    if response.status_code == 429:
        raise SourceError('api_error', 'Nguồn đang giới hạn số yêu cầu. Vui lòng thử lại sau.')
    if not response.ok:
        raise SourceError('api_error', f'Nguồn trả về lỗi HTTP {response.status_code}. Kiểm tra cấu hình tài sản và thử lại.')
    try:
        return response.json()
    except ValueError:
        raise SourceError('api_error', 'Nguồn trả về dữ liệu không đọc được.') from None


class Google:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.lock = threading.RLock()
        key = config.get('ENCRYPTION_KEY')
        if key:
            self.cipher = Fernet(key.encode())
            return
        if store.postgres:
            raise RuntimeError('ENCRYPTION_KEY is required with DATABASE_URL; keep the same key across deployments.')
        keyfile = store.folder / 'encryption.key'
        try:
            with keyfile.open('xb') as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        self.cipher = Fernet(keyfile.read_bytes())

    def configured(self):
        return bool(self.config['GOOGLE_CLIENT_ID'] and self.config['GOOGLE_CLIENT_SECRET'])

    def read(self):
        record = self.store.one('SELECT value FROM secrets WHERE name=?', ('google',))
        return json.loads(self.cipher.decrypt(record['value'])) if record else None

    def save(self, data):
        self.store.execute('INSERT INTO secrets VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value', ('google', self.cipher.encrypt(pack(data).encode())))

    def info(self):
        token = self.read()
        return {'configured': self.configured(), 'connected': bool(token),
                'email': token.get('email') if token else None,
                'connected_at': token.get('connected_at') if token else None,
                'checked_at': self.store.setting('google_checked_at'),
                'sources': self.store.setting('google_sources', {})}

    def authorization_url(self, session_id):
        if not self.configured():
            raise Problem('Quản trị hệ thống cần cấu hình Google OAuth Web client ở backend trước khi kết nối.', 503)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        self.store.execute('DELETE FROM oauth_states WHERE expires_at<? OR session_id=?', (now(), session_id))
        self.store.execute('INSERT INTO oauth_states VALUES (?,?,?,?)',
                           (digest(state), session_id, verifier, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
            'client_id': self.config['GOOGLE_CLIENT_ID'], 'redirect_uri': self.config['GOOGLE_REDIRECT_URI'],
            'response_type': 'code', 'scope': ' '.join(SCOPES), 'access_type': 'offline', 'prompt': 'consent',
            'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256'})

    def exchange(self, state, code, session_id):
        with self.store.connect(immediate=True) as db:
            record = db.execute('SELECT * FROM oauth_states WHERE state=? AND session_id=? AND expires_at>?',
                                (digest(state), session_id, now())).fetchone()
            if not record:
                raise Problem('Phiên kết nối đã hết hạn hoặc không hợp lệ. Hãy kết nối lại.', 400)
            db.execute('DELETE FROM oauth_states WHERE state=?', (digest(state),))
        token = call('POST', 'https://oauth2.googleapis.com/token', data={
            'client_id': self.config['GOOGLE_CLIENT_ID'], 'client_secret': self.config['GOOGLE_CLIENT_SECRET'],
            'redirect_uri': self.config['GOOGLE_REDIRECT_URI'], 'code': code, 'code_verifier': record['verifier'],
            'grant_type': 'authorization_code'})
        profile = call('GET', 'https://openidconnect.googleapis.com/v1/userinfo',
                       headers={'Authorization': 'Bearer ' + token['access_token']})
        if not token.get('refresh_token') or not profile.get('email_verified'):
            raise Problem('Google chưa cấp quyền truy cập ngoại tuyến hoặc email chưa xác minh. Kết nối lại và cấp quyền.')
        token.update(email=profile['email'], connected_at=now(), expires_at=(datetime.now(timezone.utc) + timedelta(seconds=token.get('expires_in', 3600))).isoformat())
        with self.lock:
            self.save(token)
            self.store.set_setting('google_sources', {})

    def access_token(self):
        with self.lock:
            record = self.store.one('SELECT value FROM secrets WHERE name=?', ('google',))
            token = json.loads(self.cipher.decrypt(record['value'])) if record else None
            if not token:
                raise SourceError('disconnected', 'Chưa kết nối Google. Liên hệ Admin để kết nối nguồn.')
            if datetime.fromisoformat(token['expires_at']) < datetime.now(timezone.utc) + timedelta(minutes=2):
                try:
                    refreshed = call('POST', 'https://oauth2.googleapis.com/token', data={
                        'client_id': self.config['GOOGLE_CLIENT_ID'], 'client_secret': self.config['GOOGLE_CLIENT_SECRET'],
                        'refresh_token': token['refresh_token'], 'grant_type': 'refresh_token'})
                except SourceError as exc:
                    if 'HTTP 400' in exc.message:
                        raise SourceError('revoked', 'Quyền Google đã hết hạn hoặc bị thu hồi. Admin cần kết nối lại.') from None
                    raise
                token.update(refreshed)
                token['expires_at'] = (datetime.now(timezone.utc) + timedelta(seconds=refreshed.get('expires_in', 3600))).isoformat()
                # Another function may have refreshed or replaced this connection
                # while the provider request was in flight. Never overwrite it.
                saved = self.store.execute('UPDATE secrets SET value=? WHERE name=? AND value=?',
                                           (self.cipher.encrypt(pack(token).encode()), 'google', record['value']))
                if not saved:
                    current = self.read()
                    if not current:
                        raise SourceError('disconnected', 'Kết nối Google đã được ngắt. Admin cần kết nối lại.')
                    return current['access_token']
            return token['access_token']

    def disconnect(self):
        with self.lock:
            token = self.read()
            # Remove locally even if Google's revocation endpoint is temporarily unavailable.
            revoked = True
            if token:
                try:
                    result = requests.post('https://oauth2.googleapis.com/revoke', data={'token': token['refresh_token']}, timeout=15)
                    revoked = result.status_code in (200, 400)
                except requests.RequestException:
                    revoked = False
            self.store.execute('DELETE FROM secrets WHERE name=?', ('google',))
            self.store.set_setting('google_sources', {})
            return revoked

    def fetch(self, source, params):
        token = self.access_token()
        headers = {'Authorization': 'Bearer ' + token}
        return getattr(self, source)(params, headers)

    def ga4(self, p, headers):
        metrics = ['activeUsers', 'sessions', 'screenPageViews', 'engagementRate']
        url = f"https://analyticsdata.googleapis.com/v1beta/properties/{self.config['GA4_PROPERTY_ID']}:runReport"

        def query(start, end, dims=(), requested_metrics=None, limit=10000):
            names = requested_metrics or metrics
            payload = {'dateRanges': [{'startDate': start, 'endDate': end}], 'metrics': [{'name': m} for m in names], 'limit': limit}
            if dims:
                payload['dimensions'] = [{'name': d} for d in dims]
            if dims == ('date',):
                payload['orderBys'] = [{'dimension': {'dimensionName': 'date'}}]
            elif dims:
                payload['orderBys'] = [{'metric': {'metricName': names[0]}, 'desc': True}]
            raw = call('POST', url, headers=headers, json=payload)
            rows = []
            for r in raw.get('rows', []):
                item = {d: r['dimensionValues'][i]['value'] for i, d in enumerate(dims)}
                item.update({m: float(r['metricValues'][i]['value']) if m == 'engagementRate' else int(r['metricValues'][i]['value']) for i, m in enumerate(names)})
                if 'date' in item:
                    item['date'] = datetime.strptime(item['date'], '%Y%m%d').date().isoformat()
                rows.append(item)
            return rows, raw.get('metadata', {})

        totals, metadata = query(p['start'], p['end'])
        daily, _ = query(p['start'], p['end'], ('date',))
        previous, previous_daily = None, []
        if p['compare']:
            values, _ = query(p['previous_start'], p['previous_end'])
            previous = values[0] if values else None
            previous_daily, _ = query(p['previous_start'], p['previous_end'], ('date',))
        channels, _ = query(p['start'], p['end'], ('sessionDefaultChannelGroup',), ['sessions'])
        pages, _ = query(p['start'], p['end'], ('pagePath',), ['screenPageViews'], 100)
        notes = []
        if metadata.get('subjectToThresholding'):
            notes.append('GA4 có áp dụng ngưỡng dữ liệu.')
        if metadata.get('dataLossFromOtherRow'):
            notes.append('Một phần dữ liệu GA4 được gộp vào nhóm (other).')
        if metadata.get('samplingMetadatas'):
            notes.append('GA4 trả về dữ liệu lấy mẫu.')
        return {'totals': totals[0] if totals else {}, 'daily': daily, 'previous': previous, 'previous_daily': previous_daily,
                'channels': channels, 'pages': pages, 'latest_available_date': max((r['date'] for r in daily), default=None),
                'timezone': metadata.get('timeZone', 'Theo cấu hình GA4 property'),
                'asset': self.config['GA4_PROPERTY_ID'], 'warnings': notes}

    def gsc(self, p, headers):
        url = 'https://www.googleapis.com/webmasters/v3/sites/' + quote(self.config['GSC_PROPERTY'], safe='') + '/searchAnalytics/query'

        def query(start, end, dimensions=()):
            payload = {'startDate': start, 'endDate': end, 'type': 'web', 'dataState': 'final', 'rowLimit': 25000}
            if dimensions:
                payload['dimensions'] = list(dimensions)
            if p['exclude_products']:
                payload['dimensionFilterGroups'] = [{'filters': [{'dimension': 'page', 'operator': 'notContains', 'expression': '/san-pham/'}]}]
            raw = call('POST', url, headers=headers, json=payload)
            return [{**{d: r.get('keys', [])[i] for i, d in enumerate(dimensions)},
                     **{m: r[m] for m in ('clicks', 'impressions', 'ctr', 'position')}} for r in raw.get('rows', [])]

        totals, daily = query(p['start'], p['end']), query(p['start'], p['end'], ('date',))
        queries = query(p['start'], p['end'], ('query',))
        previous, previous_daily = None, []
        if p['compare']:
            rows = query(p['previous_start'], p['previous_end'])
            previous = rows[0] if rows else None
            previous_daily = query(p['previous_start'], p['previous_end'], ('date',))
        notes = ['Tổng hàng truy vấn có thể khác KPI do giới hạn và bảo vệ dữ liệu của Search Console.']
        if len(queries) == 25000:
            notes.append('Bảng truy vấn giới hạn 25.000 hàng đầu. KPI lấy từ truy vấn tổng riêng.')
        return {'totals': totals[0] if totals else {}, 'daily': daily, 'queries': queries, 'previous': previous,
                'previous_daily': previous_daily, 'latest_available_date': max((r['date'] for r in daily), default=None),
                'timezone': 'America/Los_Angeles', 'asset': self.config['GSC_PROPERTY'], 'warnings': notes}

    def keywords(self, p, headers):
        sheet = self.config['KEYWORD_SHEET'].replace("'", "''")
        url = 'https://sheets.googleapis.com/v4/spreadsheets/' + quote(self.config['KEYWORD_SPREADSHEET_ID'], safe='') + '/values/' + quote(f"'{sheet}'", safe='')
        raw = call('GET', url, headers=headers, params={'valueRenderOption': 'FORMATTED_VALUE'})
        values = raw.get('values', [])
        rows, warnings = parse_keywords(values, self.config.get('KEYWORD_TRACKING_YEAR'))

        def period(start, end):
            eligible = [r for r in rows if start <= r['date'] <= end]
            latest = max((r['date'] for r in eligible), default=None)
            current = [r for r in eligible if r['date'] == latest]
            totals = {f'top{n}': sum(1 for r in current if 1 <= r['position'] <= n) for n in (5, 10, 20, 100)} if current else {}
            return eligible, latest, totals

        entries, latest, totals = period(p['start'], p['end'])
        previous_entries, previous_date, previous = period(p['previous_start'], p['previous_end']) if p['compare'] else ([], None, None)
        if not entries and rows:
            warnings.append('Không có lần tracking trong kỳ đã chọn. Lần tracking gần nhất trong Sheet: ' + max(r['date'] for r in rows))
        return {'totals': totals, 'entries': entries, 'previous': previous, 'previous_entries': previous_entries,
                'previous_date': previous_date, 'latest_available_date': latest, 'timezone': 'Ngày tracking trong Google Sheets',
                'asset': self.config['KEYWORD_SHEET'], 'warnings': warnings}


def tracking_day(value, year=None):
    text = str(value).strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d/%m/%y', '%b/%d/%Y', '%b/%d/%y'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    if year:
        for fmt in ('%b/%d/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(f'{text}/{year}', fmt).date().isoformat()
            except ValueError:
                pass
    return None


def parse_keywords(values, year=None):
    if not values:
        return [], []
    headers = [str(h).strip().lower() for h in values[0]]

    def col(names):
        return next((i for i, h in enumerate(headers) if h in names), None)

    kw = col(['từ khóa', 'từ khoá', 'keyword', 'keywords', 'query'])
    position = col(['vị trí', 'position', 'rank', 'ranking'])
    day = col(['ngày', 'date', 'ngày tracking', 'tracking date'])
    url = col(['url', 'link', 'trang đích', 'landing page', 'url đích'])
    wide = {i: tracking_day(h, year) for i, h in enumerate(headers) if tracking_day(h, year)}
    ambiguous = [h for h in headers if re.fullmatch(r'(?:[a-z]{3}|\d{1,2})/\d{1,2}(?:/\d{2,4})?', h) and not tracking_day(h, year)]
    if ambiguous and (position is None or day is None):
        raise SourceError('invalid_data', 'Có cột ngày tracking thiếu năm hoặc không hợp lệ. Cấu hình năm tracking thực tế ở backend hoặc ghi đầy đủ năm trong Sheet.')
    if kw is None or (not wide and (position is None or day is None)):
        raise SourceError('invalid_data', 'Sheet Ranking thiếu cột Từ khóa / Vị trí / Ngày hoặc cột ngày có năm rõ ràng. Không suy đoán năm tracking.')
    result, invalid = [], 0
    for row in values[1:]:
        def cell(i):
            return str(row[i]).strip() if i is not None and i < len(row) else ''
        if not cell(kw):
            continue
        points = [(cell(position), tracking_day(cell(day)))] if position is not None and day is not None else [(cell(i), d) for i, d in wide.items()]
        for val, dt in points:
            if not val:
                continue
            try:
                rank = float(val.replace(',', '.'))
                if not dt or not math.isfinite(rank) or rank < 1:
                    raise ValueError()
            except ValueError:
                invalid += 1
                continue
            result.append({'keyword': cell(kw), 'position': rank, 'url': cell(url), 'date': dt})
    if invalid:
        raise SourceError('invalid_data', f'Sheet có {invalid} giá trị ngày/vị trí không hợp lệ. Sửa dữ liệu nguồn để tránh xuất thiếu hàng.')
    return result, []


def source_result(source, params, fetch):
    base = {'source': source, 'label': LABELS[source], 'requested_start': params['start'], 'requested_end': params['end'],
            'fetched_at': now(), 'latest_available_date': None, 'status': 'pending', 'warnings': []}
    try:
        result = fetch()
        base.update(result)
        latest = result.get('latest_available_date')
        base['status'] = 'empty' if not latest else ('delayed' if latest < params['end'] else 'ready')
        if latest and latest < params['end']:
            base['warnings'].append(f'{LABELS[source]} có dữ liệu đến {latest}; không bổ sung số liệu cho ngày còn thiếu.')
        if params['compare'] and not result.get('previous'):
            base['status'] = 'incomplete'
            base['warnings'].append('Chưa có dữ liệu kỳ so sánh. Bỏ tùy chọn so sánh hoặc chọn kỳ khác để xuất.')
        prev_daily = result.get('previous_daily', [])
        if params['compare'] and prev_daily:
            prev_latest = max(r['date'] for r in prev_daily)
            base['previous_latest_available_date'] = prev_latest
            if prev_latest < params['previous_end']:
                base['warnings'].append(f'Kỳ so sánh có dữ liệu đến {prev_latest}.')
    except SourceError as exc:
        base.update(status=exc.status, error=exc.message)
    except Exception:
        # Never send raw response bodies, URLs containing credentials, or traces to operators.
        base.update(status='invalid_data', error='Dữ liệu nguồn không đúng cấu trúc yêu cầu. Kiểm tra nguồn và thử lại.')
    base['fetched_at'] = now()
    return base
