import hashlib

import json

import os

import secrets

import sqlite3

from contextlib import contextmanager

from datetime import date, datetime, timedelta, timezone

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TZ = 'Asia/Ho_Chi_Minh'

TYPES = {

    'seo': ('Website Traffic & SEO', ['ga4', 'gsc', 'keywords']),

    'ga4': ('Google Analytics 4', ['ga4']),

    'gsc': ('Google Search Console', ['gsc']),

    'keywords': ('Keyword Tracking', ['keywords']),

    'gmb': ('Google Business Profile', ['gmb']),

    'facebook-ads': ('Facebook Ads', []),

    'facebook-content': ('Facebook Content 7 ngày', []),

    'facebook-content-30d': ('Facebook Content 30 ngày', []),

    'facebook-content-6m': ('Facebook Content 6 tháng', []),

    'tiktok': ('TikTok Ads', []),

}

GOOD = {'ready', 'delayed'}

class Problem(Exception):

    def __init__(self, message, status=400, code='invalid'):

        self.message = message

        self.status = status

        self.code = code

        super().__init__(message)

def now():

    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def uid():

    return secrets.token_hex(16)

def pack(value):

    return json.dumps(

        value,

        ensure_ascii=False,

        allow_nan=False

    )

def digest(value):

    return hashlib.sha256(value.encode()).hexdigest()

def load_config():

    """

    Load application configuration.

    Local:

        - Nếu không có DATA_DIR thì dùng:

          <project>/instance

    Vercel:

        - DATABASE_URL hoặc DATABASE_POSTGRES_URL trỏ PostgreSQL để lưu dữ liệu lâu dài.

        - DATA_DIR=/tmp/kdh chỉ dùng cho thư mục tạm.

    """

    # Environment variables luôn ưu tiên hơn file .env local.

    envfile = ROOT / '.env'

    if envfile.exists():

        for line in envfile.read_text(

            encoding='utf-8-sig'

        ).splitlines():

            if (

                line.strip()

                and not line.lstrip().startswith('#')

                and '=' in line

            ):

                key, value = line.split('=', 1)

                os.environ.setdefault(

                    key.strip(),

                    value.strip()

                    .strip('"')

                    .strip("'")

                )

    vercel = os.getenv('VERCEL') == '1'

    # Vercel Neon integration with the custom prefix `DATABASE` creates
    # DATABASE_POSTGRES_URL instead of DATABASE_URL. Prefer DATABASE_URL
    # when it exists, otherwise fall back to the Neon integration URL.
    database_url = (
        os.getenv('DATABASE_URL')
        or os.getenv('DATABASE_POSTGRES_URL')
        or ''
    ).strip()

    return {

        'VERCEL': vercel,

        'DATABASE_URL': database_url,

        'ENCRYPTION_KEY': os.getenv('ENCRYPTION_KEY', '').strip(),

        'JOB_MODE': os.getenv('JOB_MODE', 'request' if vercel else 'worker'),

        'CRON_SECRET': os.getenv('CRON_SECRET', ''),

        # Quan trọng:

        # Local -> ROOT/instance

        # Vercel -> /tmp chỉ là thư mục tạm; Store dùng DATABASE_URL.

        'DATA_DIR': os.getenv(

            'DATA_DIR',

            '/tmp/kdh' if vercel else str(ROOT / 'instance')

        ),

        'APP_URL': os.getenv(

            'APP_URL',

            'http://127.0.0.1:8090'

        ).rstrip('/'),

        'COOKIE_SECURE': (

            os.getenv('COOKIE_SECURE', '1' if vercel else '0') == '1'

        ),

        'INITIAL_ADMIN_EMAIL': os.getenv(

            'INITIAL_ADMIN_EMAIL',

            ''

        ).strip(),

        'INITIAL_ADMIN_PASSWORD': os.getenv(

            'INITIAL_ADMIN_PASSWORD',

            ''

        ),

        'GOOGLE_CLIENT_ID': os.getenv(

            'GOOGLE_CLIENT_ID',

            ''

        ),

        'GOOGLE_CLIENT_SECRET': os.getenv(

            'GOOGLE_CLIENT_SECRET',

            ''

        ),

        'GOOGLE_REDIRECT_URI': os.getenv(

            'GOOGLE_REDIRECT_URI',

            'http://127.0.0.1:8090/api/google/callback'

        ),

        'GA4_PROPERTY_ID': os.getenv(

            'GA4_PROPERTY_ID',

            '484358741'

        ),

        'GSC_PROPERTY': os.getenv(

            'GSC_PROPERTY',

            'https://kinderhealth.vn/'

        ),

        'KEYWORD_SPREADSHEET_ID': os.getenv(

            'KEYWORD_SPREADSHEET_ID',

            '1oVC_gc-_878btw6GJ9gQSDHJ7sqiGu2QB-lqMArqbSo'

        ),

        'KEYWORD_SHEET': os.getenv(

            'KEYWORD_SHEET',

            'Ranking'

        ),

        'KEYWORD_TRACKING_YEAR': os.getenv(

            'KEYWORD_TRACKING_YEAR',

            ''

        ),

        'LEGACY_REPORT_DIR': os.getenv(

            'LEGACY_REPORT_DIR',

            str(

                ROOT.parent

                / 'KDH-Report'

                / 'KDH-Report'

            )

        ),

        'DASHBOARD_URL': os.getenv(

            'DASHBOARD_URL',

            'http://127.0.0.1:8088'

        ),

        'MAX_CONTENT_LENGTH': 4 * 1024 * 1024 if vercel else 5 * 1024 * 1024,

        'TESTING': False,

    }

