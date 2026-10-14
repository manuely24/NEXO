from typing import Any

from nexo.core.models import ActionRequest, DataClass, RiskLevel
from nexo.policy.engine import PolicyEngine
from nexo.tools.base import BaseTool, ToolRegistry


class StubTool(BaseTool):
    name = "stub"
    path_params = ("path",)

    def run(self, params: dict[str, Any]) -> str:
        return "ok"


class ExternalTool(StubTool):
    name = "remote"
    external = True
    risk_level = RiskLevel.EXTERNAL
    data_class = DataClass.CLOUD_OK
    path_params = ()


def build_policy(tmp_path, *tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return PolicyEngine(registry, tmp_path)


def test_rejects_paths_outside_workspace(tmp_path):
    policy = build_policy(tmp_path, StubTool())
    action = ActionRequest(
        tool="stub",
        params={"path": str(tmp_path.parent / "outside.txt")},
        risk_level=RiskLevel.INFO,
        expected_outcome="leer archivo",
    )

    result = policy.evaluate(action, explicit_approval=True)

    assert not result.allowed
    assert "fuera del workspace" in result.reason


def test_local_data_never_goes_to_external_tool(tmp_path):
    policy = build_policy(tmp_path, ExternalTool())
    action = ActionRequest(
        tool="remote",
        params={},
        risk_level=RiskLevel.EXTERNAL,
        expected_outcome="consulta remota",
        verifier="noop",
        data_class=DataClass.LOCAL,
    )

    result = policy.evaluate(action, explicit_approval=True)

    assert not result.allowed
    assert "LOCAL" in result.reason


def test_external_action_requires_explicit_approval(tmp_path):
    policy = build_policy(tmp_path, ExternalTool())
    action = ActionRequest(
        tool="remote",
        params={},
        risk_level=RiskLevel.EXTERNAL,
        expected_outcome="consulta remota",
        verifier="noop",
        data_class=DataClass.CLOUD_OK,
    )

    result = policy.evaluate(action)

    assert not result.allowed
    assert "aprobación explícita" in result.reason


def test_confidential_external_data_requires_source_authorization(tmp_path):
    policy = build_policy(tmp_path, ExternalTool())
    action = ActionRequest(
        tool="remote",
        params={"source": "github"},
        risk_level=RiskLevel.EXTERNAL,
        expected_outcome="consulta privada",
        verifier="noop",
        data_class=DataClass.CONFIDENTIAL,
    )

    denied = policy.evaluate(action, explicit_approval=True)
    allowed = policy.evaluate(
        action,
        explicit_approval=True,
        authorized_data_sources={"github"},
    )

    assert not denied.allowed
    assert "aprobación explícita" in denied.reason
    assert allowed.allowed