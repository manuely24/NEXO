"""Verificación del estado real del repositorio Git."""

from __future__ import annotations

import subprocess
from pathlib import Path

from nexo.core.models import ActionRequest
from nexo.verifiers.base import Verification, Verifier


class GitStatusVerifier(Verifier):
    name = "git_status"

    def __init__(self, workspace: str | Path, timeout_s: float = 5.0) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout_s = timeout_s

    def verify(self, action: ActionRequest, output: str) -> Verification:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--", "."],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
                timeout=self.timeout_s,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return Verification(False, f"No se pudo verificar Git: {exc}")
        clean = not result.stdout.strip()
        expected_clean = action.params.get("expected_clean")
        verified = expected_clean is None or clean == bool(expected_clean)
        detail = "Repositorio limpio" if clean else "Hay cambios pendientes"
        return Verification(verified, detail)