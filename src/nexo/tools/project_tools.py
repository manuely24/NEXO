"""Creación atómica de proyectos nuevos dentro del workspace de Nexo."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from nexo.core.models import RiskLevel
from nexo.project.architect import ProjectBlueprint, safe_project_file_parts
from nexo.tools.base import BaseTool
from nexo.tools.fs_tools import workspace_path


class ProjectScaffoldTool(BaseTool):
    name = "project.scaffold"
    risk_level = RiskLevel.MODIFIES_FILES
    path_params = ("target",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        target = workspace_path(self.workspace, str(params["target"]))
        if target.exists():
            raise FileExistsError("El destino ya existe; Nexo no sobrescribe proyectos")

        blueprint = ProjectBlueprint.model_validate(params.get("blueprint"))
        target.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".nexo-project-", dir=target.parent) as temp_dir:
            staging = Path(temp_dir) / "project"
            staging.mkdir()

            for generated_file in blueprint.files:
                parts = safe_project_file_parts(generated_file.path)
                destination = staging.joinpath(*parts).resolve()
                if not destination.is_relative_to(staging.resolve()):
                    raise PermissionError("La ruta generada sale de la carpeta temporal")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(generated_file.content, encoding="utf-8", newline="\n")

            staging.rename(target)

        return json.dumps(
            {
                "target": target.relative_to(self.workspace).as_posix(),
                "files": [file.path.replace("\\", "/") for file in blueprint.files],
            },
            ensure_ascii=False,
        )
