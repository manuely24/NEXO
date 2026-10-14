from typing import Any

from nexo.core.executor import Executor
from nexo.core.models import ActionRequest, ActionStatus, RiskLevel
from nexo.events.log import EventLog
from nexo.policy.engine import PolicyEngine
from nexo.tools.base import BaseTool, ToolRegistry
from nexo.verifiers.base import VerifierRegistry


class WriteStub(BaseTool):
    name = "write.stub"
    risk_level = RiskLevel.MODIFIES_FILES
    path_params = ("path",)

    def __init__(self):
        self.called = False

    def run(self, params: dict[str, Any]) -> str:
        self.called = True
        return "written"


def test_executor_denies_write_before_run_without_registered_verifier(tmp_path):
    tool = WriteStub()
    tools = ToolRegistry()
    tools.register(tool)
    verifiers = VerifierRegistry()
    event_log = EventLog(tmp_path / "events.db")
    executor = Executor(
        tools,
        PolicyEngine(tools, tmp_path),
        verifiers,
        event_log,
    )
    action = ActionRequest(
        tool=tool.name,
        params={"path": "data/file.txt"},
        risk_level=RiskLevel.MODIFIES_FILES,
        expected_outcome="archivo escrito",
        verifier="missing",
    )

    try:
        result = executor.execute(action, explicit_approval=True)
        assert result.status == ActionStatus.DENIED
        assert not tool.called
        assert event_log.read(correlation_id=action.id, kind="action_denied")
    finally:
        event_log.close()