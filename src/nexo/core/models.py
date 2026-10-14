"""Modelos de dominio de Nexo (contrato central del sistema).

Separación INTENCIÓN -> PLAN -> ACCIÓN -> RESULTADO -> VERIFICACIÓN.
El LLM solo podrá *producir* estos objetos; nunca ejecuta nada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class RiskLevel(IntEnum):
    """Niveles de permiso 0-4. Los asigna código, no el LLM."""

    INFO = 0  # solo información
    REVERSIBLE = 1  # acciones reversibles
    MODIFIES_FILES = 2  # modifica archivos
    EXTERNAL = 3  # acciones externas (red, GitHub, correo)
    SENSITIVE = 4  # dinero, borrado, configuración crítica


class DataClass(StrEnum):
    """D11: qué puede salir hacia el proveedor del LLM."""

    LOCAL = "local"  # nunca sale de tu máquina (claves, tokens, finanzas)
    CONFIDENTIAL = "confidential"  # solo con autorización explícita (correo, documentos)
    CLOUD_OK = "cloud_ok"  # puede enviarse (código, consultas generales)


class AutonomyMode(IntEnum):
    """D14: grado de autonomía. Se configura, no se asume."""

    ASSISTANT = 1  # analiza y propone
    EXECUTOR = 2  # ejecuta acciones previamente autorizadas
    AUTOMATION = 3  # ejecuta automáticamente categorías definidas
    AGENT = 4  # encadena acciones y se corrige dentro de límites
    PERSONAL_SYSTEM = 5  # memoria + sensores + dispositivos (visión a largo plazo)


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    DENIED = "denied"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VerificationStatus(StrEnum):
    PENDING = "pending"  # aún no se comprobó
    VERIFIED = "verified"  # el efecto real fue comprobado
    UNVERIFIED = "unverified"  # no se pudo comprobar o la comprobación falló


class InvalidTransition(Exception):
    """Se intentó un cambio de estado no permitido."""


_ALLOWED: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PROPOSED: {ActionStatus.APPROVED, ActionStatus.DENIED},
    ActionStatus.APPROVED: {ActionStatus.RUNNING},
    ActionStatus.RUNNING: {ActionStatus.SUCCEEDED, ActionStatus.FAILED},
    ActionStatus.DENIED: set(),
    ActionStatus.SUCCEEDED: set(),
    ActionStatus.FAILED: set(),
}


class Intent(BaseModel):
    """Lo que el humano pidió, tal cual."""

    id: str = Field(default_factory=new_id)
    text: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utcnow)


class ActionRequest(BaseModel):
    """Una acción propuesta. Pasa por política -> ejecución -> verificación."""

    id: str = Field(default_factory=new_id)
    tool: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel
    expected_outcome: str = Field(min_length=1)
    verifier: str | None = None  # nombre del verificador; obligatorio salvo INFO
    data_class: DataClass = DataClass.LOCAL  # por defecto, lo más restrictivo
    from_untrusted_content: bool = False  # D5: derivada de correo/web/README
    status: ActionStatus = ActionStatus.PROPOSED
    created_at: datetime = Field(default_factory=utcnow)

    def model_post_init(self, __context: Any) -> None:
        if self.risk_level > RiskLevel.INFO and not self.verifier:
            raise ValueError(
                f"La herramienta '{self.tool}' (riesgo {self.risk_level.name}) "
                "requiere un verificador."
            )

    def transition(self, new: ActionStatus) -> None:
        if new not in _ALLOWED[self.status]:
            raise InvalidTransition(f"{self.status.value} -> {new.value} no está permitido")
        self.status = new


class ActionResult(BaseModel):
    action_id: str
    status: ActionStatus
    output: str = ""
    error: str | None = None
    duration_s: float = 0.0
    verification: VerificationStatus = VerificationStatus.PENDING
    verification_detail: str = ""

    def can_report_done(self) -> bool:
        """Nexo solo puede decir 'listo' si tuvo éxito Y se verificó."""
        return (
            self.status == ActionStatus.SUCCEEDED
            and self.verification == VerificationStatus.VERIFIED
        )


class Plan(BaseModel):
    id: str = Field(default_factory=new_id)
    intent_id: str
    actions: list[ActionRequest] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
