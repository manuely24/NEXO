"""Convierte una intención estructurada en acciones propuestas, nunca ejecuta."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from nexo.core.models import ActionRequest, DataClass, Intent, Plan
from nexo.llm.base import LLMProvider
from nexo.llm.privacy import sanitize_for_llm
from nexo.tools.base import ToolRegistry


class Planner:
    def __init__(self, registry: ToolRegistry, provider: LLMProvider | None = None) -> None:
        self.registry = registry
        self.provider = provider

    def plan(
        self,
        intent: Intent,
        *,
        data_class: DataClass = DataClass.LOCAL,
        allow_confidential: bool = False,
    ) -> Plan:
        if self.provider is None:
            return self._plan_offline(intent)
        tool_specs = []
        for name in self.registry.names():
            tool = self.registry.get(name)
            tool_specs.append(
                {
                    "name": name,
                    "risk_level": tool.risk_level.name,
                    "data_class": tool.data_class.value,
                    "params": list(tool.path_params),
                }
            )
        safe_intent = sanitize_for_llm(
            intent.text,
            data_class,
            allow_confidential=allow_confidential,
        )
        prompt = (
            "Convierte la intención en JSON solamente, con la forma "
            '{"actions":[{"tool":"...","params":{},"expected_outcome":"...",'
            '"verifier":null}]}. Usa solo herramientas del catálogo. No incluyas campos '
            "de riesgo ni clasificación: el sistema los determina. Máximo 8 acciones. "
            "No inventes rutas absolutas; usa rutas relativas al workspace. "
            f"Intención: {safe_intent}\nCatálogo: {json.dumps(tool_specs, ensure_ascii=False)}"
        )
        response = self.provider.generate(prompt)
        try:
            payload = json.loads(response)
        except json.JSONDecodeError as exc:
            raise ValueError("El proveedor devolvió un plan que no es JSON válido") from exc
        if isinstance(payload, dict):
            proposals = payload.get("actions")
        else:
            proposals = payload
        if not isinstance(proposals, list) or len(proposals) > 8:
            raise ValueError("El plan debe contener una lista de hasta 8 acciones")

        actions: list[ActionRequest] = []
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError("Cada acción propuesta debe ser un objeto JSON")
            tool_name = proposal.get("tool")
            params = proposal.get("params", {})
            expected = proposal.get("expected_outcome")
            verifier = proposal.get("verifier")
            if not isinstance(tool_name, str) or not isinstance(params, dict):
                raise ValueError("Cada acción requiere tool y params válidos")
            if not isinstance(expected, str) or not expected.strip():
                raise ValueError("Cada acción requiere expected_outcome")
            if verifier is not None and not isinstance(verifier, str):
                raise ValueError("verifier debe ser texto o null")
            registered_tool = self.registry.get(tool_name)
            if registered_tool.external and registered_tool.data_class == DataClass.CONFIDENTIAL:
                params.setdefault("source", tool_name.split(".", maxsplit=1)[0])
            actions.append(
                self.propose(
                    intent,
                    tool_name,
                    params,
                    expected,
                    verifier=verifier,
                ).actions[0]
            )
        return Plan(intent_id=intent.id, actions=actions)

    def _plan_offline(self, intent: Intent) -> Plan:
        normalized = unicodedata.normalize("NFKD", intent.text.lower())
        text = "".join(char for char in normalized if not unicodedata.combining(char))
        words = set(re.findall(r"[a-z0-9]+", text))
        proposals: list[tuple[str, dict[str, Any], str, str | None]] = []

        if words.intersection({"git", "repo", "repositorio", "repository"}):
            if words.intersection({"estado", "status"}) or not words.intersection(
                {"cambio", "cambios", "diff", "diferencia", "diferencias"}
            ):
                proposals.append(("git.status", {}, "consultar estado de Git", "git_status"))
            if words.intersection({"cambio", "cambios", "diff", "diferencia", "diferencias"}):
                proposals.append(("git.diff", {}, "consultar cambios de Git", None))
        elif words.intersection({"tarea", "tareas", "entrega", "entregas", "moodle", "campusland"}):
            proposals.append(
                ("academic.get_due_tasks", {"within_days": 7}, "consultar próximas entregas", None)
            )
        elif words.intersection({"ingles", "english", "gramatica", "grammar"}):
            topics = ("present perfect", "past simple", "present simple", "articles")
            topic = next((value for value in topics if set(value.split()).issubset(words)), None)
            if topic is not None:
                proposals.append(
                    (
                        "english.explain_grammar",
                        {"topic": topic},
                        f"explicar {topic}",
                        None,
                    )
                )

        available = set(self.registry.names())
        actions = [
            self.propose(intent, tool, params, outcome, verifier=verifier).actions[0]
            for tool, params, outcome, verifier in proposals
            if tool in available
        ]
        return Plan(intent_id=intent.id, actions=actions)

    def propose(
        self,
        intent: Intent,
        tool_name: str,
        params: dict[str, Any],
        expected_outcome: str,
        verifier: str | None = None,
        from_untrusted_content: bool = False,
    ) -> Plan:
        tool = self.registry.get(tool_name)
        action = ActionRequest(
            tool=tool.name,
            params=params,
            risk_level=tool.risk_level,
            expected_outcome=expected_outcome,
            verifier=verifier,
            data_class=tool.data_class,
            from_untrusted_content=from_untrusted_content,
        )
        return Plan(intent_id=intent.id, actions=[action])