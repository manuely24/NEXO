"""Inspección del repositorio actual y operaciones Git controladas."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from nexo.core.models import DataClass, RiskLevel
from nexo.tools.base import BaseTool


class GitTool(BaseTool):
    def __init__(self, workspace: str | Path, timeout_s: float = 8.0) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout_s = timeout_s

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            check=True,
            timeout=self.timeout_s,
        )
        return result.stdout.strip()


class GitStatusTool(GitTool):
    name = "git.status"

    def run(self, params: dict[str, Any]) -> str:
        return self.git("status", "--short", "--branch", "--", ".") or "Working tree limpio"


class GitDiffTool(GitTool):
    name = "git.diff"

    def run(self, params: dict[str, Any]) -> str:
        diff = self.git("diff", "--no-ext-diff", "HEAD", "--", ".")
        return diff or "Sin diferencias en archivos seguidos"


class GitCommitPrepTool(GitTool):
    name = "git.commit_prep"

    def run(self, params: dict[str, Any]) -> str:
        kind = str(params.get("type", "")).strip().lower()
        scope = str(params.get("scope", "")).strip()
        summary = str(params.get("summary", "")).strip()
        if kind not in {"feat", "fix", "docs", "test", "refactor", "chore"}:
            raise ValueError("type debe ser feat, fix, docs, test, refactor o chore")
        if not summary or "\n" in summary:
            raise ValueError("summary debe ser una línea no vacía")
        if scope and not re.fullmatch(r"[a-zA-Z0-9._-]+", scope):
            raise ValueError("scope contiene caracteres no permitidos")
        header = f"{kind}({scope}): {summary}" if scope else f"{kind}: {summary}"
        staged = self.git("diff", "--cached", "--stat", "--", ".") or "No hay cambios staged"
        return (
            f"Mensaje propuesto:\n{header}\n\nCambios staged:\n{staged}\n"
            "Push: requiere aprobación explícita."
        )


class GitPushTool(GitTool):
    name = "git.push"
    risk_level = RiskLevel.EXTERNAL
    external = True
    data_class = DataClass.CLOUD_OK

    def run(self, params: dict[str, Any]) -> str:
        try:
            root = Path(self.git("rev-parse", "--show-toplevel")).resolve()
        except subprocess.SubprocessError as exc:
            raise RuntimeError("El workspace no está dentro de un repositorio Git") from exc
        if root != self.workspace:
            raise PermissionError("git.push solo se permite desde la raíz exacta del workspace")
        remote = str(params.get("remote", "origin"))
        branch = str(params.get("branch", "HEAD"))
        if remote.startswith("-") or branch.startswith("-"):
            raise ValueError("remote y branch no pueden ser opciones")
        return self.git("push", "--", remote, branch) or "Push completado"