import json

import pytest
from pydantic import ValidationError

from nexo.project.architect import ProjectArchitect, ProjectBlueprint


class StubProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def valid_blueprint() -> dict[str, object]:
    return {
        "project_name": "invoice-organizer",
        "project_type": "python-cli",
        "summary": "Organiza facturas locales por fecha.",
        "problem": "Reduce el trabajo manual al clasificar archivos.",
        "architecture": ["CLI", "Servicio de organización"],
        "directory_tree": "invoice-organizer/\n  README.md",
        "files": [
            {"path": "README.md", "content": "# Invoice Organizer"},
            {"path": "pyproject.toml", "content": "[project]\nname='invoice-organizer'"},
        ],
        "dependencies": ["Python 3.12"],
        "windows_installation": ["py -3.12 -m venv .venv"],
        "quickstart": ["python -m invoice_organizer"],
        "git_commands": ["git init", "git add .", 'git commit -m "feat: initial project"'],
        "risks": [],
    }


def test_architect_returns_only_phase_one_and_redacts_the_requirement():
    phase_one = {
        "phase": 1,
        "project_name": "invoice-organizer",
        "project_type": "python-cli",
        "title": "Diseño y control de daños",
        "summary": "Organiza facturas locales por fecha.",
        "problem": "Reduce el trabajo manual al clasificar archivos.",
        "architecture": ["CLI", "Servicio de organización"],
        "directory_tree": "invoice-organizer/\n  README.md",
        "files": [],
        "dependencies": [],
        "windows_installation": [],
        "quickstart": [],
        "test_commands": [],
        "git_commands": [],
        "risks": ["Archivos corruptos", "Nombres duplicados", "Permisos insuficientes"],
    }
    provider = StubProvider(json.dumps(phase_one))
    architect = ProjectArchitect(provider)

    result = architect.generate_phase(
        "Organiza facturas. Contacto dev@example.com api_key=private-value",
        1,
        "python-cli",
    )

    assert result.phase == 1
    assert result.project_name == "invoice-organizer"
    assert result.files == []
    assert len(result.risks) == 3
    assert "Windows 11" in provider.prompts[0]
    assert "SOLO la Fase 1" in provider.prompts[0]
    assert "dev@example.com" not in provider.prompts[0]
    assert "private-value" not in provider.prompts[0]


@pytest.mark.parametrize(
    "path", ["../outside.txt", "C:\\outside.txt", ".env", ".env.production", ".git/config"]
)
def test_architect_rejects_unsafe_generated_paths(path: str):
    payload = valid_blueprint()
    payload["files"] = [
        {"path": "README.md", "content": "# Safe"},
        {"path": "pyproject.toml", "content": "[project]"},
        {"path": path, "content": "unsafe"},
    ]

    with pytest.raises(ValidationError):
        ProjectBlueprint.model_validate(payload)


def test_architect_rejects_python_project_without_dependency_manifest():
    payload = valid_blueprint()
    payload["files"] = [{"path": "README.md", "content": "# Safe"}]

    with pytest.raises(ValidationError, match="pyproject.toml"):
        ProjectBlueprint.model_validate(payload)
