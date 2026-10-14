import json

import pytest

from nexo.core.models import ActionRequest
from nexo.policy.engine import PolicyEngine
from nexo.project.architect import ProjectBlueprint
from nexo.tools.base import ToolRegistry
from nexo.tools.project_tools import ProjectScaffoldTool
from nexo.verifiers.project_verifier import ProjectScaffoldVerifier


def make_blueprint() -> ProjectBlueprint:
    return ProjectBlueprint.model_validate(
        {
            "project_name": "demo-project",
            "project_type": "python-cli",
            "summary": "Proyecto de demostración.",
            "problem": "Automatiza una tarea local.",
            "architecture": ["CLI"],
            "directory_tree": "demo-project/\n  README.md\n  pyproject.toml",
            "files": [
                {"path": "README.md", "content": "# Demo Project"},
                {"path": "pyproject.toml", "content": "[project]\nname='demo-project'"},
                {"path": "src/demo.py", "content": "def main():\n    return 0\n"},
            ],
            "dependencies": [],
            "windows_installation": ["py -m venv .venv"],
            "quickstart": ["python src/demo.py"],
            "git_commands": ["git init"],
            "risks": [],
        }
    )


def test_scaffold_writes_atomically_and_verifier_confirms_all_files(tmp_path):
    tool = ProjectScaffoldTool(tmp_path)
    action = ActionRequest(
        tool=tool.name,
        params={"target": "projects/demo-project", "blueprint": make_blueprint().model_dump()},
        risk_level=tool.risk_level,
        expected_outcome="crear proyecto nuevo",
        verifier="project_scaffold",
    )

    output = tool.run(action.params)
    verification = ProjectScaffoldVerifier(tmp_path).verify(action, output)

    assert verification.verified
    assert (tmp_path / "projects/demo-project/src/demo.py").read_text(encoding="utf-8") == (
        "def main():\n    return 0\n"
    )
    assert json.loads(output)["files"] == ["README.md", "pyproject.toml", "src/demo.py"]


def test_scaffold_refuses_to_overwrite_existing_destination(tmp_path):
    target = tmp_path / "projects/demo-project"
    target.mkdir(parents=True)
    tool = ProjectScaffoldTool(tmp_path)

    with pytest.raises(FileExistsError):
        tool.run({"target": "projects/demo-project", "blueprint": make_blueprint().model_dump()})


def test_policy_requires_explicit_approval_for_scaffolding(tmp_path):
    tool = ProjectScaffoldTool(tmp_path)
    registry = ToolRegistry()
    registry.register(tool)
    policy = PolicyEngine(registry, tmp_path)
    action = ActionRequest(
        tool=tool.name,
        params={"target": "projects/demo-project", "blueprint": make_blueprint().model_dump()},
        risk_level=tool.risk_level,
        expected_outcome="crear proyecto nuevo",
        verifier="project_scaffold",
    )

    assert not policy.evaluate(action).allowed
    assert policy.evaluate(action, explicit_approval=True).allowed
