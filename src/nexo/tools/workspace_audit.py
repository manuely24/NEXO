"""Auditoría local y no destructiva de workspace y configuración de VS Code."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from nexo.tools.base import BaseTool
from nexo.tools.fs_tools import workspace_path

_CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
_LARGE_NAMES = {".venv", "venv", "node_modules", "build", "dist", ".tox", ".nox"}
_SKIP_SCAN = {".git", ".venv", "venv", "node_modules"}
_MAX_SCAN_ENTRIES = 50_000
_MAX_SIZE_ENTRIES = 50_000

_RECOMMENDED_GITIGNORE = (
    "__pycache__/",
    "*.py[cod]",
    ".venv/",
    "venv/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "node_modules/",
    ".env",
    "data/",
)

_RECOMMENDED_SETTINGS = {
    "editor.formatOnSave": True,
    "editor.minimap.enabled": False,
    "editor.smoothScrolling": False,
    "workbench.list.smoothScrolling": False,
    "workbench.reduceMotion": "on",
    "search.exclude": {
        "**/.venv/**": True,
        "**/venv/**": True,
        "**/__pycache__/**": True,
        "**/.mypy_cache/**": True,
        "**/.pytest_cache/**": True,
        "**/.ruff_cache/**": True,
        "**/node_modules/**": True,
        "**/data/**/*.db": True,
    },
    "files.watcherExclude": {
        "**/.venv/**": True,
        "**/venv/**": True,
        "**/__pycache__/**": True,
        "**/.mypy_cache/**": True,
        "**/.pytest_cache/**": True,
        "**/.ruff_cache/**": True,
        "**/node_modules/**": True,
        "**/data/**/*.db": True,
    },
}


def _directory_size(path: Path) -> tuple[int, int, bool]:
    total_bytes = 0
    entries = 0
    truncated = False
    for current, directories, filenames in os.walk(path, followlinks=False):
        directories[:] = [
            name for name in directories if not (Path(current) / name).is_symlink()
        ]
        for filename in filenames:
            file_path = Path(current) / filename
            entries += 1
            if entries > _MAX_SIZE_ENTRIES:
                truncated = True
                return total_bytes, entries - 1, truncated
            try:
                if not file_path.is_symlink():
                    total_bytes += file_path.stat().st_size
            except OSError:
                continue
    return total_bytes, entries, truncated


class WorkspaceAuditTool(BaseTool):
    name = "workspace.audit"
    path_params = ("path",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        root = workspace_path(self.workspace, str(params.get("path", ".")))
        if not root.is_dir():
            raise NotADirectoryError(root)

        cache_directories: list[Path] = []
        large_directories: list[Path] = []
        files_scanned = 0
        entries_scanned = 0
        truncated = False

        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            safe_directories = []
            for name in directories:
                child = current_path / name
                if child.is_symlink() or name == ".git":
                    continue
                if name in _CACHE_NAMES:
                    cache_directories.append(child)
                    continue
                if name in _LARGE_NAMES:
                    large_directories.append(child)
                    continue
                if name not in _SKIP_SCAN:
                    safe_directories.append(name)
            directories[:] = safe_directories

            files_scanned += len(filenames)
            entries_scanned += len(directories) + len(filenames)
            if entries_scanned >= _MAX_SCAN_ENTRIES:
                truncated = True
                break

        measured_directories = sorted(set(cache_directories + large_directories))
        measured: list[dict[str, Any]] = []
        for directory in measured_directories:
            size, file_count, size_truncated = _directory_size(directory)
            measured.append({
                "path": directory.relative_to(root).as_posix(),
                "bytes": size,
                "files": file_count,
                "truncated": size_truncated,
                "kind": "cache" if directory.name in _CACHE_NAMES else "environment_or_build",
            })

        gitignore_path = root / ".gitignore"
        gitignore_lines = (
            set(gitignore_path.read_text(encoding="utf-8").splitlines())
            if gitignore_path.is_file()
            else set()
        )
        missing_gitignore = [
            pattern for pattern in _RECOMMENDED_GITIGNORE if pattern not in gitignore_lines
        ]

        vscode_settings = root / ".vscode" / "settings.json"
        settings_status: str | dict[str, Any] = "no existe configuración local del workspace"
        if vscode_settings.is_file():
            try:
                settings = json.loads(vscode_settings.read_text(encoding="utf-8"))
                relevant_keys = (
                    "files.watcherExclude",
                    "search.exclude",
                    "files.exclude",
                    "editor.formatOnSave",
                    "editor.minimap.enabled",
                    "workbench.reduceMotion",
                )
                settings_status = {
                    key: settings[key] for key in relevant_keys if key in settings
                }
            except (OSError, UnicodeError, json.JSONDecodeError):
                settings_status = "settings.json existe, pero no se pudo analizar"

        extensions_path = Path.home() / ".vscode" / "extensions"
        extensions = (
            sorted(child.name for child in extensions_path.iterdir() if child.is_dir())[:200]
            if extensions_path.is_dir()
            else []
        )

        return json.dumps(
            {
                "workspace": str(root),
                "files_scanned": files_scanned,
                "scan_truncated": truncated,
                "generated_directories": measured,
                "gitignore_missing_recommendations": missing_gitignore,
                "workspace_settings": settings_status,
                "installed_vscode_extensions": extensions,
                "recommended_settings": _RECOMMENDED_SETTINGS,
                "actions_taken": [],
            },
            ensure_ascii=False,
        )