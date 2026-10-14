"""Proveedor Gemini mediante el SDK oficial google-genai."""

from __future__ import annotations

import os

from nexo.llm.base import LLMProvider


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash") -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Configura GEMINI_API_KEY o GOOGLE_API_KEY en el entorno")
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Instala la dependencia google-genai para usar Gemini") from exc
        self.client = genai.Client(api_key=key)
        self.model = model

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
        except Exception as exc:
            raise RuntimeError(f"La solicitud a Gemini falló: {exc}") from exc
        text = response.text
        if not text:
            raise RuntimeError("Gemini devolvió una respuesta vacía")
        return text