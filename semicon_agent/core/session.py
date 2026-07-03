from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from semicon_agent.core.trace import RunEvent


class SQLiteRunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def save_run_start(self, run_id: str, request: str, context: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                insert or replace into runs(run_id, request, context_json, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (run_id, request, json.dumps(context, ensure_ascii=False, default=str), "running", time.time(), time.time()),
            )

    def save_run_end(self, run_id: str, final_answer: str, status: str = "completed") -> None:
        with self._connect() as conn:
            conn.execute(
                "update runs set status = ?, final_answer = ?, updated_at = ? where run_id = ?",
                (status, final_answer, time.time(), run_id),
            )

    def save_events(self, events: list[RunEvent]) -> None:
        if not events:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                insert into events(run_id, event_type, message, payload_json, created_at)
                values (?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.run_id,
                        event.event_type,
                        event.message,
                        json.dumps(event.payload, ensure_ascii=False, default=str),
                        event.created_at,
                    )
                    for event in events
                ],
            )

    def list_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select run_id, request, status, final_answer, created_at, updated_at
                from runs
                order by created_at desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select run_id, event_type, message, payload_json, created_at
                from events
                where run_id = ?
                order by id asc
                """,
                (run_id,),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            events.append(item)
        return events

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists runs(
                    run_id text primary key,
                    request text not null,
                    context_json text not null,
                    status text not null,
                    final_answer text,
                    created_at real not null,
                    updated_at real not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists events(
                    id integer primary key autoincrement,
                    run_id text not null,
                    event_type text not null,
                    message text not null,
                    payload_json text not null,
                    created_at real not null
                )
                """
            )
