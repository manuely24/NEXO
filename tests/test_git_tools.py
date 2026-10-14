import subprocess

from nexo.tools.git_tools import GitCommitPrepTool, GitDiffTool, GitStatusTool


def init_repository(path):
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Nexo Test"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "nexo@example.test"], check=True
    )
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )


def test_status_and_diff_inspect_local_repository(tmp_path):
    init_repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("untracked\n", encoding="utf-8")

    status = GitStatusTool(tmp_path).run({})
    diff = GitDiffTool(tmp_path).run({})

    assert "tracked.txt" in status
    assert "new.txt" in status
    assert "changed" in diff


def test_commit_prep_formats_structured_message(tmp_path):
    init_repository(tmp_path)
    (tmp_path / "tracked.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)

    output = GitCommitPrepTool(tmp_path).run(
        {"type": "feat", "scope": "cli", "summary": "add pending view"}
    )

    assert "feat(cli): add pending view" in output
    assert "tracked.txt" in output
    assert "aprobación explícita" in output