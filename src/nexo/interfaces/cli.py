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
from nexo.llm.privacy import sanitize_for_llm
from nexo.policy.engine import PolicyEngine
from nexo.project.architect import ProjectArchitect, ProjectPhaseResult, assemble_blueprint
from nexo.project.store import ProjectSessionStore
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
from nexo.tools.project_tools import ProjectScaffoldTool
from nexo.tools.workspace_audit import WorkspaceAuditTool
from nexo.tutor.english import EnglishCorrectTextTool, EnglishExplainGrammarTool
from nexo.verifiers import (
    AcademicImportVerifier,
    AcademicTaskExistsVerifier,
    FileContainsVerifier,
    FileExistsVerifier,
    GitStatusVerifier,
    JsonListVerifier,
    JsonObjectVerifier,
    ProjectScaffoldVerifier,
    VerifierRegistry,
)

app = typer.Typer(no_args_is_help=True, help="Asistente local con políticas deterministas.")
WORKSPACE = Path(os.environ.get("NEXO_WORKSPACE", Path.cwd())).resolve()
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
        WorkspaceAuditTool(WORKSPACE),
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
        ProjectScaffoldTool(WORKSPACE),
    ):
        registry.register(tool)

    verifiers = VerifierRegistry()
    for verifier in (
        FileExistsVerifier(WORKSPACE),
        FileContainsVerifier(WORKSPACE),
        GitStatusVerifier(WORKSPACE),
        JsonListVerifier(),
        JsonObjectVerifier(),
        ProjectScaffoldVerifier(WORKSPACE),
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


def _print_project_phase(session_id: str, result: ProjectPhaseResult) -> None:
    typer.echo(f"Sesión: {session_id}")
    typer.echo(f"FASE {result.phase}/4 · {result.title}")
    typer.echo(f"Proyecto: {result.project_name} ({result.project_type})")
    typer.echo(result.summary)

    if result.phase == 1:
        typer.echo("\nÁrbol de directorios")
        typer.echo(result.directory_tree)
        typer.echo("\nArquitectura")
        for item in result.architecture:
            typer.echo(f"- {item}")
        typer.echo("\nRiesgos y mitigaciones")
        for risk in result.risks:
            typer.echo(f"- {risk}")
    else:
        if result.problem:
            typer.echo(f"\nProblema: {result.problem}")
        if result.directory_tree:
            typer.echo("\nÁrbol de directorios")
            typer.echo(result.directory_tree)
        if result.architecture:
            typer.echo("\nArquitectura")
            for item in result.architecture:
                typer.echo(f"- {item}")
        if result.files:
            typer.echo("\nArchivos de esta fase")
            for generated_file in result.files:
                typer.echo(f"\n### {generated_file.path}")
                language = Path(generated_file.path).suffix.lstrip(".")
                typer.echo(f"```{language}\n{generated_file.content}\n```")
        if result.dependencies:
            typer.echo("\nDependencias")
            for dependency in result.dependencies:
                typer.echo(f"- {dependency}")
        if result.windows_installation:
            typer.echo("\nInstalación Windows 11")
            for command in result.windows_installation:
                typer.echo(f"  {command}")
        if result.quickstart:
            typer.echo("\nUso rápido")
            for command in result.quickstart:
                typer.echo(f"  {command}")
        if result.test_commands:
            typer.echo("\nValidación sugerida")
            for command in result.test_commands:
                typer.echo(f"  {command}")
        if result.git_commands:
            typer.echo("\nComandos Git sugeridos; Nexo no los ejecuta")
            for command in result.git_commands:
                typer.echo(f"  {command}")
        if result.risks:
            typer.echo("\nRiesgos pendientes")
            for risk in result.risks:
                typer.echo(f"- {risk}")


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
        typer.echo(f"  {task['due_date']} | {task['subject']} | {task['title']} [{task['status']}]")

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


@app.command("workspace-audit")
def workspace_audit(
    path: str = typer.Argument(".", help="Carpeta relativa al workspace actual."),
) -> None:
    """Audita cachés, .gitignore y ajustes VS Code sin borrar ni editar nada."""
    output = _report(
        _run(
            "workspace.audit",
            {"path": path},
            "auditar el workspace local sin modificarlo",
        )
    )
    typer.echo(json.dumps(json.loads(output), indent=2, ensure_ascii=False))


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


@app.command("project")
def generate_project(
    requirement: str = typer.Argument(..., help="Requerimiento funcional del nuevo proyecto."),
    project_type: str = typer.Option(
        "auto",
        "--type",
        help="Tipo: auto, python-cli, static-web, express-api o express-mysql.",
    ),
    allow_cloud: bool = typer.Option(
        False,
        "--allow-cloud",
        help="Autoriza enviar el requerimiento redactado a Gemini para la Fase 1.",
    ),
) -> None:
    """Analiza el requerimiento y entrega exclusivamente la Fase 1."""
    if not allow_cloud:
        typer.echo(
            "La Fase 1 requiere Gemini. Revisa el requerimiento y repite con --allow-cloud "
            "si autorizas enviar su versión redactada.",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        planner, executor, event_log = _runtime(use_llm=True)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    try:
        if planner.provider is None:
            typer.echo("No hay proveedor LLM disponible para analizar el proyecto.", err=True)
            raise typer.Exit(code=2)

        safe_requirement = sanitize_for_llm(requirement, DataClass.CLOUD_OK)
        architect = ProjectArchitect(planner.provider)
        result = architect.generate_phase(safe_requirement, 1, project_type)
        store = ProjectSessionStore(WORKSPACE / "data" / "project-sessions.db")
        try:
            session = store.create(safe_requirement, result.project_type)
            session = store.save_phase(session.id, result)
            _print_project_phase(session.id, result)
            typer.echo(
                f"\nNexo se detiene aquí. Revisa la Fase 1; para avanzar luego: "
                f"nexo project-next {session.id} --approve-phase 1 --allow-cloud"
            )
        finally:
            store.close()
    finally:
        event_log.close()


@app.command("project-next")
def project_next(
    session_id: str = typer.Argument(..., help="Id devuelto por nexo project."),
    approve_phase: int = typer.Option(..., "--approve-phase", min=1, max=3),
    allow_cloud: bool = typer.Option(False, "--allow-cloud"),
    feedback: str = typer.Option("", "--feedback", help="Comentarios para la siguiente fase."),
) -> None:
    """Avanza una sola fase y solo tras aprobar explícitamente la anterior."""
    if not allow_cloud:
        typer.echo("Cada fase que usa Gemini requiere --allow-cloud.", err=True)
        raise typer.Exit(code=2)

    data_dir = WORKSPACE / "data"
    store = ProjectSessionStore(data_dir / "project-sessions.db")
    try:
        session = store.get(session_id)
        expected_approval = session.next_phase - 1
        if expected_approval < 1:
            typer.echo("La Fase 1 todavía no está guardada.", err=True)
            raise typer.Exit(code=2)
        if session.next_phase > 4:
            typer.echo("Las cuatro fases ya están completas; puedes revisar y aplicar el scaffold.")
            return
        if approve_phase != expected_approval:
            typer.echo(
                f"Debes aprobar la Fase {expected_approval}; no se permite saltar etapas.",
                err=True,
            )
            raise typer.Exit(code=2)
    finally:
        store.close()

    try:
        planner, _executor, event_log = _runtime(use_llm=True)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    try:
        if planner.provider is None:
            typer.echo("No hay proveedor LLM disponible para continuar.", err=True)
            raise typer.Exit(code=2)

        store = ProjectSessionStore(data_dir / "project-sessions.db")
        try:
            session = store.get(session_id)
            result = ProjectArchitect(planner.provider).generate_phase(
                session.requirement,
                session.next_phase,
                session.project_type,
                previous_phases=list(session.phases),
                feedback=feedback,
            )
            session = store.save_phase(session.id, result)
            _print_project_phase(session.id, result)
            if session.next_phase <= 4:
                typer.echo(
                    f"\nRevisa esta entrega. Para avanzar: nexo project-next {session.id} "
                    f"--approve-phase {result.phase} --allow-cloud"
                )
            else:
                typer.echo(
                    f"\nFases completas. Revisa antes de aplicar: nexo project-apply "
                    f"{session.id} --target proyectos/{result.project_name} --approve"
                )
        finally:
            store.close()
    finally:
        event_log.close()


@app.command("project-status")
def project_status(session_id: str = typer.Argument(...)) -> None:
    """Muestra el avance local de una sesión sin contactar a Gemini."""
    store = ProjectSessionStore(WORKSPACE / "data" / "project-sessions.db")
    try:
        session = store.get(session_id)
        typer.echo(f"Sesión: {session.id}")
        typer.echo(f"Estado: {session.status}")
        typer.echo(f"Tipo: {session.project_type}")
        saved_phases = ", ".join(str(phase.phase) for phase in session.phases)
        typer.echo(f"Fases guardadas: {saved_phases or 'ninguna'}")
        next_phase = str(session.next_phase) if session.next_phase <= 4 else "aplicar scaffold"
        typer.echo(f"Siguiente fase: {next_phase}")
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    finally:
        store.close()


@app.command("project-apply")
def project_apply(
    session_id: str = typer.Argument(...),
    target: str = typer.Option(..., "--target", help="Destino nuevo relativo al workspace."),
    approve: bool = typer.Option(False, "--approve", help="Aprueba escribir los archivos."),
) -> None:
    """Escribe el proyecto completo solo después de cuatro fases y aprobación explícita."""
    store = ProjectSessionStore(WORKSPACE / "data" / "project-sessions.db")
    try:
        session = store.get(session_id)
        if session.next_phase != 5:
            typer.echo("Completa y revisa las cuatro fases antes de aplicar archivos.", err=True)
            raise typer.Exit(code=2)
        blueprint = assemble_blueprint(list(session.phases))
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    finally:
        store.close()

    typer.echo(f"Destino: {target}")
    typer.echo(f"Archivos: {len(blueprint.files)}")
    for generated_file in blueprint.files:
        typer.echo(f"- {generated_file.path}")
    if not approve:
        typer.echo("No se escribió nada. Repite con --approve después de revisar el listado.")
        return

    output = _report(
        _run(
            "project.scaffold",
            {"target": target, "blueprint": blueprint.model_dump(mode="json")},
            "crear y verificar el scaffold aprobado",
            verifier="project_scaffold",
            approved=True,
        )
    )
    typer.echo(output)
    typer.echo("Los comandos Git de la Fase 4 son sugerencias; Nexo no los ejecutó.")


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
