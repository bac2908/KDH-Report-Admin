import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .core import TYPES, TZ, GOOD, allowed, filters, Problem, digest, now, pack, uid
from .google import source_result, REQUEST_DEADLINE
from .reports import gmb_data, valid_dataset, save_report, publish, excel_bytes


def enqueue(store, actor, kind, params, parent=None):
    fingerprint = digest(pack([actor, kind, params]))
    job_id = uid()
    with store.connect(immediate=True) as db:
        row = db.execute("SELECT id FROM jobs WHERE active_key=? AND status IN ('queued','running')", (fingerprint,)).fetchone()
        if row:
            return row['id'], False
        db.execute('INSERT INTO jobs (id,kind,user_id,params,status,active_key,created_at,parent_id) VALUES (?,?,?,?,?,?,?,?)',
                   (job_id, kind, actor, pack(params), 'queued', fingerprint, now(), parent))
    return job_id, True


def job_view(row):
    result = dict(row)
    result['params'] = json.loads(result['params'])
    result['steps'] = json.loads(result['steps'])
    result.pop('active_key', None)
    return result


def next_run(schedule, after=None):
    local = (after or datetime.now(timezone.utc)).astimezone(ZoneInfo(TZ))
    hour, minute = map(int, schedule['run_time'].split(':'))
    for i in range(370):
        candidate = (local + timedelta(days=i)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local:
            continue
        if schedule['frequency'] == 'weekly' and candidate.weekday() != schedule['weekday']:
            continue
        if schedule['frequency'] == 'monthly' and candidate.day != schedule['monthday']:
            continue
        return candidate.astimezone(timezone.utc).isoformat(timespec='seconds')
    raise Problem('Không thể tính lần chạy tiếp theo.')


def period_dates(period, at=None):
    today = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo(TZ)).date()
    if period == 'previous_month':
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    else:
        end = today - timedelta(days=1)
        start = end - timedelta(days=6 if period == 'last7' else 27)
    return start.isoformat(), end.isoformat()


