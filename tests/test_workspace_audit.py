import json

import pytest

from nexo.tools.workspace_audit import WorkspaceAuditTool


def test_workspace_audit_reports_caches_and_gitignore_without_reading_secrets(tmp_path):
    (tmp_path / ".mypy_cache").mkdir()
    (tmp_path / ".mypy_cache" / "cache.bin").write_bytes(b"cache")
    (tmp_path / ".env").write_text("API_KEY=private-value", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".venv/\n.env\n", encoding="utf-8")
    settings_dir = tmp_path / ".vscode"
    settings_dir.mkdir()
    (settings_dir / "settings.json").write_text(
        '{"files.watcherExclude":{"**/.venv/**":true}}',
        encoding="utf-8",
    )

    report = json.loads(WorkspaceAuditTool(tmp_path).run({"path": "."}))

    assert any(
        item["path"] == ".mypy_cache" and item["bytes"] == 5
        for item in report["generated_directories"]
    )
    assert ".pytest_cache/" in report["gitignore_missing_recommendations"]
    assert report["workspace_settings"]["files.watcherExclude"] == {
        "**/.venv/**": True
    }
    assert report["actions_taken"] == []
    assert "private-value" not in json.dumps(report)


def test_workspace_audit_rejects_parent_traversal(tmp_path):
    tool = WorkspaceAuditTool(tmp_path)

    with pytest.raises(PermissionError):
        tool.run({"path": "../outside"})