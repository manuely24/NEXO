"""CLI de Nexo; todas las acciones pasan por política, executor y auditoría."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from nexo.core.executor import Executor
from nexo.core.models import ActionResult, DataClass, Intent
from nexo.core.planner import Planner
from nexo.events.log import EventLog
from nexo.llm.gemini_provider import GeminiProvider
from nexo.policy.engine import PolicyEngine
from nexo.tools.academic_tools import (
    AcademicAddTaskTool,
    AcademicGetDueTasksTool,
    AcademicImportTasksTool,
)
from nexo.tools.base import ToolRegistry
from nexo.tools.fs_tools import FsListTool, FsReadTool, FsWriteTool
from nexo.tools.git_tools import GitCommitPrepTool, GitDiffTool, GitPushTool, GitStatusTool
from nexo.tools.github_tools import (
    GitHubDraftIssueTool,
    GitHubDraftPullRequestTool,
    GitHubListIssuesTool,
    GitHubListPullRequestsTool,
)
from nexo.tools.mail_tools import MailGetPendingTool
from nexo.tutor.english import EnglishCorrectTextTool, EnglishExplainGrammarTool
from nexo.verifiers import (
    AcademicImportVerifier,
    AcademicTaskExistsVerifier,
    FileContainsVerifier,
    FileExistsVerifier,
    GitStatusVerifier,
    JsonListVerifier,
    JsonObjectVerifier,
    VerifierRegistry,
)

app = typer.Typer(no_args_is_help=True, help="Asistente local con políticas deterministas.")
WORKSPACE = Path(__file__).resolve().parents[3]
DATABASE = WORKSPACE / "data" / "campusland.db"


def _runtime(use_llm: bool = False) -> tuple[Planner, Executor, EventLog]:
    provider = GeminiProvider() if use_llm else None
    data_dir = WORKSPACE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    registry = ToolRegistry()
    for tool in (
        FsReadTool(WORKSPACE),
        FsWriteTool(WORKSPACE),
        FsListTool(WORKSPACE),
        GitStatusTool(WORKSPACE),
        GitDiffTool(WORKSPACE),
        GitCommitPrepTool(WORKSPACE),
        GitPushTool(WORKSPACE),
        GitHubListIssuesTool(WORKSPACE),
        GitHubListPullRequestsTool(WORKSPACE),
        GitHubDraftPullRequestTool(WORKSPACE),
        GitHubDraftIssueTool(data_dir / "github-drafts"),
        MailGetPendingTool(WORKSPACE),
        AcademicGetDueTasksTool(DATABASE),
        AcademicAddTaskTool(DATABASE),
        AcademicImportTasksTool(DATABASE, WORKSPACE),
        EnglishExplainGrammarTool(),
        EnglishCorrectTextTool(),
    ):
        registry.register(tool)

    verifiers = VerifierRegistry()
    for verifier in (
        FileExistsVerifier(WORKSPACE),
        FileContainsVerifier(WORKSPACE),
        GitStatusVerifier(WORKSPACE),
        JsonListVerifier(),
        JsonObjectVerifier(),
        AcademicTaskExistsVerifier(DATABASE),
        AcademicImportVerifier(DATABASE),
    ):
        verifiers.register(verifier)
    event_log = EventLog(data_dir / "nexo-events.db")
    policy = PolicyEngine(registry, WORKSPACE)
    return Planner(registry, provider), Executor(registry, policy, verifiers, event_log), event_log


def _run(
    tool: str,
    params: dict[str, Any],
    expected_outcome: str,
    *,
    verifier: str | None = None,
    approved: bool = False,
    authorized_sources: set[str] | None = None,
    intent_text: str | None = None,
) -> ActionResult:
    planner, executor, event_log = _runtime()
    try:
        intent = Intent(text=intent_text or expected_outcome)
        plan = planner.propose(intent, tool, params, expected_outcome, verifier=verifier)
        return executor.execute(
            plan.actions[0],
            explicit_approval=approved,
            authorized_data_sources=authorized_sources,
        )
    finally:
        event_log.close()


def _report(result: ActionResult) -> str:
    if result.status.value != "succeeded":
        message = result.error or result.verification_detail
        typer.echo(f"Acción {result.status.value}: {message}", err=True)
        raise typer.Exit(code=2)
    if not result.can_report_done():
        typer.echo(f"Resultado no verificado: {result.verification_detail}", err=True)
        raise typer.Exit(code=2)
    return result.output


@app.command()
def pending(
    upcoming: int = typer.Option(
        7, "--upcoming", "--within-days", min=0, help="Días hacia adelante para tareas académicas."
    ),
    approve_github: bool = typer.Option(
        False,
        "--approve-github",
        help="Autoriza consultar issues/PRs del repo privado configurado en GitHub.",
    ),
) -> None:
    """Muestra tareas académicas y, con aprobación, issues/PRs asignados."""
    academic = _report(
        _run(
            "academic.get_due_tasks",
            {"within_days": upcoming},
            "consultar tareas académicas",
        )
    )
    tasks = json.loads(academic)
    typer.echo("Pendientes académicos")
    if not tasks:
        typer.echo("  No hay tareas próximas.")
    for task in tasks:
        typer.echo(
            f"  {task['due_date']} | {task['subject']} | {task['title']} [{task['status']}]"
        )

    if not approve_github:
        typer.echo("GitHub: omitido. Usa --approve-github para autorizar la consulta externa.")
        return
    issues = _report(
        _run(
            "github.list_issues",
            {"source": "github"},
            "consultar issues y PRs asignados",
            verifier="json_list",
            approved=True,
            authorized_sources={"github"},
        )
    )
    typer.echo("Pendientes de GitHub")
    for issue in json.loads(issues):
        kind = "PR" if issue["is_pull_request"] else "Issue"
        typer.echo(f"  #{issue['number']} {kind}: {issue['title']} - {issue['url']}")
    pull_requests = _report(
        _run(
            "github.list_pull_requests",
            {"source": "github"},
            "consultar pull requests abiertas",
            verifier="json_list",
            approved=True,
            authorized_sources={"github"},
        )
    )
    typer.echo("Pull requests abiertas")
    for pull_request in json.loads(pull_requests):
        draft = " [draft]" if pull_request["draft"] else ""
        typer.echo(
            f"  #{pull_request['number']}: {pull_request['title']}{draft} - {pull_request['url']}"
        )


@app.command("check-repo")
def check_repo() -> None:
    """Inspecciona cambios locales del workspace actual."""
    output = _report(
        _run(
            "git.status",
            {},
            "inspeccionar estado local del repositorio",
            verifier="git_status",
        )
    )
    typer.echo(output or "Working tree limpio")


@app.command()
def english(text: str = typer.Argument(..., help="Texto en inglés que quieres revisar.")) -> None:
    """Revisa un texto en inglés con orientación A2.4/B1."""
    output = _report(
        _run(
            "english.correct_text",
            {"text": text},
            "revisar texto en inglés",
            intent_text=f"Revisar inglés: {text}",
        )
    )
    typer.echo(output)


@app.command("explain-grammar")
def explain_grammar(
    topic: str = typer.Argument(..., help="Tema gramatical, por ejemplo present simple."),
) -> None:
    """Explica un tema gramatical del nivel A2.4/B1."""
    output = _report(
        _run(
            "english.explain_grammar",
            {"topic": topic},
            "explicar gramática inglesa",
        )
    )
    typer.echo(output)


@app.command("add-task")
def add_task(
    title: str = typer.Argument(...),
    subject: str = typer.Option(..., "--subject"),
    due: str = typer.Option(..., "--due", help="Fecha ISO: AAAA-MM-DD."),
    approve: bool = typer.Option(False, "--approve", help="Aprueba guardar la tarea localmente."),
) -> None:
    """Guarda una tarea académica en SQLite local."""
    output = _report(
        _run(
            "academic.add_task",
            {"title": title, "subject": subject, "due_date": due},
            "guardar tarea académica",
            verifier="academic_task_exists",
            approved=approve,
        )
    )
    typer.echo(f"Tarea guardada con id {output}.")


@app.command("mail-pending")
def mail_pending(
    path: str = typer.Argument(..., help="Ruta a resumen .txt o lista .json local."),
) -> None:
    """Lee notificaciones locales como datos CONFIDENTIAL."""
    output = _report(
        _run(
            "mail.get_pending",
            {"path": path},
            "leer pendientes de un resumen local",
        )
    )
    typer.echo(output)


@app.command("git-diff")
def git_diff() -> None:
    """Muestra diferencias de archivos seguidos dentro del workspace."""
    output = _report(_run("git.diff", {}, "consultar diferencias Git locales"))
    typer.echo(output or "Sin diferencias en archivos seguidos")


@app.command("commit-prep")
def commit_prep(
    kind: str = typer.Option(..., "--type"),
    summary: str = typer.Option(..., "--summary"),
    scope: str = typer.Option("", "--scope"),
) -> None:
    """Propone un mensaje estructurado sin crear el commit ni hacer push."""
    output = _report(
        _run(
            "git.commit_prep",
            {"type": kind, "scope": scope, "summary": summary},
            "preparar mensaje de commit",
        )
    )
    typer.echo(output)


@app.command("run")
def run_intent(
    message: str = typer.Argument(..., help="Solicitud en lenguaje natural."),
    data_class: Annotated[
        DataClass,
        typer.Option("--data-class", help="Clasificación: local, confidential o cloud_ok."),
    ] = DataClass.LOCAL,
    approve: bool = typer.Option(
        False, "--approve", help="Aprueba todas las acciones que lo requieran."
    ),
) -> None:
    """Planifica y ejecuta una solicitud mediante Gemini y el flujo seguro."""
    try:
        planner, executor, event_log = _runtime(use_llm=True)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    try:
        plan = planner.plan(
            Intent(text=message),
            data_class=data_class,
            allow_confidential=data_class == DataClass.CONFIDENTIAL,
        )
        if not plan.actions:
            typer.echo("No se propusieron acciones.")
            return
        for action in plan.actions:
            decision = executor.policy.evaluate(action)
            explicit_approval = False
            if not decision.allowed and "aprobación explícita" in decision.reason:
                typer.echo(
                    f"\nAcción: {action.tool} ({action.risk_level.name})"
                    f"\nResultado esperado: {action.expected_outcome}"
                )
                explicit_approval = approve or (
                    sys.stdin.isatty() and typer.confirm("¿Aprobar esta acción?", default=False)
                )
            result = executor.execute(
                action,
                explicit_approval=explicit_approval,
                authorized_data_sources={"github"} if action.tool.startswith("github.") else None,
            )
            typer.echo(f"\n{action.tool}: {result.status.value}")
            if result.output:
                typer.echo(result.output)
            if result.error:
                typer.echo(result.error, err=True)
            if result.verification_detail:
                typer.echo(f"Verificación: {result.verification_detail}")
    finally:
        event_log.close()


@app.command("import-tasks")
def import_tasks(
    path: str = typer.Argument(..., help="Archivo .json o .csv dentro del workspace."),
    approve: bool = typer.Option(False, "--approve", help="Aprueba la importación local."),
) -> None:
    """Importa tareas exportadas de Campusland/Moodle."""
    output = _report(
        _run(
            "academic.import_tasks",
            {"path": path},
            "importar tareas académicas",
            verifier="academic_import",
            approved=approve,
        )
    )
    typer.echo(f"Tareas importadas: {output}")


@app.command("github-draft-issue")
def github_draft_issue(
    title: str = typer.Argument(...),
    body: str = typer.Option("", "--body"),
    approve: bool = typer.Option(False, "--approve", help="Aprueba guardar el borrador local."),
) -> None:
    """Guarda localmente un borrador de issue; no lo publica en GitHub."""
    output = _report(
        _run(
            "github.draft_issue",
            {"title": title, "body": body},
            "guardar borrador local de issue",
            verifier="json_object",
            approved=approve,
        )
    )
    typer.echo(output)


@app.command("github-draft-pr")
def github_draft_pr(
    title: str = typer.Argument(...),
    head: str = typer.Option(..., "--head"),
    base: str = typer.Option(..., "--base"),
    body: str = typer.Option("", "--body"),
    approve: bool = typer.Option(False, "--approve", help="Aprueba crear un PR draft remoto."),
) -> None:
    """Crea un PR draft remoto solo con aprobación explícita."""
    output = _report(
        _run(
            "github.draft_pull_request",
            {"title": title, "head": head, "base": base, "body": body},
            "crear borrador de pull request en GitHub",
            verifier="json_object",
            approved=approve,
        )
    )
    typer.echo(output)


@app.command("ui")
def ui() -> None:
    """Levanta el panel local en http://localhost:8000."""
    import uvicorn

    from nexo.interfaces.api import create_app

    use_llm = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if not use_llm:
        typer.echo(
            "Modo local activo: Git, tareas académicas e inglés funcionan sin Gemini. "
            "Configura una API key para solicitudes abiertas.",
            err=True,
        )
    typer.echo("Nexo local: http://localhost:8000")
    uvicorn.run(create_app(use_llm=use_llm), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    app()