class Worker:
    """Durable queue, claimed atomically by the worker or an explicit request."""
    def __init__(self, store, google):
        self.store, self.google = store, google
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        if self.google.config.get('JOB_MODE') == 'request':
            return
        if not self.store.postgres:
            self.store.execute("UPDATE jobs SET status='interrupted', finished_at=?, error=? WHERE status='running'",
                               (now(), 'Ứng dụng đã khởi động lại trong lúc chạy. Bạn có thể thử lại tác vụ.'))
        self.thread = threading.Thread(target=self.loop, name='kdh-worker', daemon=True)
        self.thread.start()

    def loop(self):
        while not self.stopping.is_set():
            try:
                self.tick_schedules()
                self.run_one()
            except Exception:
                # Queue errors are retried on the next tick; job errors are persisted in run_one.
                pass
            self.stopping.wait(1)

    def tick_schedules(self):
        with self.store.connect(immediate=True) as db:
            for schedule in db.execute('SELECT * FROM schedules WHERE enabled=1 AND next_run<=?', (now(),)).fetchall():
                user = db.execute('SELECT * FROM users WHERE id=? AND active=1', (schedule['user_id'],)).fetchone()
                params = json.loads(schedule['params'])
                if not user or user['role'] != 'admin' or not allowed(user, params['report_type']):
                    db.execute('UPDATE schedules SET enabled=0 WHERE id=?', (schedule['id'],))
                    continue
                # Don't overlap successive occurrences of the same schedule.
                active = db.execute("SELECT id FROM jobs WHERE id=? AND status IN ('queued','running')", (schedule['last_job'],)).fetchone()
                if active:
                    continue
                start, end = period_dates(schedule['period'])
                params = filters({**params, 'start': start, 'end': end})
                params.update(save_report=True, auto_publish=bool(schedule['publish']), schedule_id=schedule['id'])
                job_id = uid()
                db.execute('INSERT INTO jobs (id,kind,user_id,params,status,active_key,created_at) VALUES (?,?,?,?,?,?,?)',
                           (job_id, 'analysis', schedule['user_id'], pack(params), 'queued', digest(pack([schedule['id'], start, end])), now()))
                db.execute('UPDATE schedules SET last_run=?,last_job=?,next_run=? WHERE id=?',
                           (now(), job_id, next_run(schedule), schedule['id']))

    def expire_stale(self):
        if self.google.config.get('JOB_MODE') != 'request':
            return
        # Allow a grace period beyond the request's 220s processing budget.
        # Another instance must not interrupt an active request.
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat(timespec='microseconds')
        self.store.execute("UPDATE jobs SET status='interrupted',finished_at=?,error=? WHERE status='running' AND started_at<?",
                           (now(), 'Lần chạy bị gián đoạn hoặc quá thời gian máy chủ. Bấm Thử lại để chạy lại.', cutoff))

    def run_one(self, job_id=None, deadline=None):
        self.expire_stale()
        with self.store.connect(immediate=True) as db:
            query = "SELECT * FROM jobs WHERE status='queued'"
            job = db.execute(query + (' AND id=?' if job_id else '') + ' ORDER BY created_at,id LIMIT 1',
                             (job_id,) if job_id else ()).fetchone()
            if not job:
                return False
            job = dict(job)
            db.execute("UPDATE jobs SET status='running',started_at=? WHERE id=?", (now(), job['id']))
        if deadline is None and self.google.config.get('JOB_MODE') == 'request':
            deadline = time.monotonic() + 220
        token = REQUEST_DEADLINE.set(deadline)
        try:
            self.perform(job)
        except Problem as exc:
            self.store.execute("UPDATE jobs SET status='failed',finished_at=?,error=? WHERE id=?",
                               (now(), exc.message, job['id']))
        except Exception:
            self.store.execute("UPDATE jobs SET status='failed',finished_at=?,error=? WHERE id=?",
                               (now(), 'Tác vụ không hoàn tất. Kết quả cũ vẫn được giữ. Kiểm tra nguồn và thử lại.', job['id']))
        finally:
            REQUEST_DEADLINE.reset(token)
        return True

    def perform(self, job):
        p = json.loads(job['params'])
        if p.get('demo') and (job['kind'] == 'connection' or not self.store.setting('demo_pack')):
            raise Problem('Dữ liệu demo chưa được bật cho tác vụ này.')
        user = self.store.one('SELECT * FROM users WHERE id=? AND active=1', (job['user_id'],))
        if not user or not allowed(user, p['report_type']) or (job['kind'] == 'connection' and user['role'] != 'admin'):
            raise Problem('Người thực hiện không còn quyền chạy tác vụ.')
        if p.get('save_report') and user['role'] == 'viewer':
            raise Problem('Không còn quyền lưu báo cáo.')
        if job['kind'] == 'export':
            row = self.store.one('SELECT data FROM datasets WHERE id=?', (p['dataset_id'],))
            if not row:
                raise Problem('Không tìm thấy kết quả báo cáo.')
            content = excel_bytes(json.loads(row['data']))
            self.store.save_artifact(job['id'], content)
            self.store.execute("UPDATE jobs SET status='succeeded',finished_at=?,dataset_id=? WHERE id=?", (now(), p['dataset_id'], job['id']))
            return
        sources, steps = {}, []
        for name in TYPES[p['report_type']][1]:
            steps.append({'source': name, 'status': 'running', 'started_at': now()})
            self.store.execute('UPDATE jobs SET steps=? WHERE id=?', (pack(steps), job['id']))
            fetch = (lambda: gmb_data(self.store, p)) if name == 'gmb' else (lambda n=name: self.google.fetch(n, p))
            if p.get('demo') and name != 'gmb':
                from .demo import demo_source
                fetch = lambda n=name: demo_source(n, p)
            result = source_result(name, p, fetch)
            sources[name] = result
            steps[-1].update(status=result['status'], finished_at=now(), error=result.get('error'), warnings=result.get('warnings'))
            self.store.execute('UPDATE jobs SET steps=? WHERE id=?', (pack(steps), job['id']))
        status = 'succeeded' if all(s['status'] in GOOD for s in sources.values()) else ('partial' if any(s['status'] in GOOD for s in sources.values()) else 'failed')
        dataset_id = None
        if job['kind'] == 'connection':
            self.store.set_setting('google_sources', {k: {f: v.get(f) for f in ('source','label','status','error','requested_start','requested_end','latest_available_date','fetched_at','warnings')} for k, v in sources.items()})
            self.store.set_setting('google_checked_at', now())
        else:
            dataset_id = uid()
            dataset = {'id': dataset_id, 'params': p, 'created_at': now(), 'sources': sources,
                       'organization': self.store.setting('organization', {'name':'KinderHealth','author':''})}
            self.store.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?)',
                               (dataset_id, job['user_id'], p['report_type'], dataset['created_at'], int(valid_dataset(dataset)), pack(dataset)))
            if p.get('save_report') and valid_dataset(dataset):
                report_id = save_report(self.store, job['user_id'], dataset)
                if p.get('auto_publish'):
                    publish(self.store, job['user_id'], report_id)
        self.store.execute('UPDATE jobs SET status=?,finished_at=?,dataset_id=? WHERE id=?', (status, now(), dataset_id, job['id']))
