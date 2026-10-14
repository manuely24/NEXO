import pytest

from nexo.project.architect import ProjectPhaseResult, assemble_blueprint
from nexo.project.store import ProjectSessionStore


def phase_one() -> ProjectPhaseResult:
    return ProjectPhaseResult.model_validate(
        {
            "phase": 1,
            "project_name": "demo-project",
            "project_type": "python-cli",
            "title": "Diseño y control de daños",
            "summary": "Demo local.",
            "problem": "Automatiza una tarea repetitiva.",
            "architecture": ["CLI", "Servicio"],
            "directory_tree": "demo-project/\n  README.md\n  pyproject.toml",
            "files": [],
            "risks": ["Datos corruptos", "Ruta inválida", "Dependencia ausente"],
        }
    )


def phase_two() -> ProjectPhaseResult:
    return ProjectPhaseResult.model_validate(
        {
            "phase": 2,
            "project_name": "demo-project",
            "project_type": "python-cli",
            "title": "Estructura y código",
            "summary": "Código base.",
            "files": [
                {"path": "pyproject.toml", "content": "[project]\nname='demo-project'"},
                {"path": "src/demo.py", "content": "def main():\n    return 0\n"},
            ],
            "dependencies": ["Python 3.12"],
            "windows_installation": ["py -3.12 -m venv .venv"],
            "quickstart": ["python src/demo.py"],
        }
    )


def phase_three() -> ProjectPhaseResult:
    return ProjectPhaseResult.model_validate(
        {
            "phase": 3,
            "project_name": "demo-project",
            "project_type": "python-cli",
            "title": "Pruebas y manejo de errores",
            "summary": "Pruebas aisladas con datos ficticios.",
            "files": [
                {"path": "tests/test_demo.py", "content": "def test_demo():\n    assert True\n"}
            ],
            "test_commands": ["python -m pytest"],
            "risks": ["Las pruebas deben ejecutarse antes de publicar."],
        }
    )


def phase_four() -> ProjectPhaseResult:
    return ProjectPhaseResult.model_validate(
        {
            "phase": 4,
            "project_name": "demo-project",
            "project_type": "python-cli",
            "title": "Documentación y Git",
            "summary": "README y comandos de publicación sugeridos.",
            "files": [{"path": "README.md", "content": "# Demo Project\n"}],
            "windows_installation": ["py -3.12 -m venv .venv"],
            "quickstart": ["python src/demo.py"],
            "git_commands": ["git init", "git add .", 'git commit -m "feat: initial project"'],
        }
    )


def test_project_session_persists_each_approved_phase_in_order(tmp_path):
    store = ProjectSessionStore(tmp_path / "sessions.db")
    session = store.create("Organiza archivos locales", "auto")

    assert session.next_phase == 1
    session = store.save_phase(session.id, phase_one())
    assert session.next_phase == 2
    assert session.project_type == "python-cli"

    with pytest.raises(ValueError, match="Se esperaba la Fase 2"):
        store.save_phase(session.id, phase_three())

    store.close()
    reopened = ProjectSessionStore(tmp_path / "sessions.db")
    restored = reopened.get(session.id)
    assert restored.next_phase == 2
    assert restored.phases[0].risks[0] == "Datos corruptos"
    reopened.close()


def test_blueprint_is_assembled_only_from_four_ordered_phases():
    with pytest.raises(ValueError, match="cuatro fases aprobadas"):
        assemble_blueprint([phase_one()])

    blueprint = assemble_blueprint([phase_one(), phase_two(), phase_three(), phase_four()])

    assert blueprint.project_name == "demo-project"
    assert {file.path for file in blueprint.files} == {
        "pyproject.toml",
        "src/demo.py",
        "tests/test_demo.py",
        "README.md",
    }
    assert blueprint.git_commands[0] == "git init"
