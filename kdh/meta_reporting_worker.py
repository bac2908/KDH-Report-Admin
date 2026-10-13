"""Execute one queued Meta sync with atomic normalized-data persistence."""

import json
import os

from .core import Problem, digest, now, pack, uid
from .meta_reporting import MetaReportingReader, SOURCES, validate_range
from .platform_data import PlatformData, DEFAULT_CLIENT_ID, _stable_metric_id, _validate_snapshot_payload


class MetaReportingWorker:
    def __init__(self, store, meta):
        self.store, self.meta = store, meta
        self.platform = PlatformData(store)

    def _step(self, job_id, source, status, count=0, message=None):
        step = {'source': source, 'status': status, 'record_count': count}
        if message:
            step['error'] = message
        self.store.execute('UPDATE jobs SET steps=? WHERE id=?', (pack([step]), job_id))

    def _save_metric(self, db, *, asset_id, source, sync_id, entity_type, row,
                     entity_id='', dimensions=None):
        day = row['date']
        metric_id = _stable_metric_id(asset_id, entity_type, entity_id, day, '')
        measures = {k: v for k, v in row.items() if k not in
                    ('date', 'campaign_id', 'campaign_name', 'post_id')}
        db.execute('''INSERT INTO daily_metrics
            (id,client_id,asset_id,provider,entity_type,entity_id,metric_date,dimension_key,
             dimensions,metrics,source_hash,sync_run_id,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(asset_id,entity_type,entity_id,metric_date,dimension_key)
            DO UPDATE SET metrics=excluded.metrics,dimensions=excluded.dimensions,
               source_hash=excluded.source_hash,sync_run_id=excluded.sync_run_id,
               fetched_at=excluded.fetched_at''',
            (metric_id, self.meta.client_id, asset_id, 'meta', entity_type, entity_id, day,
             '', pack(dimensions or {}), pack(measures), digest(pack(row)), sync_id, now()))

    def _persist(self, sync_id, job, source, asset, connection_id, result, start, end):
        # Source snapshot + normalized rows + sync status are committed together;
        # a failed attempt cannot overwrite previously successful metrics.
        _validate_snapshot_payload(result)
        n = len(result['daily']) + len(result['entries'])
        with self.store.connect(immediate=True) as db:
            entity_type = 'ad_account' if source == 'facebook_ads' else 'page'
            for row in result['daily']:
                self._save_metric(db, asset_id=asset['id'], source=source, sync_id=sync_id,
                                  entity_type=entity_type, row=row)
            for row in result['entries']:
                item_id = row.get('campaign_id') if source == 'facebook_ads' else row.get('post_id')
                if not item_id:
                    continue
                dimensions = ({'campaign_name': row.get('campaign_name', '')}
                              if source == 'facebook_ads' else {})
                self._save_metric(db, asset_id=asset['id'], source=source, sync_id=sync_id,
                    entity_type='campaign' if source == 'facebook_ads' else 'post',
                    entity_id=item_id, dimensions=dimensions, row=row)
            stamp = now()
            db.execute('''INSERT INTO source_snapshots
                (id,sync_run_id,client_id,asset_id,provider,source_key,
                 requested_start,requested_end,payload,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (uid(), sync_id, self.meta.client_id, asset['id'], 'meta', source,
                 start, end, pack(result), stamp))
            db.execute('''UPDATE sync_runs SET status='succeeded',latest_available_date=?,
                record_count=?,finished_at=?,fetched_at=?,warnings=? WHERE id=?''',
                (result['latest_available_date'], n, stamp, stamp,
                 pack(result.get('warnings', [])), sync_id))
            db.execute('UPDATE connections SET last_sync_at=?,updated_at=? WHERE id=?',
                       (stamp, stamp, connection_id))
            if result['latest_available_date']:
                db.execute('''INSERT INTO sync_watermarks
                    (asset_id,last_complete_date,last_attempt_at,lookback_days,updated_at)
                    VALUES (?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET
                    last_complete_date=excluded.last_complete_date,
                    last_attempt_at=excluded.last_attempt_at,updated_at=excluded.updated_at''',
                    (asset['id'], result['latest_available_date'], stamp, 3, stamp))
            step = [{'source': source, 'status': 'succeeded' if n else 'no_data', 'record_count': n}]
            db.execute("UPDATE jobs SET status='succeeded',finished_at=?,error=NULL,steps=? WHERE id=?",
                       (stamp, pack(step), job['id']))
        return n

    def run(self, job):
        if self.meta and self.meta.client_id == DEFAULT_CLIENT_ID and os.getenv('META_REPORTING_ALLOW_PRIMARY_CLIENT') != '1':
            raise Problem('Meta Reporting trên client chính chưa được bật để bảo vệ dữ liệu.')
        if self.meta is None:
            raise Problem('Worker chưa được cấu hình Meta.', 503)
        params = json.loads(job['params'])
        source, asset_id = params.get('source'), params.get('asset_id')
        if source not in SOURCES or not isinstance(asset_id, str) or params.get('demo') is not False:
            raise Problem('Tác vụ Meta không hợp lệ.')
        start, end = params.get('start'), params.get('end')
        validate_range(start, end)
        expected_report = 'facebook-ads' if source == 'facebook_ads' else 'facebook-content'
        if params.get('report_type') != expected_report:
            raise Problem('Loại báo cáo không khớp nguồn Meta.')
        actor = self.store.one('SELECT role,active FROM users WHERE id=?', (job['user_id'],))
        if not actor or actor['role'] != 'admin' or not actor['active']:
            raise Problem('Người yêu cầu không còn quyền đồng bộ Meta.', 403)
        if not self.meta.info()['connected']:
            raise Problem('Meta OAuth chưa kết nối hoặc đã hết hạn.', 409)
        token = self.meta.read() or {}
        conn = self.store.one('''SELECT id FROM connections WHERE client_id=? AND provider='meta'
            AND external_account_id=? AND status='connected' ORDER BY created_at DESC LIMIT 1''',
            (self.meta.client_id, token.get('account_id')))
        if not conn:
            raise Problem('Không tìm thấy kết nối Meta phù hợp.', 409)
        asset = self.store.one('''SELECT * FROM source_assets WHERE id=? AND client_id=?
            AND provider='meta' AND connection_id=? AND asset_type=? AND enabled=1''',
            (asset_id, self.meta.client_id, conn['id'], SOURCES[source][0]))
        if not asset:
            raise Problem('Tài sản Meta không còn khả dụng.', 403)
        self._step(job['id'], source, 'running')
        sync_id = self.platform.start_sync(client_id=self.meta.client_id, provider='meta',
            sync_type='manual', requested_start=start, requested_end=end,
            connection_id=conn['id'], asset_id=asset_id, job_id=job['id'])
        try:
            reader = MetaReportingReader(self.meta)
            result = (reader.ads(asset['external_id'], start, end) if source == 'facebook_ads'
                      else reader.content(asset['external_id'], start, end))
            self._persist(sync_id, job, source, asset, conn['id'], result, start, end)
        except Exception:
            self.platform.finish_sync(sync_id, status='failed', record_count=0,
                error_code='meta_read_or_persistence_error',
                error_message='Meta không trả đủ dữ liệu hoặc không lưu được. Kiểm tra quyền và thử lại.')
            self._step(job['id'], source, 'failed', message='Meta không đồng bộ được; xem trạng thái nguồn.')
            raise
