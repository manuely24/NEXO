"""Redacción determinista antes de enviar texto a un proveedor remoto."""

from __future__ import annotations

import re

from nexo.core.models import DataClass

_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|passwd|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"(?i)(?:[A-Z]:\\(?:[^\\\s]+\\)*[^\\\s]*|/(?:[^/\s]+/)+[^/\s]*)"),
)


def sanitize_for_llm(
    text: str,
    data_class: DataClass = DataClass.CLOUD_OK,
    *,
    allow_confidential: bool = False,
) -> str:
    if data_class == DataClass.LOCAL:
        return "[LOCAL DATA OMITTED]"
    if data_class == DataClass.CONFIDENTIAL and not allow_confidential:
        return "[CONFIDENTIAL DATA OMITTED]"
    sanitized = text
    for pattern in _PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized