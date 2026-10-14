"""Contrato de verificadores para resultados de acciones."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from nexo.core.models import ActionRequest


@dataclass(frozen=True)
class Verification:
    verified: bool
    detail: str


class Verifier(ABC):
    name: str

    @abstractmethod
    def verify(self, action: ActionRequest, output: str) -> Verification:
        """Comprueba un efecto posterior a la ejecución."""


class VerifierRegistry:
    def __init__(self) -> None:
        self._verifiers: dict[str, Verifier] = {}

    def register(self, verifier: Verifier) -> None:
        if not verifier.name or verifier.name in self._verifiers:
            raise ValueError(f"Verificador vacío o duplicado: {verifier.name!r}")
        self._verifiers[verifier.name] = verifier

    def get(self, name: str) -> Verifier:
        try:
            return self._verifiers[name]
        except KeyError as exc:
            raise KeyError(f"Verificador no registrado: {name}") from exc