SCHEMA = """

PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (

    id TEXT PRIMARY KEY,

    email TEXT UNIQUE NOT NULL,

    name TEXT NOT NULL,

    password TEXT NOT NULL,

    role TEXT NOT NULL

        CHECK(role IN ('admin','operator','viewer')),

    allowed TEXT NOT NULL DEFAULT '[]',

    active INTEGER NOT NULL DEFAULT 1,

    created_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS sessions (

    id TEXT PRIMARY KEY,

    user_id TEXT REFERENCES users(id),

    csrf TEXT NOT NULL,

    expires_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS attempts (

    key TEXT PRIMARY KEY,

    count INTEGER NOT NULL,

    until_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS oauth_states (

    state TEXT PRIMARY KEY,

    session_id TEXT NOT NULL,

    verifier TEXT NOT NULL,

    expires_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS secrets (

    name TEXT PRIMARY KEY,

    value BLOB NOT NULL

);

CREATE TABLE IF NOT EXISTS settings (

    key TEXT PRIMARY KEY,

    value TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS jobs (

    id TEXT PRIMARY KEY,

    kind TEXT NOT NULL,

    user_id TEXT REFERENCES users(id),

    params TEXT NOT NULL,

    status TEXT NOT NULL,

    active_key TEXT NOT NULL,

    created_at TEXT NOT NULL,

    started_at TEXT,

    finished_at TEXT,

    steps TEXT NOT NULL DEFAULT '[]',

    error TEXT,

    dataset_id TEXT,

    parent_id TEXT

);

CREATE UNIQUE INDEX IF NOT EXISTS unique_active_job

ON jobs(active_key)

WHERE status IN ('queued','running');

CREATE TABLE IF NOT EXISTS artifacts (

    job_id TEXT PRIMARY KEY REFERENCES jobs(id),

    content BLOB NOT NULL

);

CREATE TABLE IF NOT EXISTS datasets (

    id TEXT PRIMARY KEY,

    user_id TEXT REFERENCES users(id),

    report_type TEXT NOT NULL,

    created_at TEXT NOT NULL,

    valid INTEGER NOT NULL,

    data TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS reports (

    id TEXT PRIMARY KEY,

    report_type TEXT NOT NULL,

    name TEXT NOT NULL,

    version INTEGER NOT NULL,

    dataset_id TEXT REFERENCES datasets(id),

    user_id TEXT REFERENCES users(id),

    created_at TEXT NOT NULL,

    start_date TEXT,

    end_date TEXT,

    valid INTEGER NOT NULL,

    origin TEXT NOT NULL,

    content_hash TEXT NOT NULL,

    html TEXT NOT NULL,

    UNIQUE(report_type, version),

    UNIQUE(report_type, content_hash)

);

CREATE TABLE IF NOT EXISTS publications (

    report_type TEXT PRIMARY KEY,

    report_id TEXT REFERENCES reports(id),

    published_at TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS uploads (

    id TEXT PRIMARY KEY,

    name TEXT NOT NULL,

    sha256 TEXT UNIQUE NOT NULL,

    user_id TEXT REFERENCES users(id),

    start_date TEXT NOT NULL,

    end_date TEXT NOT NULL,

    created_at TEXT NOT NULL,

    data TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS upload_locations (

    upload_id TEXT REFERENCES uploads(id),

    location TEXT NOT NULL,

    start_date TEXT NOT NULL,

    end_date TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS events (

    id TEXT PRIMARY KEY,

    user_id TEXT REFERENCES users(id),

    action TEXT NOT NULL,

    at TEXT NOT NULL,

    detail TEXT NOT NULL

);

CREATE TABLE IF NOT EXISTS schedules (

    id TEXT PRIMARY KEY,

    name TEXT NOT NULL,

    user_id TEXT REFERENCES users(id),

    params TEXT NOT NULL,

    frequency TEXT NOT NULL,

    run_time TEXT NOT NULL,

    weekday INTEGER NOT NULL DEFAULT 0,

    monthday INTEGER NOT NULL DEFAULT 1,

    period TEXT NOT NULL,

    publish INTEGER NOT NULL DEFAULT 0,

    enabled INTEGER NOT NULL DEFAULT 1,

    next_run TEXT NOT NULL,

    last_run TEXT,

    last_job TEXT

);

"""

