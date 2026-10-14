"""Ejecución aprobada, acotada por tiempo y seguida de verificación."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from nexo.core.models import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    RiskLevel,
    VerificationStatus,
)
from nexo.events.log import EventLog
from nexo.policy.engine import PolicyEngine
from nexo.tools.base import ToolRegistry
from nexo.verifiers.base import Verification, VerifierRegistry


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        policy: PolicyEngine,
        verifiers: VerifierRegistry,
        event_log: EventLog,
        timeout_s: float = 10.0,
    ) -> None:
        self.registry = registry
        self.policy = policy
        self.verifiers = verifiers
        self.event_log = event_log
        self.timeout_s = timeout_s

    def execute(
        self,
        action: ActionRequest,
        *,
        explicit_approval: bool = False,
        authorized_data_sources: set[str] | None = None,
    ) -> ActionResult:
        self.event_log.append(
            "action_proposed",
            {"tool": action.tool, "risk_level": action.risk_level.name},
            correlation_id=action.id,
        )
        decision = self.policy.evaluate(
            action,
            explicit_approval=explicit_approval,
            authorized_data_sources=authorized_data_sources,
        )
        self.event_log.append(
            "policy_decision",
            {"tool": action.tool, "allowed": decision.allowed, "reason": decision.reason},
            correlation_id=action.id,
        )
        if not decision.allowed:
            action.transition(ActionStatus.DENIED)
            self.event_log.append(
                "action_denied", {"tool": action.tool, "reason": decision.reason}, action.id
            )
            return ActionResult(
                action_id=action.id,
                status=ActionStatus.DENIED,
                error=decision.reason,
                verification=VerificationStatus.UNVERIFIED,
            )

        if action.risk_level > RiskLevel.INFO or action.verifier is not None:
            try:
                if action.verifier is None:
                    raise KeyError("La acción requiere un verificador")
                self.verifiers.get(action.verifier)
            except KeyError as exc:
                action.transition(ActionStatus.DENIED)
                self.event_log.append(
                    "action_denied",
                    {"tool": action.tool, "reason": str(exc)},
                    action.id,
                )
                return ActionResult(
                    action_id=action.id,
                    status=ActionStatus.DENIED,
                    error=str(exc),
                    verification=VerificationStatus.UNVERIFIED,
                )

        action.transition(ActionStatus.APPROVED)
        self.event_log.append(
            "action_approved", {"tool": action.tool}, correlation_id=action.id
        )
        action.transition(ActionStatus.RUNNING)
        self.event_log.append(
            "action_started", {"tool": action.tool, "param_names": sorted(action.params)}, action.id
        )
        started = time.monotonic()
        try:
            output = self._run_with_timeout(action.tool, action.params)
            verification = self._verify(action, output)
            self.event_log.append(
                "action_verified",
                {"tool": action.tool, "verified": verification.verified},
                correlation_id=action.id,
            )
            action.transition(ActionStatus.SUCCEEDED)
            result = ActionResult(
                action_id=action.id,
                status=ActionStatus.SUCCEEDED,
                output=output,
                duration_s=time.monotonic() - started,
                verification=(
                    VerificationStatus.VERIFIED
                    if verification.verified
                    else VerificationStatus.UNVERIFIED
                ),
                verification_detail=verification.detail,
            )
        except Exception as exc:
            action.transition(ActionStatus.FAILED)
            result = ActionResult(
                action_id=action.id,
                status=ActionStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
                duration_s=time.monotonic() - started,
                verification=VerificationStatus.UNVERIFIED,
            )
        self.event_log.append(
            "action_finished",
            {
                "tool": action.tool,
                "status": result.status.value,
                "duration_s": result.duration_s,
                "output_length": len(result.output),
                "error": result.error,
                "verification": result.verification.value,
                "verification_detail": result.verification_detail,
            },
            action.id,
        )
        return result

    def _run_with_timeout(self, tool_name: str, params: dict[str, Any]) -> str:
        tool = self.registry.get(tool_name)
        outcome: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def invoke() -> None:
            try:
                outcome.put((True, tool.run(params)))
            except Exception as exc:
                outcome.put((False, exc))

        threading.Thread(target=invoke, daemon=True).start()
        try:
            succeeded, value = outcome.get(timeout=self.timeout_s)
        except queue.Empty as exc:
            raise TimeoutError(f"La herramienta excedió {self.timeout_s:.1f}s") from exc
        if not succeeded:
            raise value
        if not isinstance(value, str):
            raise TypeError("Las herramientas deben devolver str")
        return value

    def _verify(self, action: ActionRequest, output: str) -> Verification:
        if action.risk_level == RiskLevel.INFO and action.verifier is None:
            return Verification(True, "Acción informativa; no requiere verificador")
        if action.verifier is None:
            raise ValueError("La acción requiere un verificador")
        return self.verifiers.get(action.verifier).verify(action, output)