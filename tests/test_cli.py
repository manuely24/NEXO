from typer.testing import CliRunner

from nexo.interfaces.cli import app


def test_run_without_gemini_key_returns_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    result = CliRunner().invoke(app, ["run", "revisa el repositorio"])

    assert result.exit_code == 2
    assert "Configura GEMINI_API_KEY" in result.output