"""Backend-only Meta OAuth. No assets, insights, sync, or Dataset operations."""
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

import requests
from cryptography.fernet import InvalidToken

from .core import Problem, digest, now, pack
from .google import SourceError
from .platform_data import DEFAULT_CLIENT_ID, PlatformData

# Required read permissions for the app's Facebook Login for Business configuration.
# OAuth validates the grant only; it never discovers assets or fetches reports.
REQUIRED_PERMISSIONS = (
    'pages_show_list',
    'pages_read_engagement',
    'ads_read',
)


class Meta:
    def __init__(self, store, config, cipher):
        self.store, self.config, self.cipher = store, config, cipher
        self.client_id = DEFAULT_CLIENT_ID
        self.secret_name = 'meta:' + self.client_id
        self.platform = PlatformData(store)

    def configured(self):
        try:
            uri = urlsplit(self.config['META_REDIRECT_URI'])
            app = urlsplit(self.config['APP_URL'])
        except ValueError:
            return False
        return bool(re.fullmatch(r'[0-9]+', self.config['META_APP_ID']) and
                    self.config['META_APP_SECRET'] and
                    re.fullmatch(r'[0-9]+', self.config.get('META_CONFIG_ID', '')) and
                    re.fullmatch(r'v[0-9]+\.[0-9]+', self.config['META_GRAPH_VERSION']) and
                    uri.scheme == app.scheme and uri.netloc == app.netloc and
                    uri.path == '/api/meta/callback' and not uri.query and not uri.fragment and
                    not uri.username and not uri.password and
                    (uri.scheme == 'https' or (uri.scheme == 'http' and
                     uri.hostname in ('localhost', '127.0.0.1', '::1'))))

    def config_hash(self):
        return digest(pack([self.config[key] for key in
                           ('META_APP_ID', 'META_APP_SECRET', 'META_CONFIG_ID', 'META_GRAPH_VERSION', 'META_REDIRECT_URI')]))

    def read(self):
        record = self.store.one('SELECT value FROM secrets WHERE name=?', (self.secret_name,))
        return json.loads(self.cipher.decrypt(bytes(record['value']))) if record else None

    def info(self):
        result = {'configured': self.configured(), 'connected': False, 'has_connection': False,
                  'status': 'disconnected', 'client_id': self.client_id, 'account_id': None,
                  'account_name': None, 'connected_at': None, 'expires_at': None,
                  'data_access_expires_at': None, 'scopes': []}
        try:
            token = self.read()
        except (InvalidToken, ValueError, TypeError):
            return {**result, 'has_connection': True, 'status': 'error'}
        if not token:
            return result
        if not isinstance(token, dict) or not isinstance(token.get('expires_at'), str):
            return {**result, 'has_connection': True, 'status': 'error'}
        # Explicit allowlist: no token, secret, provider response, or proof is public.
        result.update({key: token.get(key) for key in
                       ('account_id', 'account_name', 'connected_at', 'expires_at',
                        'data_access_expires_at', 'scopes')})
        result['has_connection'] = True
        expires = [token.get('expires_at'), token.get('data_access_expires_at')]
        expired = any(value and value <= now() for value in expires)
        result['status'] = 'expired' if expired else 'connected'
        scopes = token.get('scopes')
        if (not result['configured'] or token.get('app_id') != self.config['META_APP_ID'] or
                token.get('config_id') != self.config.get('META_CONFIG_ID') or
                not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes) or
                not set(REQUIRED_PERMISSIONS).issubset(scopes)):
            result['status'] = 'reconnect_required'
        result['connected'] = result['status'] == 'connected'
        return result

    def authorization_url(self, session_id):
        if not self.configured():
            raise Problem('Quản trị hệ thống cần cấu hình Meta OAuth và redirect URI hợp lệ ở backend.', 503)
        state = secrets.token_urlsafe(32)
        expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
        with self.store.connect(immediate=True) as db:
            # One pending authorization for the single client; a fresh connect cancels older attempts.
            db.execute('DELETE FROM meta_oauth_states WHERE client_id=? OR expires_at<?', (self.client_id, now()))
            db.execute('INSERT INTO meta_oauth_states (state,client_id,session_id,config_hash,expires_at) VALUES (?,?,?,?,?)',
                       (digest(state), self.client_id, session_id, self.config_hash(), expires))
        return f"https://www.facebook.com/{self.config['META_GRAPH_VERSION']}/dialog/oauth?" + urlencode({
            'client_id': self.config['META_APP_ID'], 'redirect_uri': self.config['META_REDIRECT_URI'],
            'config_id': self.config['META_CONFIG_ID'], 'response_type': 'code',
            'override_default_response_type': 'true', 'state': state})

    def call(self, method, path, *, token=None, params=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        transport = {'params': params}
        if path in ('oauth/access_token', 'debug_token'):
            # Graph's method override preserves GET semantics while keeping codes,
            # app secrets and token-exchange/debug inputs out of request URLs.
            transport = {'data': {**(params or {}), 'method': method}}
            method = 'POST'
        try:
            response = requests.request(method, f"https://graph.facebook.com/{self.config['META_GRAPH_VERSION']}/{path}",
                                        **transport, headers=headers, timeout=(3, 5), allow_redirects=False)
            if not 200 <= response.status_code < 300:
                raise SourceError('meta_oauth_error', 'Meta chưa xác nhận yêu cầu. Hãy kết nối lại hoặc thử lại sau.')
            value = response.json()
        except (requests.RequestException, ValueError):
            raise SourceError('meta_oauth_error', 'Không thể xác nhận kết nối Meta. Vui lòng thử lại.') from None
        if not isinstance(value, dict) or 'error' in value:
            raise SourceError('meta_oauth_error', 'Meta trả về phản hồi không hợp lệ. Vui lòng thử lại.')
        return value

    def proof(self, token):
        return hmac.new(self.config['META_APP_SECRET'].encode(), token.encode(), hashlib.sha256).hexdigest()

    def callback(self, state, code, session_id, error=''):
        state_hash = digest(state)
        with self.store.connect(immediate=True) as db:
            claimed = db.execute('''UPDATE meta_oauth_states SET consumed=1
                WHERE state=? AND client_id=? AND session_id=? AND config_hash=? AND expires_at>? AND consumed=0''',
                (state_hash, self.client_id, session_id, self.config_hash(), now())).rowcount
            if not claimed:
                raise Problem('Phiên kết nối Meta đã hết hạn hoặc không hợp lệ.', 400)
        try:
            # A denied callback must also validate and consume state; never reflect provider error text.
            if error:
                return 'denied' if error == 'access_denied' else 'failed'
            if not code or not self.configured():
                raise Problem('Thiếu mã cấp quyền hoặc cấu hình Meta không hợp lệ.', 400)
            client = {'client_id': self.config['META_APP_ID'], 'client_secret': self.config['META_APP_SECRET']}
            short = self.call('GET', 'oauth/access_token', params={**client, 'code': code,
                              'redirect_uri': self.config['META_REDIRECT_URI']})
            if not isinstance(short.get('access_token'), str) or not short['access_token']:
                raise Problem('Meta chưa cấp access token.', 502)
            long = self.call('GET', 'oauth/access_token', params={**client, 'grant_type': 'fb_exchange_token',
                             'fb_exchange_token': short['access_token']})
            access_token = long.get('access_token')
            if not isinstance(access_token, str) or not access_token:
                raise Problem('Meta chưa cấp access token dài hạn.', 502)
            metadata = self.call('GET', 'debug_token', token=client['client_id'] + '|' + client['client_secret'],
                                 params={'input_token': access_token}).get('data')
            if (not isinstance(metadata, dict) or metadata.get('is_valid') is not True or
                    metadata.get('app_id') != client['client_id'] or metadata.get('type') != 'USER' or
                    not isinstance(metadata.get('user_id'), str) or not metadata['user_id']):
                raise Problem('Meta không xác nhận token thuộc ứng dụng và tài khoản này.', 502)
            expires_at = self.expiration(metadata.get('expires_at'), required=True)
            data_expires_at = self.expiration(metadata.get('data_access_expires_at'))
            scopes = metadata.get('scopes')
            if (not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes) or
                    not set(REQUIRED_PERMISSIONS).issubset(scopes)):
                raise Problem('Meta chưa xác nhận đủ quyền đọc yêu cầu. Hãy kiểm tra cấu hình đăng nhập Meta.', 502)
            profile = self.call('GET', 'me', token=access_token,
                                params={'fields': 'id,name', 'appsecret_proof': self.proof(access_token)})
            if profile.get('id') != metadata['user_id'] or not isinstance(profile.get('name'), str):
                raise Problem('Meta không xác nhận danh tính tài khoản.', 502)
            token = {'access_token': access_token, 'app_id': client['client_id'], 'client_id': self.client_id,
                     'config_id': self.config['META_CONFIG_ID'],
                     'account_id': profile['id'], 'account_name': profile['name'], 'connected_at': now(),
                     'expires_at': expires_at, 'data_access_expires_at': data_expires_at, 'scopes': scopes}
            with self.store.connect(immediate=True) as db:
                # Disconnect/new connect may have cancelled this attempt during provider requests.
                valid = db.execute('''DELETE FROM meta_oauth_states
                    WHERE state=? AND consumed=1 AND expires_at>?''', (state_hash, now())).rowcount
                admin = db.execute('''SELECT users.id FROM sessions JOIN users ON users.id=sessions.user_id
                    WHERE sessions.id=? AND sessions.expires_at>? AND users.active=1 AND users.role='admin' ''',
                    (session_id, now())).fetchone()
                if not valid or not admin:
                    raise Problem('Phiên kết nối Meta đã bị hủy. Hãy kết nối lại.', 400)
                db.execute('INSERT INTO secrets (name,value) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
                           (self.secret_name, self.cipher.encrypt(pack(token).encode())))
                self.clear_connections(db)
                self.platform.upsert_connection(client_id=self.client_id, provider='meta',
                    external_account_id=profile['id'], account_name=profile['name'], secret_name=self.secret_name, db=db)
            return 'success'
        finally:
            self.store.execute('DELETE FROM meta_oauth_states WHERE state=?', (state_hash,))

    @staticmethod
    def expiration(value, required=False):
        if not required and (value is None or value == 0):
            return None
        try:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError
            expiry = datetime.fromtimestamp(value, timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                raise ValueError
            return expiry.isoformat()
        except (ValueError, OverflowError, OSError):
            raise Problem('Thời hạn token Meta không hợp lệ. Hãy kết nối lại.', 502) from None

    def clear_connections(self, db):
        db.execute("UPDATE connections SET status='disconnected',secret_name=NULL,updated_at=? WHERE client_id=? AND provider='meta'",
                   (now(), self.client_id))

    def disconnect(self):
        # Serialize with callback/connect across processes, including provider revocation, so a
        # replacement grant cannot be revoked by an older disconnect. Network timeouts are bounded.
        with self.store.connect(immediate=True) as db:
            revoked = True
            record = db.execute('SELECT value FROM secrets WHERE name=?', (self.secret_name,)).fetchone()
            if record:
                try:
                    token = json.loads(self.cipher.decrypt(bytes(record['value'])))
                    revoked = False
                    if self.configured() and token['app_id'] == self.config['META_APP_ID']:
                        result = self.call('DELETE', 'me/permissions', token=token['access_token'],
                                           params={'appsecret_proof': self.proof(token['access_token'])})
                        revoked = result.get('success') is True
                except (SourceError, InvalidToken, ValueError, TypeError, KeyError):
                    revoked = False
            db.execute('DELETE FROM meta_oauth_states WHERE client_id=?', (self.client_id,))
            db.execute('DELETE FROM secrets WHERE name=?', (self.secret_name,))
            self.clear_connections(db)
        return revoked
