"""Verificadores de resultados estructurados."""

from __future__ import annotations

import json
from pathlib import Path

from nexo.academic.store import CampuslandTaskStore
from nexo.core.models import ActionRequest
from nexo.verifiers.base import Verification, Verifier


class JsonListVerifier(Verifier):
    name = "json_list"

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            return Verification(False, "La salida no es JSON válido")
        valid = isinstance(result, list)
        return Verification(valid, "Lista JSON verificada" if valid else "Se esperaba una lista")


class JsonObjectVerifier(Verifier):
    name = "json_object"

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            result = json.loads(output)
        except json.JSONDecodeError:
            return Verification(False, "La salida no es JSON válido")
        valid = isinstance(result, dict)
        return Verification(valid, "Objeto JSON verificado" if valid else "Se esperaba un objeto")


class AcademicTaskExistsVerifier(Verifier):
    name = "academic_task_exists"

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            task_id = int(output)
        except ValueError:
            return Verification(False, "La herramienta no devolvió un id de tarea válido")
        store = CampuslandTaskStore(self.database)
        try:
            exists = store.get_task(task_id) is not None
        finally:
            store.close()
        return Verification(exists, "Tarea persistida en SQLite" if exists else "Tarea ausente")


class AcademicImportVerifier(Verifier):
    name = "academic_import"

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            imported = int(output)
        except ValueError:
            return Verification(False, "La herramienta no devolvió un total válido")
        store = CampuslandTaskStore(self.database)
        try:
            present = store.count_tasks()
        finally:
            store.close()
        verified = imported >= 0 and present >= imported
        return Verification(verified, f"Importación reportó {imported} tareas")