class Store:

    def __init__(self, folder, database_url=''):

        self.database_url = database_url

        self.postgres = bool(database_url)

        self.folder = Path(folder)

        self.folder.mkdir(

            parents=True,

            exist_ok=True

        )

        self.path = self.folder / 'kdh.sqlite3'

        with self.connect(immediate=self.postgres) as db:

            db.executescript(SCHEMA)

    @contextmanager

    def connect(self, immediate=False):

        if self.postgres:

            from .postgres import connect

            with connect(self.database_url, immediate) as db:

                yield db

            return

        db = sqlite3.connect(

            self.path,

            timeout=30

        )

        db.row_factory = sqlite3.Row

        db.execute(

            'PRAGMA foreign_keys=ON'

        )

        try:

            if immediate:

                db.execute(

                    'BEGIN IMMEDIATE'

                )

            yield db

            db.commit()

        except Exception:

            db.rollback()

            raise

        finally:

            db.close()

    def all(self, sql, args=()):

        with self.connect() as db:

            rows = db.execute(

                sql,

                args

            ).fetchall()

            return [

                dict(row)

                for row in rows

            ]

    def one(self, sql, args=()):

        rows = self.all(

            sql,

            args

        )

        return rows[0] if rows else None

    def execute(self, sql, args=()):

        with self.connect() as db:

            result = db.execute(

                sql,

                args

            )

            return result.rowcount

    def event(

        self,

        user,

        action,

        detail=None

    ):

        self.execute(

            'INSERT INTO events VALUES (?,?,?,?,?)',

            (

                uid(),

                user,

                action,

                now(),

                pack(detail or {})

            )

        )

    def setting(

        self,

        key,

        default=None

    ):

        row = self.one(

            'SELECT value FROM settings WHERE key=?',

            (key,)

        )

        if not row:

            return default

        return json.loads(

            row['value']

        )

    def set_setting(

        self,

        key,

        value

    ):

        self.execute(

            'INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',

            (

                key,

                pack(value)

            )

        )

    def save_artifact(self, job_id, content):

        # Keep small Excel files alongside their durable job/dataset records.

        if self.postgres and len(content) > 4 * 1024 * 1024:

            raise Problem('File Excel vượt 4 MB. Hãy chọn khoảng ngày ngắn hơn để tải trên Vercel.')

        self.execute('INSERT INTO artifacts VALUES (?,?) ON CONFLICT(job_id) DO UPDATE SET content=excluded.content',

                     (job_id, content))

    def artifact(self, job_id):

        row = self.one('SELECT content FROM artifacts WHERE job_id=?', (job_id,))

        if row:

            return bytes(row['content'])

        # Backward compatibility for exports created by older Docker versions.

        path = self.folder / 'exports' / (job_id + '.xlsx')

        return path.read_bytes() if path.is_file() else None

