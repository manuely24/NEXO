"""Verificación posterior de operaciones sobre archivos."""

from __future__ import annotations

from pathlib import Path

from nexo.core.models import ActionRequest
from nexo.tools.fs_tools import workspace_path
from nexo.verifiers.base import Verification, Verifier


class FileExistsVerifier(Verifier):
    name = "file_exists"

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()

    def verify(self, action: ActionRequest, output: str) -> Verification:
        path = action.params.get("path")
        exists = False
        if isinstance(path, str):
            exists = workspace_path(self.workspace, path).exists()
        return Verification(exists, "El archivo existe" if exists else "El archivo no existe")


class FileContainsVerifier(Verifier):
    name = "file_contains"

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()

    def verify(self, action: ActionRequest, output: str) -> Verification:
        path = action.params.get("path")
        expected = action.params.get("expected", action.params.get("content"))
        if not isinstance(path, str) or not isinstance(expected, str):
            return Verification(False, "Se requieren path y expected/content")
        try:
            file_path = workspace_path(self.workspace, path)
            contains = expected in file_path.read_text(encoding="utf-8")
        except (OSError, PermissionError, UnicodeError) as exc:
            return Verification(False, f"No se pudo leer el archivo: {exc}")
        return Verification(contains, "Contenido verificado" if contains else "Contenido ausente")