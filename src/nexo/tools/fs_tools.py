"""Herramientas de filesystem limitadas al workspace del proyecto."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nexo.core.models import RiskLevel
from nexo.tools.base import BaseTool


def workspace_path(workspace: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    resolved = candidate.resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        raise PermissionError("La ruta debe permanecer dentro del workspace")
    return resolved


class FsReadTool(BaseTool):
    name = "fs.read"
    path_params = ("path",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        path = workspace_path(self.workspace, str(params["path"]))
        if not path.is_file():
            raise FileNotFoundError(path)
        return path.read_text(encoding="utf-8")


class FsWriteTool(BaseTool):
    name = "fs.write"
    risk_level = RiskLevel.MODIFIES_FILES
    path_params = ("path",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        path = workspace_path(self.workspace, str(params["path"]))
        content = params.get("content")
        if not isinstance(content, str):
            raise TypeError("content debe ser texto")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Archivo escrito: {path.relative_to(self.workspace)}"


class FsListTool(BaseTool):
    name = "fs.list"
    path_params = ("path",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        path = workspace_path(self.workspace, str(params["path"]))
        if not path.is_dir():
            raise NotADirectoryError(path)
        return "\n".join(sorted(child.name for child in path.iterdir()))