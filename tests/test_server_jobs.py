from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from semicon_agent.server.jobs import JobRecord, SQLiteJobMetadataStore


def test_job_metadata_store_migrates_legacy_schema(tmp_path: Path) -> None:
    job_db = tmp_path / "jobs.sqlite"
    with sqlite3.connect(job_db) as conn:
        conn.execute(
            """
            create table jobs(
                job_id text primary key,
                status text not null,
                created_at real not null,
                updated_at real not null,
                result_json text,
                error text
            )
            """
        )

    store = SQLiteJobMetadataStore(job_db)
    now = time.time()
    store.upsert(
        JobRecord(
            job_id="legacy-job",
            status="queued",
            created_at=now,
            updated_at=now,
            payload={"request": "analyze yield", "max_steps": 3},
            progress={"stage": "queued", "message": "Queued."},
            cancel_requested=True,
        )
    )

    records = store.load_jobs()

    assert records[0].job_id == "legacy-job"
    assert records[0].payload == {"request": "analyze yield", "max_steps": 3}
    assert records[0].progress == {"stage": "queued", "message": "Queued."}
    assert records[0].cancel_requested is True
