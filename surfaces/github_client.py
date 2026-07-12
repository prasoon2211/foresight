import json
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any, Protocol
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import jwt
from django.conf import settings


class GitHubClient(Protocol):
    def post_issue_comment(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        body: str,
    ) -> int: ...

    def add_issue_labels(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        labels: tuple[str, ...],
    ) -> None: ...

    def remove_issue_label(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        label: str,
    ) -> None: ...

    def find_open_pull_request(
        self,
        installation_id: int,
        repo_full_name: str,
        branch_name: str,
    ) -> str | None: ...


class FakeGitHubClient:
    """In-memory GitHub boundary with externally inspectable calls."""

    def __init__(
        self,
        *,
        open_pull_requests: Mapping[tuple[str, str], str] | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.comments: list[tuple[str, int, str]] = []
        self.label_additions: list[tuple[str, int, tuple[str, ...]]] = []
        self.label_removals: list[tuple[str, int, str]] = []
        self.pull_request_lookups: list[tuple[int, str, str]] = []
        self.open_pull_requests = dict(open_pull_requests or {})

    def post_issue_comment(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        body: str,
    ) -> int:
        self.calls.append("post_issue_comment")
        self.comments.append((repo_full_name, issue_number, body))
        return len(self.comments)

    def add_issue_labels(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        labels: tuple[str, ...],
    ) -> None:
        self.calls.append("add_issue_labels")
        self.label_additions.append((repo_full_name, issue_number, labels))

    def remove_issue_label(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        label: str,
    ) -> None:
        self.calls.append("remove_issue_label")
        self.label_removals.append((repo_full_name, issue_number, label))

    def find_open_pull_request(
        self,
        installation_id: int,
        repo_full_name: str,
        branch_name: str,
    ) -> str | None:
        self.calls.append("find_open_pull_request")
        self.pull_request_lookups.append((installation_id, repo_full_name, branch_name))
        return self.open_pull_requests.get((repo_full_name, branch_name))


class GitHubAppClient:
    """GitHub REST client authenticated as one App installation at a time."""

    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        api_url: str = "https://api.github.com",
    ) -> None:
        self.app_id = app_id
        self.private_key = private_key
        self.api_url = api_url.rstrip("/")
        self._tokens: dict[int, tuple[str, float]] = {}

    def post_issue_comment(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        body: str,
    ) -> int:
        response = self._request_json(
            "POST",
            f"/repos/{quote(repo_full_name, safe='/')}/issues/{issue_number}/comments",
            installation_id=installation_id,
            payload={"body": body},
        )
        return int(response["id"])

    def add_issue_labels(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        labels: tuple[str, ...],
    ) -> None:
        self._request_json(
            "POST",
            f"/repos/{quote(repo_full_name, safe='/')}/issues/{issue_number}/labels",
            installation_id=installation_id,
            payload={"labels": list(labels)},
        )

    def remove_issue_label(
        self,
        installation_id: int,
        repo_full_name: str,
        issue_number: int,
        label: str,
    ) -> None:
        self._request_json(
            "DELETE",
            (
                f"/repos/{quote(repo_full_name, safe='/')}/issues/{issue_number}"
                f"/labels/{quote(label, safe='')}"
            ),
            installation_id=installation_id,
        )

    def find_open_pull_request(
        self,
        installation_id: int,
        repo_full_name: str,
        branch_name: str,
    ) -> str | None:
        owner = repo_full_name.split("/", 1)[0]
        query = urlencode(
            {
                "state": "open",
                "head": f"{owner}:{branch_name}",
                "per_page": 1,
            }
        )
        response = self._request_json(
            "GET",
            f"/repos/{quote(repo_full_name, safe='/')}/pulls?{query}",
            installation_id=installation_id,
        )
        if not isinstance(response, list) or not response:
            return None
        pr_url = response[0].get("html_url")
        return str(pr_url) if pr_url else None

    def _installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        if cached is not None and cached[1] > time.time() + 60:
            return cached[0]
        now = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": self.app_id},
            self.private_key,
            algorithm="RS256",
        )
        response = self._request_json(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            authorization=f"Bearer {app_jwt}",
        )
        token = str(response["token"])
        self._tokens[installation_id] = (token, time.time() + 3000)
        return token

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        installation_id: int | None = None,
        authorization: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> Any:
        if authorization is None:
            if installation_id is None:
                raise ValueError("an installation ID or authorization header is required")
            authorization = f"Bearer {self._installation_token(installation_id)}"
        request = Request(
            f"{self.api_url}{path}",
            data=json.dumps(payload).encode() if payload is not None else None,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": authorization,
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "foresight",
            },
        )
        with urlopen(request, timeout=15) as response:
            body = response.read()
        if not body:
            return {}
        return json.loads(body)


_override: ContextVar[GitHubClient | None] = ContextVar("github_client", default=None)
_default_client: GitHubClient | None = None


def get_github_client() -> GitHubClient:
    global _default_client
    client = _override.get()
    if client is not None:
        return client
    if _default_client is None:
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
            raise RuntimeError("GitHub App client is not configured")
        _default_client = GitHubAppClient(
            app_id=settings.GITHUB_APP_ID,
            private_key=settings.GITHUB_APP_PRIVATE_KEY,
            api_url=settings.GITHUB_API_URL,
        )
    return _default_client


@contextmanager
def use_github_client(client: GitHubClient) -> Iterator[None]:
    token: Token[GitHubClient | None] = _override.set(client)
    try:
        yield
    finally:
        _override.reset(token)
