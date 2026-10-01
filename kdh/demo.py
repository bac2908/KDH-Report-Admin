"""Explicit, deterministic demo data. Never called as an API-error fallback."""
import csv
import io
import json
import math
from datetime import date, datetime, timedelta, timezone

from .core import TYPES, TZ, Problem, digest, filters, now, pack, uid
from .google import source_result
from .reports import GMB_COLS, NATIVE_METRICS, excel_bytes, render_report

NOTICE = 'DEMO · Số liệu mô phỏng để trình diễn, không phải dữ liệu kinh doanh thực tế.'
KEYWORDS = [f'{topic}{suffix}' for topic in (
    'phòng khám nhi', 'khám dinh dưỡng cho bé', 'tiêm chủng cho trẻ', 'khám tổng quát trẻ em',
    'bác sĩ nhi', 'trẻ biếng ăn', 'chăm sóc trẻ sơ sinh', 'tư vấn dinh dưỡng',
    'lịch tiêm phòng', 'khám hô hấp cho bé', 'khám tiêu hóa trẻ em', 'theo dõi tăng trưởng',
    'kiểm tra sức khỏe cho bé', 'phòng khám ngoài giờ', 'dinh dưỡng trẻ em', 'khám nhi cuối tuần'
) for suffix in ('', ' TPHCM', ' gần đây')]


