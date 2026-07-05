from __future__ import annotations

import json
import sqlite3
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Callable, Literal


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
JobTask = Callable[[], dict[str, object]]
JobTaskFactory = Callable[[dict[str, object]], JobTask]


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    created_at: float
    updated_at: float
    result: dict[str, object] | None = None
    error: str | None = None
    payload: dict[str, object] | None = None
    future: Future | None = field(default=None, repr=False)
    task: JobTask | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            payload["result"] = self.result
            run_id = self.result.get("run_id")
            if run_id:
                payload["run_id"] = run_id
        if self.error is not None:
            payload["error"] = self.error
        return payload


class SQLiteJobMetadataStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def load_jobs(self) -> list[JobRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select job_id, status, created_at, updated_at, result_json, error, payload_json
                from jobs
                order by created_at desc
                """
            ).fetchall()
        records = []
        for row in rows:
            result_json = row["result_json"]
            payload_json = row["payload_json"]
            records.append(
                JobRecord(
                    job_id=row["job_id"],
                    status=row["status"],
                    created_at=float(row["created_at"]),
                    updated_at=float(row["updated_at"]),
                    result=json.loads(result_json) if result_json else None,
                    error=row["error"],
                    payload=json.loads(payload_json) if payload_json else None,
                )
            )
        return records

    def upsert(self, record: JobRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert into jobs(job_id, status, created_at, updated_at, result_json, error, payload_json)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(job_id) do update set
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json,
                    error = excluded.error,
                    payload_json = excluded.payload_json
                """,
                (
                    record.job_id,
                    record.status,
                    record.created_at,
                    record.updated_at,
                    json.dumps(record.result, ensure_ascii=False, default=str) if record.result is not None else None,
                    record.error,
                    json.dumps(record.payload, ensure_ascii=False, default=str) if record.payload is not None else None,
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists jobs(
                    job_id text primary key,
                    status text not null,
                    created_at real not null,
                    updated_at real not null,
                    result_json text,
                    error text,
                    payload_json text
                )
                """
            )
            columns = {row["name"] for row in conn.execute("pragma table_info(jobs)").fetchall()}
            if "payload_json" not in columns:
                conn.execute("alter table jobs add column payload_json text")


class InMemoryJobStore:
    def __init__(
        self,
        max_workers: int = 2,
        metadata_path: str | Path | None = None,
        task_factory: JobTaskFactory | None = None,
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="semicon-agent-job")
        self._metadata = SQLiteJobMetadataStore(metadata_path) if metadata_path is not None else None
        self._task_factory = task_factory
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._load_persisted_jobs()

    def submit(self, task: JobTask, payload: dict[str, object] | None = None) -> JobRecord:
        now = time.time()
        record = JobRecord(
            job_id=str(uuid.uuid4()),
            status="queued",
            created_at=now,
            updated_at=now,
            payload=payload,
            task=task,
        )
        self._enqueue(record, task)
        return record

    def _enqueue(self, record: JobRecord, task: JobTask) -> None:
        with self._lock:
            self._jobs[record.job_id] = record
            self._persist(record)
        future = self._executor.submit(self._run, record.job_id, task)
        with self._lock:
            record.future = future

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[JobRecord]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def counts(self) -> dict[str, int]:
        counts = {"queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
        with self._lock:
            for job in self._jobs.values():
                counts[job.status] += 1
        return counts

    def cancel(self, job_id: str) -> bool | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.status in {"completed", "failed", "cancelled"}:
                return False
            future = record.future
        if future is None or not future.cancel():
            return False
        self._update(job_id, status="cancelled", error="Job was cancelled before execution.")
        return True

    def retry(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return None
            if record.status not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            task = self._task_from_payload(record.payload) if record.payload is not None else record.task
            payload = record.payload
        if task is None:
            raise ValueError("Job cannot be retried because its task is unavailable.")
        return self.submit(task, payload=payload)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str, task: JobTask) -> None:
        self._update(job_id, status="running")
        try:
            result = task()
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
            return
        self._update(job_id, status="completed", result=result)

    def _update(
        self,
        job_id: str,
        status: JobStatus,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = status
            record.updated_at = time.time()
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            self._persist(record)

    def _load_persisted_jobs(self) -> None:
        if self._metadata is None:
            return
        for record in self._metadata.load_jobs():
            if record.status in {"queued", "running"}:
                task = self._task_from_payload(record.payload)
                if task is not None:
                    record.status = "queued"
                    record.updated_at = time.time()
                    record.error = None
                    record.task = task
                    self._enqueue(record, task)
                    continue
                record.status = "failed"
                record.updated_at = time.time()
                record.error = "Job was interrupted before completion."
                self._metadata.upsert(record)
            self._jobs[record.job_id] = record

    def _task_from_payload(self, payload: dict[str, object] | None) -> JobTask | None:
        if payload is None or self._task_factory is None:
            return None
        return self._task_factory(payload)

    def _persist(self, record: JobRecord) -> None:
        if self._metadata is not None:
            self._metadata.upsert(record)
