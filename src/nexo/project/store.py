"""Persistencia local de sesiones del arquitecto de proyectos."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from nexo.project.architect import PROJECT_TYPES, ProjectPhaseResult


@dataclass(frozen=True)
class ProjectSession:
    id: str
    requirement: str
    project_type: str
    next_phase: int
    phases: tuple[ProjectPhaseResult, ...]
    status: str


class ProjectSessionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.path))
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS project_sessions (
                id TEXT PRIMARY KEY,
                requirement TEXT NOT NULL,
                project_type TEXT NOT NULL,
                next_phase INTEGER NOT NULL,
                phases_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'awaiting_phase_1',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        self._connection.commit()

    def create(self, requirement: str, project_type: str) -> ProjectSession:
        if not requirement.strip():
            raise ValueError("El requerimiento no puede estar vacío")
        if project_type not in PROJECT_TYPES:
            raise ValueError("Tipo de proyecto no admitido")

        session_id = uuid4().hex[:12]
        timestamp = datetime.now(UTC).isoformat()
        self._connection.execute(
            """INSERT INTO project_sessions (
                id, requirement, project_type, next_phase, phases_json, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, 1, '{}', 'awaiting_phase_1', ?, ?)""",
            (session_id, requirement.strip(), project_type, timestamp, timestamp),
        )
        self._connection.commit()
        return self.get(session_id)

    def get(self, session_id: str) -> ProjectSession:
        row = self._connection.execute(
            """SELECT id, requirement, project_type, next_phase, phases_json, status
               FROM project_sessions WHERE id = ?""",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No existe la sesión de proyecto {session_id}")

        phase_payloads = json.loads(row["phases_json"])
        phases = tuple(
            ProjectPhaseResult.model_validate(phase_payloads[str(number)])
            for number in sorted(map(int, phase_payloads))
        )
        return ProjectSession(
            id=row["id"],
            requirement=row["requirement"],
            project_type=row["project_type"],
            next_phase=int(row["next_phase"]),
            phases=phases,
            status=row["status"],
        )

    def save_phase(self, session_id: str, phase: ProjectPhaseResult) -> ProjectSession:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            row = self._connection.execute(
                "SELECT next_phase, phases_json, project_type FROM project_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"No existe la sesión de proyecto {session_id}")
            if int(row["next_phase"]) != phase.phase:
                raise ValueError(
                    f"Se esperaba la Fase {row['next_phase']}; "
                    f"no se puede guardar la Fase {phase.phase}"
                )
            if row["project_type"] not in {"auto", phase.project_type}:
                raise ValueError("La fase cambió el tipo de proyecto seleccionado")

            phases = json.loads(row["phases_json"])
            if phases and phase.project_name != next(iter(phases.values()))["project_name"]:
                raise ValueError("La fase cambió el nombre del proyecto")
            phases[str(phase.phase)] = phase.model_dump(mode="json")
            next_phase = phase.phase + 1
            status = "complete" if phase.phase == 4 else f"awaiting_phase_{next_phase}"
            self._connection.execute(
                """UPDATE project_sessions
                   SET project_type = ?, next_phase = ?, phases_json = ?, status = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    phase.project_type,
                    next_phase,
                    json.dumps(phases, ensure_ascii=False),
                    status,
                    datetime.now(UTC).isoformat(),
                    session_id,
                ),
            )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return self.get(session_id)

    def close(self) -> None:
        self._connection.close()
