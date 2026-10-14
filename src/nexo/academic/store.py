"""Almacén SQLite local para tareas de Campusland/Moodle."""

from __future__ import annotations

import csv
import json
import sqlite3
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any


class CampuslandTaskStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS academic_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
            )"""
        )
        self._conn.commit()

    def add_task(
        self,
        title: str,
        subject: str,
        due_date: date | str,
        status: str = "pending",
    ) -> int:
        if not title.strip() or not subject.strip():
            raise ValueError("title y subject no pueden estar vacíos")
        due = date.fromisoformat(due_date) if isinstance(due_date, str) else due_date
        if status not in {"pending", "in_progress", "completed"}:
            raise ValueError("status debe ser pending, in_progress o completed")
        cursor = self._conn.execute(
            "INSERT INTO academic_tasks (title, subject, due_date, status) VALUES (?, ?, ?, ?)",
            (title.strip(), subject.strip(), due.isoformat(), status),
        )
        self._conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def list_due(
        self, within_days: int = 7, today: date | None = None
    ) -> list[dict[str, str | int]]:
        if within_days < 0:
            raise ValueError("within_days no puede ser negativo")
        start = today or date.today()
        end = start.fromordinal(start.toordinal() + within_days)
        rows = self._conn.execute(
            """SELECT id, title, subject, due_date, status FROM academic_tasks
               WHERE status != 'completed' AND due_date <= ?
               ORDER BY due_date, id""",
            (end.isoformat(),),
        )
        return [dict(row) for row in rows]

    def get_task(self, task_id: int) -> dict[str, str | int] | None:
        row = self._conn.execute(
            "SELECT id, title, subject, due_date, status FROM academic_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def count_tasks(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM academic_tasks").fetchone()
        return int(row[0])

    def import_file(self, path: str | Path) -> int:
        source = Path(path)
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
            rows = payload.get("tasks") if isinstance(payload, dict) else payload
        elif source.suffix.lower() == ".csv":
            with source.open(encoding="utf-8-sig", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
        else:
            raise ValueError("El archivo debe tener extensión .json o .csv")
        if not isinstance(rows, list):
            raise ValueError("El archivo debe contener una lista de tareas")
        normalized = [self._normalize_import_row(row) for row in rows]
        with self._conn:
            self._conn.executemany(
                """INSERT INTO academic_tasks (title, subject, due_date, status)
                   VALUES (?, ?, ?, ?)""",
                normalized,
            )
        return len(normalized)

    @staticmethod
    def _normalize_import_row(row: Any) -> tuple[str, str, str, str]:
        if not isinstance(row, dict):
            raise ValueError("Cada tarea importada debe ser un objeto")

        def key(value: object) -> str:
            plain = unicodedata.normalize("NFKD", str(value))
            return "".join(char.lower() for char in plain if char.isalnum())

        values = {key(name): value for name, value in row.items()}

        def field(*aliases: str) -> str:
            for alias in aliases:
                value = values.get(key(alias))
                if value is not None and str(value).strip():
                    return str(value).strip()
            return ""

        title = field("title", "tarea", "task", "actividad", "nombre")
        subject = field("subject", "materia", "asignatura", "curso", "course")
        due_value = field(
            "due_date", "due date", "fecha límite", "fecha de entrega", "fecha entrega", "deadline"
        )
        status = field("status", "estado").lower() or "pending"
        status_aliases = {
            "pendiente": "pending",
            "en progreso": "in_progress",
            "completada": "completed",
        }
        status = status_aliases.get(status, status.replace(" ", "_"))
        if not title or not subject or not due_value:
            raise ValueError("Cada tarea requiere título, materia y fecha límite")
        due = CampuslandTaskStore._parse_import_date(due_value).isoformat()
        if status not in {"pending", "in_progress", "completed"}:
            raise ValueError(f"Estado de tarea no válido: {status}")
        return title, subject, due, status

    @staticmethod
    def _parse_import_date(value: str) -> date:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            formats = (
                "%A, %B %d, %Y, %I:%M %p",
                "%B %d, %Y, %I:%M %p",
                "%A, %B %d, %Y, %H:%M",
                "%B %d, %Y, %H:%M",
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y/%m/%d",
                "%A, %B %d, %Y",
                "%B %d, %Y",
                "%A, %d %B %Y",
                "%d %B %Y",
            )
            for date_format in formats:
                try:
                    candidate = value if "," in date_format else value.split(",", 1)[0]
                    return datetime.strptime(candidate, date_format).date()
                except ValueError:
                    continue
        raise ValueError(f"Fecha límite no reconocida: {value}")

    def close(self) -> None:
        self._conn.close()