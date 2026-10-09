import json
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .core import (
    GOOD,
    TYPES,
    TZ,
    Problem,
    allowed,
    digest,
    filters,
    now,
    pack,
    uid,
)
from .google import REQUEST_DEADLINE, source_result
from .platform_data import DEFAULT_CLIENT_ID, PlatformData
from .reports import excel_bytes, gmb_data, publish, save_report, valid_dataset


GOOGLE_PLATFORM_SOURCES = {
    "ga4": "ga4_property",
    "gsc": "search_console_property",
    "keywords": "keyword_sheet",
}


def platform_sync_status(result):
    """Map provider/source status to the normalized sync_runs status."""
    source_status = result.get("status")

    if source_status in ("ready", "empty"):
        return "succeeded"

    if source_status in ("delayed", "incomplete"):
        return "partial"

    return "failed"


def enqueue(store, actor, kind, params, parent=None):
    fingerprint = digest(pack([actor, kind, params]))
    job_id = uid()

    with store.connect(immediate=True) as db:
        row = db.execute(
            "SELECT id FROM jobs WHERE active_key=? AND status IN ('queued','running')",
            (fingerprint,),
        ).fetchone()

        if row:
            return row["id"], False

        db.execute(
            """
            INSERT INTO jobs (
                id,kind,user_id,params,status,active_key,created_at,parent_id
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                job_id,
                kind,
                actor,
                pack(params),
                "queued",
                fingerprint,
                now(),
                parent,
            ),
        )

    return job_id, True


def job_view(row):
    result = dict(row)
    result["params"] = json.loads(result["params"])
    result["steps"] = json.loads(result["steps"])
    result.pop("active_key", None)
    return result


def next_run(schedule, after=None):
    local = (after or datetime.now(timezone.utc)).astimezone(ZoneInfo(TZ))
    hour, minute = map(int, schedule["run_time"].split(":"))

    for i in range(370):
        candidate = (local + timedelta(days=i)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )

        if candidate <= local:
            continue

        if (
            schedule["frequency"] == "weekly"
            and candidate.weekday() != schedule["weekday"]
        ):
            continue

        if (
            schedule["frequency"] == "monthly"
            and candidate.day != schedule["monthday"]
        ):
            continue

        return candidate.astimezone(timezone.utc).isoformat(timespec="seconds")

    raise Problem("Không thể tính lần chạy tiếp theo.")


def period_dates(period, at=None):
    today = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo(TZ)).date()

    if period == "previous_month":
        end = today.replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)
    else:
        end = today - timedelta(days=1)
        start = end - timedelta(days=6 if period == "last7" else 27)

    return start.isoformat(), end.isoformat()


class Worker:
    """Durable queue, claimed atomically by the worker or an explicit request."""

    def __init__(self, store, google):
        self.store = store
        self.google = google
        self.platform = PlatformData(store)
        self.stopping = threading.Event()
        self.thread = None

    def _google_platform_refs(self):
        """Use assets resolved from the current provider configuration only."""
        refs = self.google.ensure_platform_records()
        # Without a connection, source_result still records the provider's
        # disconnected status in the job/Dataset. Do not invent an account or
        # select stale assets from a previous connection to make the job run.
        return refs if refs.get("connection_id") else None

    def _sync_type(self, job, params):
        if job["kind"] == "connection":
            return "validation"

        if params.get("schedule_id"):
            return "incremental"

        return "manual"

    def _persist_google_daily_metrics(
        self,
        *,
        source,
        result,
        asset_id,
        sync_run_id,
    ):
        """Persist only real provider rows returned by Google into daily_metrics."""
        record_count = 0

        if source == "ga4":
            rows = list(result.get("daily") or [])
            rows += list(result.get("previous_daily") or [])

            for row in rows:
                metric_date = row.get("date")

                if not metric_date:
                    continue

                metrics = {
                    "active_users": row.get("activeUsers"),
                    "sessions": row.get("sessions"),
                    "page_views": row.get("screenPageViews"),
                    "engagement_rate": row.get("engagementRate"),
                }

                self.platform.upsert_daily_metric(
                    client_id=DEFAULT_CLIENT_ID,
                    asset_id=asset_id,
                    provider="google",
                    entity_type="website",
                    entity_id="",
                    metric_date=metric_date,
                    dimension_key="",
                    dimensions={},
                    metrics=metrics,
                    source_hash=digest(pack(row)),
                    sync_run_id=sync_run_id,
                )
                record_count += 1

        elif source == "gsc":
            rows = list(result.get("daily") or [])
            rows += list(result.get("previous_daily") or [])

            for row in rows:
                metric_date = row.get("date")

                if not metric_date:
                    continue

                metrics = {
                    "clicks": row.get("clicks"),
                    "impressions": row.get("impressions"),
                    "ctr": row.get("ctr"),
                    "position": row.get("position"),
                }

                self.platform.upsert_daily_metric(
                    client_id=DEFAULT_CLIENT_ID,
                    asset_id=asset_id,
                    provider="google",
                    entity_type="website",
                    entity_id="",
                    metric_date=metric_date,
                    dimension_key="",
                    dimensions={},
                    metrics=metrics,
                    source_hash=digest(pack(row)),
                    sync_run_id=sync_run_id,
                )
                record_count += 1

        elif source == "keywords":
            rows = list(result.get("entries") or [])
            rows += list(result.get("previous_entries") or [])

            for row in rows:
                metric_date = row.get("date")
                keyword = str(row.get("keyword") or "").strip()
                url = str(row.get("url") or "").strip()

                if not metric_date or not keyword:
                    continue

                self.platform.upsert_daily_metric(
                    client_id=DEFAULT_CLIENT_ID,
                    asset_id=asset_id,
                    provider="google",
                    entity_type="keyword",
                    entity_id=keyword,
                    metric_date=metric_date,
                    dimension_key=url,
                    dimensions={
                        "keyword": keyword,
                        "url": url,
                    },
                    metrics={
                        "position": row.get("position"),
                    },
                    source_hash=digest(pack(row)),
                    sync_run_id=sync_run_id,
                )
                record_count += 1

        return record_count

    def _finish_google_sync(self, *, sync_id, source, result, asset_id):
        """Persist returned rows when valid, then finalize the durable sync run."""
        sync_status = platform_sync_status(result)

        if sync_status == "failed":
            self.platform.finish_sync(
                sync_id,
                status="failed",
                latest_available_date=result.get("latest_available_date"),
                record_count=0,
                warnings=result.get("warnings", []),
                error_code=result.get("status"),
                error_message=result.get("error"),
            )
            return result

        try:
            record_count = self._persist_google_daily_metrics(
                source=source,
                result=result,
                asset_id=asset_id,
                sync_run_id=sync_id,
            )
            self.platform.save_source_snapshot(
                sync_run_id=sync_id,
                client_id=DEFAULT_CLIENT_ID,
                asset_id=asset_id,
                provider="google",
                source_key=source,
                requested_start=result.get("requested_start"),
                requested_end=result.get("requested_end"),
                payload=result,
            )
            self.platform.finish_sync(
                sync_id,
                status=sync_status,
                latest_available_date=result.get("latest_available_date"),
                record_count=record_count,
                warnings=result.get("warnings", []),
            )
        except Exception:
            self.platform.finish_sync(
                sync_id,
                status="failed",
                latest_available_date=result.get("latest_available_date"),
                record_count=0,
                warnings=result.get("warnings", []),
                error_code="persistence_error",
                error_message=(
                    "Đã lấy được dữ liệu nguồn nhưng không thể lưu vào "
                    "Data Foundation."
                ),
            )
            result["status"] = "invalid_data"
            result["error"] = (
                "Đã lấy được dữ liệu nguồn nhưng không thể lưu vào "
                "Data Foundation."
            )
            return result

        return result

    def start(self):
        if self.google.config.get("JOB_MODE") == "request":
            return

        if not self.store.postgres:
            self.store.execute(
                """
                UPDATE jobs
                SET status='interrupted', finished_at=?, error=?
                WHERE status='running'
                """,
                (
                    now(),
                    "Ứng dụng đã khởi động lại trong lúc chạy. "
                    "Bạn có thể thử lại tác vụ.",
                ),
            )

        self.thread = threading.Thread(
            target=self.loop,
            name="kdh-worker",
            daemon=True,
        )
        self.thread.start()

    def loop(self):
        while not self.stopping.is_set():
            try:
                self.tick_schedules()
                self.run_one()
            except Exception:
                # Queue errors are retried on the next tick; job errors are
                # persisted in run_one.
                pass

            self.stopping.wait(1)

    def tick_schedules(self):
        with self.store.connect(immediate=True) as db:
            schedules = db.execute(
                "SELECT * FROM schedules WHERE enabled=1 AND next_run<=?",
                (now(),),
            ).fetchall()

            for schedule in schedules:
                user = db.execute(
                    "SELECT * FROM users WHERE id=? AND active=1",
                    (schedule["user_id"],),
                ).fetchone()
                params = json.loads(schedule["params"])

                if (
                    not user
                    or user["role"] != "admin"
                    or not allowed(user, params["report_type"])
                ):
                    db.execute(
                        "UPDATE schedules SET enabled=0 WHERE id=?",
                        (schedule["id"],),
                    )
                    continue

                active = db.execute(
                    """
                    SELECT id
                    FROM jobs
                    WHERE id=? AND status IN ('queued','running')
                    """,
                    (schedule["last_job"],),
                ).fetchone()

                if active:
                    continue

                start, end = period_dates(schedule["period"])
                params = filters(
                    {
                        **params,
                        "start": start,
                        "end": end,
                    }
                )
                params.update(
                    save_report=True,
                    auto_publish=bool(schedule["publish"]),
                    schedule_id=schedule["id"],
                )

                job_id = uid()
                db.execute(
                    """
                    INSERT INTO jobs (
                        id,kind,user_id,params,status,active_key,created_at
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        job_id,
                        "analysis",
                        schedule["user_id"],
                        pack(params),
                        "queued",
                        digest(pack([schedule["id"], start, end])),
                        now(),
                    ),
                )
                db.execute(
                    """
                    UPDATE schedules
                    SET last_run=?, last_job=?, next_run=?
                    WHERE id=?
                    """,
                    (
                        now(),
                        job_id,
                        next_run(schedule),
                        schedule["id"],
                    ),
                )

    def expire_stale(self):
        if self.google.config.get("JOB_MODE") != "request":
            return

        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=6)
        ).isoformat(timespec="microseconds")

        self.store.execute(
            """
            UPDATE jobs
            SET status='interrupted', finished_at=?, error=?
            WHERE status='running' AND started_at<?
            """,
            (
                now(),
                "Lần chạy bị gián đoạn hoặc quá thời gian máy chủ. "
                "Bấm Thử lại để chạy lại.",
                cutoff,
            ),
        )

    def run_one(self, job_id=None, deadline=None):
        self.expire_stale()

        with self.store.connect(immediate=True) as db:
            query = "SELECT * FROM jobs WHERE status='queued'"
            job = db.execute(
                query
                + (" AND id=?" if job_id else "")
                + " ORDER BY created_at,id LIMIT 1",
                (job_id,) if job_id else (),
            ).fetchone()

            if not job:
                return False

            job = dict(job)
            db.execute(
                "UPDATE jobs SET status='running',started_at=? WHERE id=?",
                (now(), job["id"]),
            )

        if deadline is None and self.google.config.get("JOB_MODE") == "request":
            deadline = time.monotonic() + 220

        token = REQUEST_DEADLINE.set(deadline)

        try:
            self.perform(job)
        except Problem as exc:
            self.store.execute(
                """
                UPDATE jobs
                SET status='failed',finished_at=?,error=?
                WHERE id=?
                """,
                (now(), exc.message, job["id"]),
            )
        except Exception:
            self.store.execute(
                """
                UPDATE jobs
                SET status='failed',finished_at=?,error=?
                WHERE id=?
                """,
                (
                    now(),
                    "Tác vụ không hoàn tất. Kết quả cũ vẫn được giữ. "
                    "Kiểm tra nguồn và thử lại.",
                    job["id"],
                ),
            )
        finally:
            REQUEST_DEADLINE.reset(token)

        return True

    def perform(self, job):
        p = json.loads(job["params"])

        if p.get("demo") and (
            job["kind"] == "connection"
            or not self.store.setting("demo_pack")
        ):
            raise Problem("Dữ liệu demo chưa được bật cho tác vụ này.")

        user = self.store.one(
            "SELECT * FROM users WHERE id=? AND active=1",
            (job["user_id"],),
        )

        if (
            not user
            or not allowed(user, p["report_type"])
            or (
                job["kind"] == "connection"
                and user["role"] != "admin"
            )
        ):
            raise Problem("Người thực hiện không còn quyền chạy tác vụ.")

        if p.get("save_report") and user["role"] == "viewer":
            raise Problem("Không còn quyền lưu báo cáo.")

        if job["kind"] == "export":
            row = self.store.one(
                "SELECT data FROM datasets WHERE id=?",
                (p["dataset_id"],),
            )

            if not row:
                raise Problem("Không tìm thấy kết quả báo cáo.")

            content = excel_bytes(json.loads(row["data"]))
            self.store.save_artifact(job["id"], content)
            self.store.execute(
                """
                UPDATE jobs
                SET status='succeeded',finished_at=?,dataset_id=?
                WHERE id=?
                """,
                (now(), p["dataset_id"], job["id"]),
            )
            return

        source_names = TYPES[p["report_type"]][1]
        platform_refs = None

        has_real_google_source = (
            not p.get("demo")
            and any(name in GOOGLE_PLATFORM_SOURCES for name in source_names)
        )

        if has_real_google_source:
            platform_refs = self._google_platform_refs()

        sources = {}
        steps = []
        sync_runs = {}

        for name in source_names:
            steps.append(
                {
                    "source": name,
                    "status": "running",
                    "started_at": now(),
                }
            )
            self.store.execute(
                "UPDATE jobs SET steps=? WHERE id=?",
                (pack(steps), job["id"]),
            )

            sync_id = None
            asset_id = None

            if platform_refs and name in GOOGLE_PLATFORM_SOURCES:
                asset_id = platform_refs["assets"].get(name)
                sync_id = self.platform.start_sync(
                    client_id=DEFAULT_CLIENT_ID,
                    provider="google",
                    sync_type=self._sync_type(job, p),
                    requested_start=p.get("start"),
                    requested_end=p.get("end"),
                    connection_id=platform_refs["connection_id"],
                    asset_id=asset_id,
                    job_id=job["id"],
                )
                sync_runs[name] = sync_id

            if name == "gmb":
                fetch = lambda: gmb_data(self.store, p)
            else:
                fetch = lambda n=name: self.google.fetch(n, p)

            # Demo is allowed only when explicitly requested. It is never used as
            # a fallback after a real provider failure.
            if p.get("demo") and name != "gmb":
                from .demo import demo_source

                fetch = lambda n=name: demo_source(n, p)

            from .marketing_provenance import AdapterResult, record_adapter_receipt
            adapter_receipt = []
            provider_fetch = fetch

            def captured_fetch():
                response = provider_fetch()
                if isinstance(response, AdapterResult):
                    adapter_receipt.append(response.receipt)
                return response

            result = source_result(name, p, captured_fetch)

            if sync_id:
                result = self._finish_google_sync(
                    sync_id=sync_id,
                    source=name,
                    result=result,
                    asset_id=asset_id,
                )
                if adapter_receipt and not p.get('demo') and result['status'] in ('ready', 'delayed', 'empty', 'incomplete'):
                    record_adapter_receipt(self.store, self.google.cipher, sync_id, result, adapter_receipt[0])

            sources[name] = result
            steps[-1].update(
                status=result["status"],
                finished_at=now(),
                error=result.get("error"),
                warnings=result.get("warnings"),
            )
            self.store.execute(
                "UPDATE jobs SET steps=? WHERE id=?",
                (pack(steps), job["id"]),
            )

        if all(source["status"] in GOOD for source in sources.values()):
            status = "succeeded"
        elif any(source["status"] in GOOD for source in sources.values()):
            status = "partial"
        else:
            status = "failed"

        dataset_id = None

        if job["kind"] == "connection":
            self.store.set_setting(
                "google_sources",
                {
                    key: {
                        field: value.get(field)
                        for field in (
                            "source",
                            "label",
                            "status",
                            "error",
                            "requested_start",
                            "requested_end",
                            "latest_available_date",
                            "fetched_at",
                            "warnings",
                        )
                    }
                    for key, value in sources.items()
                },
            )
            self.store.set_setting("google_checked_at", now())
        else:
            dataset_id = uid()
            dataset = {
                "id": dataset_id,
                "client_id": DEFAULT_CLIENT_ID,
                "sync_runs": sync_runs,
                "params": p,
                "created_at": now(),
                "sources": sources,
                "organization": self.store.setting(
                    "organization",
                    {
                        "name": "KinderHealth",
                        "author": "",
                    },
                ),
            }

            self.store.execute(
                "INSERT INTO datasets VALUES (?,?,?,?,?,?)",
                (
                    dataset_id,
                    job["user_id"],
                    p["report_type"],
                    dataset["created_at"],
                    int(valid_dataset(dataset)),
                    pack(dataset),
                ),
            )

            if p.get("save_report") and valid_dataset(dataset):
                report_id = save_report(
                    self.store,
                    job["user_id"],
                    dataset,
                )

                if p.get("auto_publish"):
                    publish(
                        self.store,
                        job["user_id"],
                        report_id,
                    )

        self.store.execute(
            """
            UPDATE jobs
            SET status=?,finished_at=?,dataset_id=?
            WHERE id=?
            """,
            (status, now(), dataset_id, job["id"]),
        )
