"""Registro de eventos de auditoría: SQLite append-only.

Los triggers impiden UPDATE y DELETE incluso desde código de Nexo.
Los valores con claves sensibles (token, password...) se redactan antes de guardar.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SENSITIVE_KEYS = ("token", "password", "passwd", "secret", "api_key", "apikey", "authorization")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    correlation_id TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_corr ON events(correlation_id);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events es append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events es append-only'); END;
"""


def redact(value: Any) -> Any:
    """Reemplaza recursivamente valores de claves sensibles."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if any(s in str(k).lower() for s in SENSITIVE_KEYS) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class EventLog:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._subscribers: set[Callable[[dict[str, Any]], None]] = set()
        self._lock = threading.RLock()

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        self._subscribers.add(callback)

        def unsubscribe() -> None:
            self._subscribers.discard(callback)

        return unsubscribe

    def append(
        self, kind: str, payload: dict[str, Any], correlation_id: str | None = None
    ) -> int:
        timestamp = datetime.now(UTC).isoformat()
        safe_payload = redact(payload)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (ts, kind, correlation_id, payload) VALUES (?, ?, ?, ?)",
                (
                    timestamp,
                    kind,
                    correlation_id,
                    json.dumps(safe_payload, default=str, ensure_ascii=False),
                ),
            )
            self._conn.commit()
            assert cur.lastrowid is not None
            event_id = cur.lastrowid
        event = {
            "id": event_id,
            "ts": timestamp,
            "kind": kind,
            "correlation_id": correlation_id,
            "payload": safe_payload,
        }
        for subscriber in tuple(self._subscribers):
            try:
                subscriber(event)
            except Exception:
                continue
        return event_id

    def read(
        self, correlation_id: str | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT id, ts, kind, correlation_id, payload FROM events WHERE 1=1"
        args: list[Any] = []
        if correlation_id is not None:
            query += " AND correlation_id = ?"
            args.append(correlation_id)
        if kind is not None:
            query += " AND kind = ?"
            args.append(kind)
        query += " ORDER BY id"
        with self._lock:
            return [
                {
                    "id": r[0],
                    "ts": r[1],
                    "kind": r[2],
                    "correlation_id": r[3],
                    "payload": json.loads(r[4]),
                }
                for r in self._conn.execute(query, args)
            ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
