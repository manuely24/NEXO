import json
from typing import Any

from fastapi.testclient import TestClient

from nexo.core.executor import Executor
from nexo.core.models import RiskLevel
from nexo.core.planner import Planner
from nexo.events.log import EventLog
from nexo.interfaces.api import create_app
from nexo.llm.base import LLMProvider
from nexo.policy.engine import PolicyEngine
from nexo.tools.academic_tools import AcademicGetDueTasksTool
from nexo.tools.base import BaseTool, ToolRegistry
from nexo.verifiers import FileExistsVerifier, VerifierRegistry


class MockProvider(LLMProvider):
    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, prompt: str) -> str:
        return self.response


class InfoTool(BaseTool):
    name = "test.info"

    def run(self, params: dict[str, Any]) -> str:
        return "información local"


class WriteTool(BaseTool):
    name = "test.write"
    risk_level = RiskLevel.MODIFIES_FILES
    path_params = ("path",)

    def __init__(self, workspace):
        self.workspace = workspace

    def run(self, params: dict[str, Any]) -> str:
        path = self.workspace / params["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("approved", encoding="utf-8")
        return str(path)


def make_client(tmp_path, provider):
    registry = ToolRegistry()
    registry.register(InfoTool())
    registry.register(WriteTool(tmp_path))
    registry.register(AcademicGetDueTasksTool(tmp_path / "data" / "tasks.db"))
    verifiers = VerifierRegistry()
    verifiers.register(FileExistsVerifier(tmp_path))
    event_log = EventLog(tmp_path / "events.db")
    executor = Executor(
        registry,
        PolicyEngine(registry, tmp_path),
        verifiers,
        event_log,
    )
    planner = Planner(registry, provider)
    app = create_app(planner, executor, event_log, workspace=tmp_path)
    return TestClient(app), event_log


def test_health_static_and_pending_endpoints(tmp_path):
    client, event_log = make_client(tmp_path, MockProvider('{"actions": []}'))
    try:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert "Nexo" in client.get("/").text
        assert client.get("/api/pending?upcoming=3").status_code == 200
        assert client.get("/api/pending?upcoming=-1").status_code == 422
    finally:
        event_log.close()


def test_run_executes_info_and_waits_for_write_decision(tmp_path):
    info_provider = MockProvider(
        json.dumps(
            {
                "actions": [
                    {
                        "tool": "test.info",
                        "params": {},
                        "expected_outcome": "leer información",
                    }
                ]
            }
        )
    )
    client, event_log = make_client(tmp_path, info_provider)
    try:
        response = client.post("/api/run", json={"message": "consulta local"})
        action = response.json()["actions"][0]
        assert action["status"] == "succeeded"
        assert action["verification"] == "verified"
    finally:
        event_log.close()


def test_run_handles_local_academic_request_without_llm(tmp_path):
    client, event_log = make_client(tmp_path, None)
    try:
        response = client.post(
            "/api/run",
            json={"message": "¿Qué tareas académicas tengo pendientes esta semana?"},
        )

        assert response.status_code == 200
        action = response.json()["actions"][0]
        assert action["tool"] == "academic.get_due_tasks"
        assert action["status"] == "succeeded"
        assert action["verification"] == "verified"
        assert action["output"] == "[]"
    finally:
        event_log.close()

    write_provider = MockProvider(
        json.dumps(
            {
                "actions": [
                    {
                        "tool": "test.write",
                        "params": {"path": "data/approved.txt"},
                        "expected_outcome": "crear archivo",
                        "verifier": "file_exists",
                    }
                ]
            }
        )
    )
    client, event_log = make_client(tmp_path, write_provider)
    try:
        pending = client.post("/api/run", json={"message": "crea archivo"}).json()["actions"][0]
        assert pending["status"] == "pending_approval"
        assert not (tmp_path / "data" / "approved.txt").exists()
        restored = client.get("/api/actions/pending").json()
        assert restored[0]["id"] == pending["id"]
        assert restored[0]["expected_outcome"] == "crear archivo"

        denied = client.post(
            f"/api/actions/{pending['id']}/decision", json={"approved": False}
        )
        assert denied.json()["status"] == "denied"
        assert client.get("/api/actions/pending").json() == []
        assert not (tmp_path / "data" / "approved.txt").exists()

        pending = client.post("/api/run", json={"message": "crea archivo"}).json()["actions"][0]
        approved = client.post(
            f"/api/actions/{pending['id']}/decision", json={"approved": True}
        )
        assert approved.json()["status"] == "succeeded"
        assert approved.json()["verification"] == "verified"
        assert (tmp_path / "data" / "approved.txt").exists()
    finally:
        event_log.close()


def test_websocket_streams_new_audit_events(tmp_path):
    client, event_log = make_client(tmp_path, MockProvider('{"actions": []}'))
    try:
        with client.websocket_connect("/ws") as websocket:
            assert websocket.receive_json() == {"type": "connected"}
            event_log.append("action_proposed", {"tool": "test.info"}, "action-1")
            message = websocket.receive_json()
            assert message["type"] == "event"
            assert message["event"]["kind"] == "action_proposed"
    finally:
        event_log.close()