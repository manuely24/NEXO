"""Verifica que los archivos del scaffold existan dentro del workspace."""

from __future__ import annotations

import json
from pathlib import Path

from nexo.core.models import ActionRequest
from nexo.project.architect import safe_project_file_parts
from nexo.tools.fs_tools import workspace_path
from nexo.verifiers.base import Verification, Verifier


class ProjectScaffoldVerifier(Verifier):
    name = "project_scaffold"

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            result = json.loads(output)
            target = workspace_path(self.workspace, str(result["target"]))
            files = result["files"]
            if not isinstance(files, list) or not files:
                return Verification(False, "El scaffold no informó archivos generados")

            target_root = target.resolve()
            for raw_path in files:
                parts = safe_project_file_parts(raw_path)
                path = target_root.joinpath(*parts).resolve()
                if not path.is_relative_to(target_root) or not path.is_file():
                    return Verification(False, f"No se verificó el archivo {raw_path}")
        except (KeyError, TypeError, ValueError, OSError, PermissionError) as exc:
            return Verification(False, f"No se pudo verificar el scaffold: {exc}")

        return Verification(True, f"Se verificaron {len(files)} archivos del proyecto")
