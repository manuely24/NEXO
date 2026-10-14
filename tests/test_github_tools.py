import json
import subprocess
from io import BytesIO

from nexo.tools.github_tools import (
    GitHubDraftIssueTool,
    GitHubDraftPullRequestTool,
    GitHubListIssuesTool,
    GitHubListPullRequestsTool,
    get_github_token,
)


def make_repo(path):
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "https://github.com/acme/demo.git"],
        check=True,
    )


def mock_response(monkeypatch, payload, captured):
    def urlopen(request, timeout):
        captured.append((request, timeout))
        return BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr("nexo.tools.github_tools.urllib.request.urlopen", urlopen)


def test_lists_assigned_issues_with_local_token(tmp_path, monkeypatch):
    make_repo(tmp_path)
    captured = []
    mock_response(
        monkeypatch,
        [{"number": 5, "title": "Fix bug", "html_url": "https://github.com/acme/demo/issues/5"}],
        captured,
    )

    result = json.loads(GitHubListIssuesTool(tmp_path, token="local-test-token").run({}))

    assert result[0]["number"] == 5
    assert captured[0][0].get_header("Authorization") == "Bearer local-test-token"


def test_lists_open_pull_requests(tmp_path, monkeypatch):
    make_repo(tmp_path)
    captured = []
    mock_response(
        monkeypatch,
        [
            {
                "number": 7,
                "title": "Add feature",
                "html_url": "https://github.com/acme/demo/pull/7",
                "draft": True,
                "head": {"ref": "feature"},
                "base": {"ref": "main"},
            }
        ],
        captured,
    )

    result = json.loads(GitHubListPullRequestsTool(tmp_path, token="token").run({}))

    assert result[0]["draft"] is True
    assert "pulls?state=open" in captured[0][0].full_url


def test_creates_pull_request_as_draft(tmp_path, monkeypatch):
    make_repo(tmp_path)
    captured = []
    mock_response(
        monkeypatch,
        {"number": 8, "html_url": "https://github.com/acme/demo/pull/8"},
        captured,
    )

    result = json.loads(
        GitHubDraftPullRequestTool(tmp_path, token="token").run(
            {"title": "Feature", "head": "feature", "base": "main"}
        )
    )

    assert result["draft"] is True
    assert captured[0][0].get_method() == "POST"
    assert json.loads(captured[0][0].data)["draft"] is True


def test_issue_draft_is_saved_locally(tmp_path):
    result = json.loads(
        GitHubDraftIssueTool(tmp_path / "drafts").run(
            {"title": "Investigate", "body": "Details"}
        )
    )

    assert result["state"] == "draft"
    assert json.loads((tmp_path / "drafts" / f"issue-{result['id']}.json").read_text())[
        "title"
    ] == "Investigate"


def test_github_token_falls_back_to_keyring(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("keyring.get_password", lambda service, username: "stored-token")

    assert get_github_token() == "stored-token"


def test_github_environment_token_takes_precedence(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "environment-token")
    monkeypatch.setattr("keyring.get_password", lambda service, username: "stored-token")

    assert get_github_token() == "environment-token"