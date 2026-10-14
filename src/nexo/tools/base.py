"""Abstracción y registro determinista de herramientas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from nexo.core.models import DataClass, RiskLevel


class BaseTool(ABC):
    name: str
    risk_level: RiskLevel = RiskLevel.INFO
    external: bool = False
    data_class: DataClass = DataClass.LOCAL
    path_params: tuple[str, ...] = ()

    @abstractmethod
    def run(self, params: dict[str, Any]) -> str:
        """Ejecuta una acción ya autorizada por el Policy Engine."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not tool.name or tool.name in self._tools:
            raise ValueError(f"Nombre de herramienta vacío o duplicado: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Herramienta no registrada: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))