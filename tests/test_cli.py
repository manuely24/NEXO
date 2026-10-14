from typer.testing import CliRunner

from nexo.interfaces.cli import app
from nexo.project.architect import ProjectPhaseResult
from nexo.project.store import ProjectSessionStore


def test_run_without_gemini_key_returns_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = CliRunner().invoke(app, ["run", "revisa el repositorio"])

    assert result.exit_code == 2
    assert "Configura GEMINI_API_KEY" in result.output


def test_project_requires_cloud_consent_before_creating_a_session(monkeypatch):
    from nexo.interfaces import cli

    def unexpected_runtime(**_kwargs):
        raise AssertionError("No debe iniciar Gemini sin consentimiento")

    monkeypatch.setattr(cli, "_runtime", unexpected_runtime)
    result = CliRunner().invoke(app, ["project", "organiza archivos"])

    assert result.exit_code == 2
    assert "--allow-cloud" in result.output


def test_project_next_refuses_to_skip_an_approval_phase(tmp_path, monkeypatch):
    from nexo.interfaces import cli

    monkeypatch.setattr(cli, "WORKSPACE", tmp_path)
    store = ProjectSessionStore(tmp_path / "data" / "project-sessions.db")
    session = store.create("organiza archivos", "auto")
    phase = ProjectPhaseResult.model_validate(
        {
            "phase": 1,
            "project_name": "file-organizer",
            "project_type": "python-cli",
            "title": "Diseño y control de daños",
            "summary": "Organizador local.",
            "problem": "Reduce clasificación manual.",
            "architecture": ["CLI"],
            "directory_tree": "file-organizer/\n  README.md",
            "risks": ["Permisos", "Archivos corruptos", "Nombres duplicados"],
        }
    )
    store.save_phase(session.id, phase)
    store.close()

    result = CliRunner().invoke(
        app,
        ["project-next", session.id, "--approve-phase", "3", "--allow-cloud"],
    )

    assert result.exit_code == 2
    assert "Debes aprobar la Fase 1" in result.output


def test_workspace_audit_cli_reports_without_cleanup(tmp_path, monkeypatch):
    from nexo.interfaces import cli

    monkeypatch.setattr(cli, "WORKSPACE", tmp_path)
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "marker.txt").write_text("environment", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["workspace-audit", "."])

    assert result.exit_code == 0
    assert '"actions_taken": []' in result.output
    assert '"path": ".venv"' in result.output
    assert (tmp_path / ".venv" / "marker.txt").is_file()
