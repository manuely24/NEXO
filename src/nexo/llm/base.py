"""Interfaz mínima para proveedores de lenguaje."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Devuelve texto generado; el llamador valida toda salida estructurada."""