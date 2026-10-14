"""Lectura de resúmenes locales de correo, siempre CONFIDENTIAL."""

from __future__ import annotations

import json
import re
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from nexo.core.models import DataClass
from nexo.tools.base import BaseTool
from nexo.tools.fs_tools import workspace_path

_LOCAL_CONTENT = re.compile(
    r"(?i)\b(password|contraseña|token|api[_ -]?key|secret|cuenta bancaria|"
    r"tarjeta de crédito|diagnóstico|historial médico|número de documento)\b"
)
_CREDENTIAL_VALUE = re.compile(r"(?i)\b(?:password|token|api[_-]?key|secret)\s*[:=]\s*\S+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def sanitize_mail_item(item: dict[str, Any]) -> dict[str, str]:
    fields = {
        name: str(item.get(name, ""))
        for name in ("subject", "sender", "from", "summary", "body", "date")
        if item.get(name) is not None
    }
    content = " ".join(fields.values())
    if _LOCAL_CONTENT.search(content):
        safe_fields = {
            name: "[LOCAL DATA OMITTED]" if name in {"subject", "summary", "body"} else value
            for name, value in fields.items()
        }
        return {
            **safe_fields,
            "status": str(item.get("status", "pending")),
            "classification": DataClass.LOCAL.value,
        }
    for name, value in fields.items():
        fields[name] = _CREDENTIAL_VALUE.sub("[REDACTED]", value)
    return {
        **fields,
        "status": str(item.get("status", "pending")),
        "classification": DataClass.CONFIDENTIAL.value,
    }


def _parse_eml(content: bytes) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(content)
    body_part = message.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        payload = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            extractor = _TextExtractor()
            extractor.feed(str(payload))
            body = " ".join(extractor.parts)
        else:
            body = str(payload)
    return {
        "subject": str(message.get("subject", "")),
        "sender": str(message.get("from", "")),
        "date": str(message.get("date", "")),
        "body": body,
        "status": "pending",
    }


class MailGetPendingTool(BaseTool):
    name = "mail.get_pending"
    data_class = DataClass.CONFIDENTIAL
    path_params = ("path",)

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()

    def run(self, params: dict[str, Any]) -> str:
        path = workspace_path(self.workspace, str(params["path"]))
        suffix = path.suffix.lower()
        if suffix == ".eml":
            messages = [_parse_eml(path.read_bytes())]
        elif suffix == ".json":
            content = path.read_text(encoding="utf-8")
            messages = json.loads(content)
            if not isinstance(messages, list):
                raise ValueError("El JSON debe contener una lista de notificaciones")
        else:
            content = path.read_text(encoding="utf-8")
            messages = [
                {"summary": line.strip()}
                for line in content.splitlines()
                if line.strip()
            ]
        pending = [
            sanitize_mail_item(message)
            for message in messages
            if isinstance(message, dict) and message.get("status", "pending") != "done"
        ]
        return json.dumps(pending, ensure_ascii=False)