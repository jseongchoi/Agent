from __future__ import annotations

import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Literal


JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    created_at: float
    updated_at: float
    result: dict[str, object] | None = None
    error: str | None = None
    future: Future | None = field(default=None, repr=False)
    task: Callable[[], dict[str, object]] | None = field(default=None, repr=False)

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


class InMemoryJobStore:
    def __init__(self, max_workers: int = 2) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="semicon-agent-job")
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def submit(self, task: Callable[[], dict[str, object]]) -> JobRecord:
        now = time.time()
        record = JobRecord(job_id=str(uuid.uuid4()), status="queued", created_at=now, updated_at=now, task=task)
        with self._lock:
            self._jobs[record.job_id] = record
        future = self._executor.submit(self._run, record.job_id, task)
        with self._lock:
            record.future = future
        return record

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
            task = record.task
        if task is None:
            raise ValueError("Job cannot be retried because its task is unavailable.")
        return self.submit(task)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str, task: Callable[[], dict[str, object]]) -> None:
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
