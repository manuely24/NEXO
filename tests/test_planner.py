import json
from typing import Any

import pytest

from nexo.core.models import DataClass, Intent, RiskLevel
from nexo.core.planner import Planner
from nexo.llm.base import LLMProvider
from nexo.tools.base import BaseTool, ToolRegistry


class MockProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class InfoTool(BaseTool):
    name = "local.inspect"

    def run(self, params: dict[str, Any]) -> str:
        return "ok"


def make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(InfoTool())
    return registry


def test_planner_maps_multiple_actions_to_registered_tools():
    provider = MockProvider(
        json.dumps(
            {
                "actions": [
                    {
                        "tool": "local.inspect",
                        "params": {"kind": "git"},
                        "expected_outcome": "mostrar estado",
                        "verifier": None,
                    },
                    {
                        "tool": "local.inspect",
                        "params": {"kind": "academic"},
                        "expected_outcome": "mostrar tareas",
                        "verifier": None,
                    },
                ]
            }
        )
    )
    planner = Planner(make_registry(), provider)

    plan = planner.plan(Intent(text="Muestra git y mis tareas"))

    assert len(plan.actions) == 2
    assert all(action.tool == "local.inspect" for action in plan.actions)
    assert all(action.risk_level == RiskLevel.INFO for action in plan.actions)


def test_local_intent_is_omitted_from_provider_prompt():
    provider = MockProvider('{"actions": []}')
    planner = Planner(make_registry(), provider)
    secret_intent = "mi clave token=secret-value"

    planner.plan(Intent(text=secret_intent), data_class=DataClass.LOCAL)

    assert secret_intent not in provider.prompts[0]
    assert "[LOCAL DATA OMITTED]" in provider.prompts[0]
    assert "secret-value" not in provider.prompts[0]


def test_confidential_intent_is_omitted_without_explicit_permission():
    provider = MockProvider('{"actions": []}')
    planner = Planner(make_registry(), provider)

    planner.plan(Intent(text="private email text"), data_class=DataClass.CONFIDENTIAL)

    assert "private email text" not in provider.prompts[0]
    assert "[CONFIDENTIAL DATA OMITTED]" in provider.prompts[0]


def test_cloud_prompt_redacts_credentials_email_and_local_paths():
    provider = MockProvider('{"actions": []}')
    planner = Planner(make_registry(), provider)
    intent = Intent(
        text="token=ghp_secret contact me@example.com in C:\\Users\\me\\private.txt"
    )

    planner.plan(intent, data_class=DataClass.CLOUD_OK)

    prompt = provider.prompts[0]
    assert "ghp_secret" not in prompt
    assert "me@example.com" not in prompt
    assert "C:\\Users\\me\\private.txt" not in prompt


def test_planner_rejects_unregistered_tool():
    provider = MockProvider(
        '{"actions":[{"tool":"shell.exec","params":{},"expected_outcome":"run"}]}'
    )
    planner = Planner(make_registry(), provider)

    with pytest.raises(KeyError, match="no registrada"):
        planner.plan(Intent(text="ejecuta shell"))


def test_planner_rejects_invalid_json():
    planner = Planner(make_registry(), MockProvider("not json"))

    with pytest.raises(ValueError, match="JSON válido"):
        planner.plan(Intent(text="haz algo"))