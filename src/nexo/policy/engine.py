"""Política local: el LLM propone, esta capa decide."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nexo.core.models import ActionRequest, DataClass, RiskLevel
from nexo.tools.base import ToolRegistry


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class PolicyEngine:
    def __init__(self, registry: ToolRegistry, workspace: str | Path) -> None:
        self.registry = registry
        self.workspace = Path(workspace).resolve()
        self.data_dir = (self.workspace / "data").resolve()

    def evaluate(
        self,
        action: ActionRequest,
        *,
        explicit_approval: bool = False,
        authorized_data_sources: set[str] | None = None,
    ) -> PolicyDecision:
        try:
            tool = self.registry.get(action.tool)
        except KeyError as exc:
            return PolicyDecision(False, str(exc))

        if action.risk_level < tool.risk_level:
            return PolicyDecision(False, "El nivel de riesgo declarado es inferior al requerido")
        sensitivity = {
            DataClass.CLOUD_OK: 0,
            DataClass.CONFIDENTIAL: 1,
            DataClass.LOCAL: 2,
        }
        if sensitivity[action.data_class] < sensitivity[tool.data_class]:
            return PolicyDecision(
                False, "La clase de datos es menos restrictiva que la herramienta"
            )
        if tool.external and action.data_class == DataClass.LOCAL:
            return PolicyDecision(False, "Los datos LOCAL nunca pueden salir del equipo")
        if tool.external and action.data_class == DataClass.CONFIDENTIAL:
            source = str(action.params.get("source", ""))
            if not source:
                return PolicyDecision(
                    False, "La acción requiere aprobación explícita de una fuente"
                )
            if source not in (authorized_data_sources or set()):
                return PolicyDecision(
                    False, f"La fuente {source} requiere aprobación explícita"
                )

        for parameter in tool.path_params:
            raw_path = action.params.get(parameter)
            if not isinstance(raw_path, str) or not raw_path.strip():
                return PolicyDecision(False, f"Falta la ruta requerida: {parameter}")
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = self.workspace / candidate
            resolved = candidate.resolve()
            if not resolved.is_relative_to(self.workspace):
                return PolicyDecision(False, f"Ruta fuera del workspace: {parameter}")

        requires_approval = (
            action.risk_level >= RiskLevel.MODIFIES_FILES
            or tool.external
            or action.from_untrusted_content
        )
        if requires_approval and not explicit_approval:
            return PolicyDecision(False, "La acción requiere aprobación explícita")
        return PolicyDecision(True, "Acción autorizada por política")