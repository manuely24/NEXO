"""Lectura de issues y pull requests asignados mediante GitHub REST API."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from nexo.core.models import DataClass, RiskLevel
from nexo.tools.base import BaseTool


def get_github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        import keyring

        return keyring.get_password("nexo", "github_token")
    except Exception:
        return None


class GitHubTool(BaseTool):
    risk_level = RiskLevel.EXTERNAL
    external = True
    data_class = DataClass.CONFIDENTIAL

    def __init__(
        self,
        workspace: str | Path,
        timeout_s: float = 8.0,
        token: str | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.timeout_s = timeout_s
        self._token = token

    def _repo(self) -> tuple[str, str]:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            check=True,
            timeout=self.timeout_s,
        ).stdout.strip()
        if Path(root).resolve() != self.workspace:
            raise PermissionError("GitHub solo se consulta desde la raíz exacta del workspace")
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.workspace,
            capture_output=True,
            text=True,
            check=True,
            timeout=self.timeout_s,
        )
        remote = result.stdout.strip()
        if remote.startswith("git@github.com:"):
            slug = remote.removeprefix("git@github.com:")
        else:
            parsed = urllib.parse.urlparse(remote)
            if parsed.hostname not in {"github.com", "www.github.com"}:
                raise ValueError("El remote origin no es de github.com")
            slug = parsed.path.lstrip("/")
        parts = slug.removesuffix(".git").strip("/").split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("No se pudo obtener owner/repo desde origin")
        return parts[0], parts[1]

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        token = self._token or get_github_token()
        if not token:
            raise RuntimeError("Configura GITHUB_TOKEN/GH_TOKEN o una credencial keyring de Nexo")
        owner, repo = self._repo()
        url = f"https://api.github.com/repos/{owner}/{repo}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"La solicitud a GitHub falló: {exc}") from exc
        try:
            return json.loads(body) if body else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("GitHub devolvió JSON inválido") from exc


class GitHubListIssuesTool(GitHubTool):
    name = "github.list_issues"

    def run(self, params: dict[str, Any]) -> str:
        issues = self._request("GET", "issues?filter=assigned&state=open&per_page=100")
        pending = [
            {
                "number": item["number"],
                "title": item["title"],
                "url": item["html_url"],
                "is_pull_request": "pull_request" in item,
                "labels": [label["name"] for label in item.get("labels", [])],
            }
            for item in issues
            if (
                isinstance(item, dict)
                and "number" in item
                and "title" in item
                and "pull_request" not in item
            )
        ]
        return json.dumps(pending, ensure_ascii=False)


class GitHubListPullRequestsTool(GitHubTool):
    name = "github.list_pull_requests"

    def run(self, params: dict[str, Any]) -> str:
        pull_requests = self._request("GET", "pulls?state=open&per_page=100")
        result = [
            {
                "number": item["number"],
                "title": item["title"],
                "url": item["html_url"],
                "draft": bool(item.get("draft", False)),
                "head": item.get("head", {}).get("ref", ""),
                "base": item.get("base", {}).get("ref", ""),
            }
            for item in pull_requests
            if isinstance(item, dict) and "number" in item and "title" in item
        ]
        return json.dumps(result, ensure_ascii=False)


class GitHubDraftPullRequestTool(GitHubTool):
    name = "github.draft_pull_request"
    data_class = DataClass.CLOUD_OK

    def run(self, params: dict[str, Any]) -> str:
        required = ("title", "head", "base")
        if any(not str(params.get(field, "")).strip() for field in required):
            raise ValueError("title, head y base son obligatorios")
        result = self._request(
            "POST",
            "pulls",
            {
                "title": str(params["title"]).strip(),
                "head": str(params["head"]).strip(),
                "base": str(params["base"]).strip(),
                "body": str(params.get("body", "")),
                "draft": True,
            },
        )
        return json.dumps(
            {"number": result.get("number"), "url": result.get("html_url"), "draft": True},
            ensure_ascii=False,
        )


class GitHubDraftIssueTool(BaseTool):
    name = "github.draft_issue"
    risk_level = RiskLevel.MODIFIES_FILES
    data_class = DataClass.LOCAL

    def __init__(self, drafts_dir: str | Path) -> None:
        self.drafts_dir = Path(drafts_dir).resolve()

    def run(self, params: dict[str, Any]) -> str:
        title = str(params.get("title", "")).strip()
        if not title:
            raise ValueError("title es obligatorio")
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        draft_id = uuid4().hex
        path = self.drafts_dir / f"issue-{draft_id}.json"
        path.write_text(
            json.dumps(
                {"title": title, "body": str(params.get("body", "")), "state": "draft"},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return json.dumps({"id": draft_id, "path": str(path), "state": "draft"})