def parse_day(value):

    try:

        if (

            not isinstance(value, str)

            or len(value) != 10

        ):

            raise ValueError()

        return date.fromisoformat(

            value

        )

    except (ValueError, TypeError):

        raise Problem(

            'Ngày không hợp lệ. Dùng định dạng YYYY-MM-DD.'

        )

def filters(data):

    from zoneinfo import ZoneInfo

    report_type = data.get(

        'report_type',

        'seo'

    )

    if (

        report_type not in TYPES

        or not TYPES[report_type][1]

    ):

        raise Problem(

            'Loại báo cáo này hiện chỉ hỗ trợ xem bản HTML đã lưu.'

        )

    start = parse_day(

        data.get('start')

    )

    end = parse_day(

        data.get('end')

    )

    if start > end:

        raise Problem(

            'Từ ngày phải trước hoặc bằng Đến ngày.'

        )

    if (end - start).days > 365:

        raise Problem(

            'Mỗi lần phân tích tối đa 366 ngày.'

        )

    if end > datetime.now(

        ZoneInfo(TZ)

    ).date():

        raise Problem(

            'Không thể lấy dữ liệu cho ngày trong tương lai.'

        )

    compare = data.get(

        'compare',

        False

    )

    if not isinstance(

        compare,

        bool

    ):

        raise Problem(

            'Tùy chọn so sánh không hợp lệ.'

        )

    if not isinstance(

        data.get('demo', False),

        bool

    ):

        raise Problem(

            'Tùy chọn dữ liệu demo không hợp lệ.'

        )

    result = {

        'report_type': report_type,

        'start': start.isoformat(),

        'end': end.isoformat(),

        'compare': compare,

        'search_type': 'web',

        'exclude_products': bool(

            data.get(

                'exclude_products',

                False

            )

        )

    }

    if data.get('demo'):

        result['demo'] = True

    if compare:

        prev_end = start - timedelta(

            days=1

        )

        result.update(

            previous_start=(

                prev_end - (end - start)

            ).isoformat(),

            previous_end=prev_end.isoformat()

        )

    if report_type == 'gmb':

        result['upload_id'] = str(

            data.get(

                'upload_id',

                ''

            )

        )

        result['previous_upload_id'] = (

            str(

                data.get(

                    'previous_upload_id',

                    ''

                )

            )

            if compare

            else ''

        )

        if not result['upload_id']:

            raise Problem(

                'Chọn file CSV cho kỳ báo cáo.'

            )

    return result

def allowed(

    user,

    report_type

):

    return (

        user['role'] == 'admin'

        or report_type

        in json.loads(

            user['allowed']

        )

    )

def public_user(user):

    return {

        key: (

            json.loads(user[key])

            if key == 'allowed'

            else user[key]

        )

        for key in (

            'id',

            'email',

            'name',

            'role',

            'allowed',

            'active'

        )

    }
