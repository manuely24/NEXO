"""Herramientas de consulta y alta académica."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nexo.academic.store import CampuslandTaskStore
from nexo.core.models import RiskLevel
from nexo.tools.base import BaseTool


class AcademicGetDueTasksTool(BaseTool):
    name = "academic.get_due_tasks"

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def run(self, params: dict[str, Any]) -> str:
        store = CampuslandTaskStore(self.database)
        try:
            tasks = store.list_due(within_days=int(params.get("within_days", 7)))
        finally:
            store.close()
        return json.dumps(tasks, ensure_ascii=False)


class AcademicAddTaskTool(BaseTool):
    name = "academic.add_task"
    risk_level = RiskLevel.MODIFIES_FILES

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def run(self, params: dict[str, Any]) -> str:
        store = CampuslandTaskStore(self.database)
        try:
            task_id = store.add_task(
                title=str(params.get("title", "")),
                subject=str(params.get("subject", "")),
                due_date=str(params.get("due_date", "")),
            )
        finally:
            store.close()
        return str(task_id)


class AcademicImportTasksTool(BaseTool):
    name = "academic.import_tasks"
    risk_level = RiskLevel.MODIFIES_FILES
    path_params = ("path",)

    def __init__(self, database: str | Path, workspace: str | Path) -> None:
        self.database = Path(database)
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        path = Path(str(params["path"]))
        if not path.is_absolute():
            path = self.workspace / path
        path = path.resolve()
        if not path.is_relative_to(self.workspace):
            raise PermissionError("El archivo de importación debe estar dentro del workspace")
        store = CampuslandTaskStore(self.database)
        try:
            return str(store.import_file(path))
        finally:
            store.close()