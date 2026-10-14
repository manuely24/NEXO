"""API local de Nexo y canal WebSocket de auditoría en vivo."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from nexo.core.executor import Executor
from nexo.core.models import ActionRequest, ActionStatus, DataClass, Intent
from nexo.core.planner import Planner
from nexo.events.log import EventLog

STATIC_DIR = Path(__file__).parent / "static"


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    data_class: DataClass = DataClass.LOCAL


class DecisionRequest(BaseModel):
    approved: bool


def create_app(
    planner: Planner | None = None,
    executor: Executor | None = None,
    event_log: EventLog | None = None,
    *,
    workspace: str | Path | None = None,
    database: str | Path | None = None,
    use_llm: bool = False,
) -> FastAPI:
    if planner is None or executor is None or event_log is None:
        from nexo.interfaces.cli import _runtime

        planner, executor, event_log = _runtime(use_llm=use_llm)
    pending_actions: dict[str, ActionRequest] = {}
    app = FastAPI(title="Nexo local", docs_url=None, redoc_url=None)
    app.state.pending_actions = pending_actions
    app.state.event_log = event_log

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/pending")
    def pending(upcoming: int = 7) -> list[dict[str, str | int]]:
        if upcoming < 0:
            raise HTTPException(status_code=422, detail="upcoming no puede ser negativo")
        intent = Intent(text="Consultar tareas académicas próximas")
        action = planner.propose(
            intent,
            "academic.get_due_tasks",
            {"within_days": upcoming},
            "consultar tareas académicas próximas",
        ).actions[0]
        result = executor.execute(action)
        if not result.can_report_done():
            raise HTTPException(status_code=500, detail=result.error or result.verification_detail)
        try:
            decoded = json.loads(result.output)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail="Respuesta académica inválida") from exc
        if not isinstance(decoded, list) or any(not isinstance(task, dict) for task in decoded):
            raise HTTPException(status_code=500, detail="Respuesta académica con formato inválido")
        return cast(list[dict[str, str | int]], decoded)

    @app.get("/api/actions/pending")
    def list_pending_actions() -> list[dict[str, str]]:
        return [
            {
                "id": action.id,
                "tool": action.tool,
                "expected_outcome": action.expected_outcome,
                "risk": action.risk_level.name,
                "status": "pending_approval",
                "reason": executor.policy.evaluate(action).reason,
            }
            for action in pending_actions.values()
        ]

    @app.post("/api/run")
    def run(request: RunRequest) -> dict[str, object]:
        try:
            plan = planner.plan(
                Intent(text=request.message),
                data_class=request.data_class,
                allow_confidential=request.data_class == DataClass.CONFIDENTIAL,
            )
        except (RuntimeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        results: list[dict[str, object]] = []
        for action in plan.actions:
            decision = executor.policy.evaluate(action)
            if not decision.allowed and "aprobación explícita" in decision.reason:
                pending_actions[action.id] = action
                results.append(
                    {
                        "id": action.id,
                        "tool": action.tool,
                        "expected_outcome": action.expected_outcome,
                        "risk": action.risk_level.name,
                        "status": "pending_approval",
                        "reason": decision.reason,
                    }
                )
                continue
            result = executor.execute(action)
            results.append(
                {
                    "id": action.id,
                    "tool": action.tool,
                    "expected_outcome": action.expected_outcome,
                    "risk": action.risk_level.name,
                    "status": result.status.value,
                    "verification": result.verification.value,
                    "output": result.output,
                    "error": result.error,
                }
            )
        return {"plan_id": plan.id, "actions": results}

    @app.post("/api/actions/{action_id}/decision")
    def decide(action_id: str, request: DecisionRequest) -> dict[str, object]:
        action = pending_actions.pop(action_id, None)
        if action is None:
            raise HTTPException(status_code=404, detail="No hay una acción pendiente con ese id")
        if not request.approved:
            action.transition(ActionStatus.DENIED)
            event_log.append(
                "action_denied",
                {"tool": action.tool, "reason": "Denegada en la interfaz web"},
                correlation_id=action.id,
            )
            return {"id": action.id, "status": ActionStatus.DENIED.value}
        authorized_sources = {"github"} if action.tool.startswith("github.") else None
        result = executor.execute(
            action,
            explicit_approval=True,
            authorized_data_sources=authorized_sources,
        )
        return {
            "id": action.id,
            "status": result.status.value,
            "verification": result.verification.value,
            "output": result.output,
            "error": result.error,
        }

    @app.websocket("/ws")
    async def audit_stream(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        allowed_origins = {None, "http://localhost:8000", "http://127.0.0.1:8000"}
        if origin not in allowed_origins:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        def on_event(event: dict[str, object]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, event)

        unsubscribe = event_log.subscribe(on_event)
        try:
            await websocket.send_json({"type": "connected"})
            while True:
                await websocket.send_json({"type": "event", "event": await queue.get()})
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app