def days(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [first + timedelta(days=i) for i in range((last-first).days+1)]


def split_total(total, weights):
    values = [int(total * w / sum(weights)) for w in weights]
    values[-1] += total - sum(values)
    return values


def demo_source(source, p):
    def period(start, end, previous=False):
        daily = []
        for day in days(start, end):
            n = day.toordinal()
            volume = .86 if previous else 1
            wave = 1 + .14 * math.sin(n * .8) + .08 * math.cos(n * .31)
            if source == 'ga4':
                sessions = round((1550 + n % 31 * 13) * wave * volume)
                daily.append({'date': day.isoformat(), 'activeUsers': round(sessions * .76),
                              'sessions': sessions, 'screenPageViews': round(sessions * 2.28),
                              'engagementRate': round(.65 + .055 * math.sin(n), 4)})
            elif source == 'gsc':
                impressions = round((7200 + n % 19 * 140) * wave * volume * (.93 if p['exclude_products'] else 1))
                clicks = round(impressions * (.042 + .006 * math.sin(n * .4)))
                daily.append({'date': day.isoformat(), 'clicks': clicks, 'impressions': impressions,
                              'ctr': clicks / impressions, 'position': round(9.5 + 1.5 * math.sin(n * .21) + (1.2 if previous else 0), 2)})
        if source == 'ga4':
            sessions = sum(r['sessions'] for r in daily)
            totals = {'activeUsers': round(sum(r['activeUsers'] for r in daily) * .79), 'sessions': sessions,
                      'screenPageViews': sum(r['screenPageViews'] for r in daily),
                      'engagementRate': sum(r['engagementRate']*r['sessions'] for r in daily)/sessions}
            return daily, totals
        if source == 'gsc':
            impressions = sum(r['impressions'] for r in daily)
            clicks = sum(r['clicks'] for r in daily)
            return daily, {'clicks': clicks, 'impressions': impressions, 'ctr': clicks/impressions,
                           'position': sum(r['position']*r['impressions'] for r in daily)/impressions}
        entries = [{'keyword': keyword, 'position': 1 + (i * 7 % 43) + (4 if previous else 0),
                    'url': 'https://demo.example/nhom-dich-vu/' + str(i % 8 + 1), 'date': end}
                   for i, keyword in enumerate(KEYWORDS)]
        return entries, {f'top{n}': sum(r['position'] <= n for r in entries) for n in (5, 10, 20, 100)}

    entries, totals = period(p['start'], p['end'])
    previous_entries, previous = period(p['previous_start'], p['previous_end'], True) if p['compare'] else ([], None)
    result = {'demo': True, 'latest_available_date': p['end'], 'timezone': TZ,
              'asset': 'DEMO · ' + source.upper(), 'warnings': [NOTICE], 'totals': totals, 'previous': previous}
    if source == 'keywords':
        return {**result, 'entries': entries, 'previous_entries': previous_entries, 'previous_date': p.get('previous_end')}
    result.update(daily=entries, previous_daily=previous_entries)
    if source == 'ga4':
        result['channels'] = [dict(sessionDefaultChannelGroup=k, sessions=v) for k, v in zip(
            ['Organic Search', 'Direct', 'Paid Search', 'Organic Social', 'Referral', 'Email'],
            split_total(totals['sessions'], [48, 22, 14, 9, 5, 2]))]
        result['pages'] = [dict(pagePath=k, screenPageViews=v) for k, v in zip(
            ['/', '/kham-nhi/', '/dinh-duong/', '/tiem-chung/', '/bac-si/', '/kien-thuc/', '/dat-lich/'],
            split_total(totals['screenPageViews'], [25, 20, 17, 14, 10, 8, 6]))]
    else:
        impressions = split_total(totals['impressions'], [49-i for i in range(len(KEYWORDS))])
        clicks = split_total(totals['clicks'], [49-i for i in range(len(KEYWORDS))])
        result['queries'] = [{'query': keyword, 'clicks': c, 'impressions': im, 'ctr': c/im,
                              'position': round(2.1+i*.38, 2)}
                             for i, (keyword, c, im) in enumerate(zip(KEYWORDS, clicks, impressions))]
    return result


def gmb_entries(previous=False):
    return [{'location': f'DEMO-KDH-{i+1:02}', 'name': 'DEMO · ' + name,
             **{k: round(v * scale * (.84 if previous else 1)) for k, v in zip(
                 NATIVE_METRICS.values(), [8400, 2400, 6300, 1100, 320, 680, 510])}}
            for i, (name, scale) in enumerate([('Cơ sở Trung Tâm', 1), ('Cơ sở Phía Đông', .78), ('Cơ sở Phía Nam', .62)])]


def seed_demo(store, actor):
    """One atomic DB seed, idempotent across reruns. Existing records are untouched."""
    from .jobs import period_dates
    if not store.one("SELECT id FROM users WHERE id=? AND active=1 AND role='admin'", (actor,)):
        raise Problem('Cần tài khoản quản trị đang hoạt động.')
    current = store.setting('demo_pack')
    if current:
        return current
    start, end = period_dates('last28')
    base = filters({'report_type': 'seo', 'start': start, 'end': end, 'compare': True, 'demo': True})
    stamp = now()
    org = {'name': 'KinderHealth · DEMO', 'author': 'Phòng Marketing (mô phỏng)'}
    upload_ids = [uid(), uid()]
    uploads = []
    for previous, upload_id in zip((False, True), upload_ids):
        a, b = (base['previous_start'], base['previous_end']) if previous else (start, end)
        data = {'demo': True, 'start': a, 'end': b, 'entries': gmb_entries(previous)}
        csv_file = io.StringIO()
        writer = csv.DictWriter(csv_file, fieldnames=GMB_COLS)
        writer.writeheader(); writer.writerows(data['entries'])
        uploads.append((upload_id, f'DEMO_GMB_{a}_{b}.csv', digest(csv_file.getvalue()), actor, a, b, stamp, pack(data)))
    datasets = []
    for index, kind in enumerate(['seo', 'ga4', 'gsc', 'keywords', 'gmb', 'seo']):
        p = {**base, 'report_type': kind}
        if index == 5:
            p = filters({**base, 'start': base['previous_start'], 'end': base['previous_end']})
        if kind == 'gmb':
            p.update(upload_id=upload_ids[0], previous_upload_id=upload_ids[1])
            def sample_gmb():
                entries, prev = gmb_entries(), gmb_entries(True)
                def total(rows):
                    t = {m: sum(r[m] for r in rows) for m in NATIVE_METRICS.values()}
                    t['views'] = sum(t[m] for m in ('search_mobile','search_desktop','maps_mobile','maps_desktop'))
                    return t
                return {'demo': True, 'entries': entries, 'previous_entries': prev, 'totals': total(entries),
                        'previous': total(prev), 'latest_available_date': end, 'timezone': TZ,
                        'asset': 'DEMO · CSV GMB', 'warnings': [NOTICE, 'Dữ liệu tổng cho cả kỳ CSV.']}
            sources = {'gmb': source_result('gmb', p, sample_gmb)}
        else:
            sources = {k: source_result(k, p, lambda k=k: demo_source(k, p)) for k in TYPES[kind][1]}
        created = (datetime.now(timezone.utc)-timedelta(minutes=10+index*20)).isoformat()
        for source in sources.values():
            source['fetched_at'] = created
        datasets.append({'id': uid(), 'params': p, 'created_at': created, 'sources': sources, 'organization': org})
    export_id = uid()
    export_content = excel_bytes(datasets[0])
    summary = {'version': 1, 'created_at': stamp, 'dataset_id': datasets[0]['id'], 'datasets': 6,
               'reports': 6, 'uploads': 2, 'jobs': 9, 'export_job_id': export_id, 'start': start, 'end': end}
    with store.connect(immediate=True) as db:
        # Recheck under the write lock if two seed commands raced.
        existing = db.execute("SELECT value FROM settings WHERE key='demo_pack'").fetchone()
        if existing:
            return json.loads(existing['value'])
        db.executemany('INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?)', uploads)
        for row in uploads:
            data = json.loads(row[-1])
            db.executemany('INSERT INTO upload_locations VALUES (?,?,?,?)',
                           [(row[0], r['location'], data['start'], data['end']) for r in data['entries']])
        def history(kind, p, status, at, dataset_id=None, steps=None, error=None, job_id=None):
            ident = job_id or uid()
            db.execute('INSERT INTO jobs (id,kind,user_id,params,status,active_key,created_at,started_at,finished_at,steps,error,dataset_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (ident, kind, actor, pack({**p, 'simulated_history': True}), status, ident, at, at, at,
                        pack(steps or []), error, dataset_id))
        for d in datasets:
            p, at = d['params'], d['created_at']
            db.execute('INSERT INTO datasets VALUES (?,?,?,?,?,?)', (d['id'], actor, p['report_type'], at, 1, pack(d)))
            html = render_report(d, org)
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 AS version FROM reports WHERE report_type=?', (p['report_type'],)).fetchone()['version']
            db.execute('INSERT INTO reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (uid(), p['report_type'], 'DEMO · ' + TYPES[p['report_type']][0], version, d['id'], actor, at,
                        p['start'], p['end'], 1, 'demo', digest(html), html))
            history('analysis', p, 'succeeded', at, d['id'], [{'source': k, 'status': 'ready', 'warnings': [NOTICE]} for k in d['sources']])
        history('analysis', base, 'failed', (datetime.now(timezone.utc)-timedelta(minutes=8)).isoformat(),
                steps=[{'source': 'ga4', 'status': 'timeout', 'error': 'DEMO · Minh họa nguồn phản hồi quá lâu.'}],
                error='DEMO · Tình huống lỗi mô phỏng. Bấm Thử lại để chạy bộ dữ liệu demo.')
        history('analysis', base, 'interrupted', (datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat(),
                error='DEMO · Minh họa tác vụ bị gián đoạn khi máy chủ khởi động lại.')
        history('export', {**base, 'dataset_id': datasets[0]['id']}, 'succeeded', stamp, datasets[0]['id'], job_id=export_id)
        db.execute('INSERT INTO artifacts VALUES (?,?)', (export_id, export_content))
        db.execute('INSERT INTO settings VALUES (?,?)', ('demo_pack', pack(summary)))
        db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (uid(), actor, 'seed_demo', stamp, pack(summary)))
    return summary
