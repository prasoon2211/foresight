import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest
from asgiref.typing import ASGIReceiveEvent, ASGISendEvent, Scope
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from api import terminal_proxy
from core.models import Org, OrgMembership, Repo, Run, RunState, Signal
from core.session_exports import store_session_export
from executor import AgentMessage, FakeExecutor
from foresight.asgi import application
from orchestration.executor_backend import use_executor


@pytest.mark.django_db
def test_browser_can_bootstrap_csrf_for_headless_auth(client: Client) -> None:
    response = client.get("/api/csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert response.cookies["csrftoken"].value

    browser = Client(enforce_csrf_checks=True)
    bootstrap = browser.get("/api/csrf")
    login = browser.post(
        "/_allauth/browser/v1/auth/login",
        data={"email": "missing@example.com", "password": "wrong"},
        content_type="application/json",
        headers={
            "Origin": "http://localhost:5173",
            "X-CSRFToken": bootstrap.json()["csrf_token"],
        },
    )
    assert login.status_code == 400
    assert login.headers["Content-Type"] == "application/json"


@pytest.fixture
def run_room(client: Client) -> tuple[Client, Org, Signal, Run]:
    user = get_user_model().objects.create_user(
        username="run-room-member",
        email="run-room@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(org=org, user=user, role=OrgMembership.Role.MEMBER)
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    signal = Signal.objects.create(
        org=org,
        repo=repo,
        title="Fix widgets",
        body="The widgets are broken.",
        intake_state="dispatched",
    )
    run = Run.objects.create(
        signal=signal,
        state=RunState.RUNNING,
        sandbox_id="sandbox-14",
        agent_session_id="session-14",
        agent_base_url="https://agent.internal",
        server_password="secret",
    )
    client.force_login(user)
    return client, org, signal, run


@pytest.mark.django_db
def test_attach_endpoints_are_minted_fresh_and_provider_terminal_stays_server_side(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, _, run = run_room
    fake = FakeExecutor()

    with use_executor(fake):
        first = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/attach")
        second = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/attach")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["web_url"] == "https://fake.test/sandbox-14/web"
    assert first.json()["api_url"] == "https://fake.test/sandbox-14/api"
    assert first.json()["tui_command"] == ("opencode attach fake://sandbox-14 --session session-14")
    assert first.json()["terminal_websocket_url"].startswith(
        f"ws://localhost:8000/api/orgs/{org.pk}/runs/{run.pk}/terminal?ticket="
    )
    assert "fake.test" not in first.json()["terminal_websocket_url"]
    assert first.json()["terminal_websocket_url"] != second.json()["terminal_websocket_url"]
    assert fake.calls == ["get_attach_endpoints", "get_attach_endpoints"]


@pytest.mark.django_db
def test_dashboard_lists_the_members_orgs_and_connected_repos(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, signal, _ = run_room

    orgs = client.get("/api/orgs")
    repos = client.get(f"/api/orgs/{org.pk}/repos")

    assert orgs.status_code == 200
    assert orgs.json() == [
        {
            "id": org.pk,
            "name": "Acme",
            "concurrency_cap": 3,
            "role": "member",
        }
    ]
    assert repos.status_code == 200
    assert repos.json()[0]["id"] == signal.repo_id
    assert repos.json()[0]["full_name"] == "acme/widgets"
    assert repos.json()[0]["connection_status"] == "connected"


@pytest.mark.django_db
def test_signal_run_history_and_polling_reflect_run_row_changes(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, signal, run = run_room
    failed = Run.objects.create(
        signal=signal,
        state=RunState.FAILED,
        failure_reason="agent_error",
        failure_detail="Provider rejected the request.",
    )

    history = client.get(f"/api/orgs/{org.pk}/signals/{signal.pk}/runs")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [run.pk, failed.pk]
    assert history.json()[1]["failure_detail"] == "Provider rejected the request."

    run.state = RunState.AWAITING_REVIEW
    run.save(update_fields=["state", "updated_at"])
    polled = client.get(f"/api/orgs/{org.pk}/runs/{run.pk}")
    assert polled.status_code == 200
    assert polled.json()["state"] == RunState.AWAITING_REVIEW


@pytest.mark.django_db
def test_finished_run_transcript_is_returned_from_durable_export(
    run_room: tuple[Client, Org, Signal, Run],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, org, _, run = run_room
    monkeypatch.setattr(settings, "SESSION_EXPORT_ROOT", tmp_path)
    run.session_export_path = store_session_export(
        run_id=run.pk,
        messages=[
            AgentMessage(role="user", text="Fix the widget."),
            AgentMessage(role="assistant", text="Opened pull request 14."),
        ],
    )
    run.state = RunState.AWAITING_REVIEW
    run.save(update_fields=["session_export_path", "state", "updated_at"])

    response = client.get(f"/api/orgs/{org.pk}/runs/{run.pk}/transcript")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run.pk,
        "messages": [
            {"role": "user", "text": "Fix the widget."},
            {"role": "assistant", "text": "Opened pull request 14."},
        ],
    }


@pytest.mark.django_db
def test_recently_archived_sandbox_can_be_revived(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, _, run = run_room
    run.state = RunState.AWAITING_REVIEW
    run.sandbox_archived_at = timezone.now()
    run.save(update_fields=["state", "sandbox_archived_at", "updated_at"])
    fake = FakeExecutor()

    with use_executor(fake):
        response = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/revive")

    assert response.status_code == 200
    assert response.json()["revivable"] is False
    assert response.json()["sandbox_archived_at"] is None
    assert fake.calls == ["revive"]


@pytest.mark.django_db
def test_expired_archived_sandbox_is_not_offered_for_revival(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, _, run = run_room
    run.state = RunState.AWAITING_REVIEW
    run.sandbox_archived_at = timezone.now() - timedelta(days=15)
    run.save(update_fields=["state", "sandbox_archived_at", "updated_at"])
    fake = FakeExecutor()

    with use_executor(fake):
        response = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/revive")

    assert response.status_code == 409
    assert response.json()["code"] == "sandbox_unavailable"
    assert fake.calls == []


async def _invoke_websocket(
    *,
    path: str,
    query: str,
    cookie: str = "",
    incoming: list[dict[str, object]] | None = None,
) -> list[ASGISendEvent]:
    messages = list(incoming or [{"type": "websocket.connect"}])
    sent: list[ASGISendEvent] = []

    async def receive() -> ASGIReceiveEvent:
        if messages:
            return cast(ASGIReceiveEvent, messages.pop(0))
        await asyncio.Future()
        raise AssertionError("unreachable")

    async def send(message: ASGISendEvent) -> None:
        sent.append(message)

    headers = [(b"cookie", cookie.encode())] if cookie else []
    await application(
        cast(
            Scope,
            {
                "type": "websocket",
                "asgi": {"version": "3.0"},
                "path": path,
                "query_string": query.encode(),
                "headers": headers,
            },
        ),
        receive,
        send,
    )
    return sent


@pytest.mark.django_db(transaction=True)
def test_terminal_websocket_rejects_an_unauthenticated_browser(
    run_room: tuple[Client, Org, Signal, Run],
) -> None:
    client, org, _, run = run_room
    fake = FakeExecutor()
    with use_executor(fake):
        attach = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/attach").json()
        terminal_url = urlsplit(attach["terminal_websocket_url"])
        sent = asyncio.run(
            _invoke_websocket(
                path=terminal_url.path,
                query=terminal_url.query,
            )
        )

    assert sent == [{"type": "websocket.close", "code": 4401, "reason": ""}]
    assert fake.calls == ["get_attach_endpoints"]


class FakeTerminalSocket:
    def __init__(self) -> None:
        self.received: list[str | bytes] = []
        self._browser_sent = asyncio.Event()

    async def send(self, message: str | bytes) -> None:
        self.received.append(message)
        self._browser_sent.set()

    async def __aiter__(self) -> AsyncIterator[str | bytes]:
        await self._browser_sent.wait()
        yield "terminal ready"


@pytest.mark.django_db(transaction=True)
def test_authenticated_terminal_websocket_proxies_without_exposing_provider_url(
    run_room: tuple[Client, Org, Signal, Run],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, org, _, run = run_room
    fake = FakeExecutor()
    upstream = FakeTerminalSocket()
    opened_urls: list[str] = []

    @asynccontextmanager
    async def open_fake_terminal(url: str) -> AsyncIterator[FakeTerminalSocket]:
        opened_urls.append(url)
        yield upstream

    monkeypatch.setattr(terminal_proxy, "open_terminal_connection", open_fake_terminal)
    with use_executor(fake):
        attach = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/attach").json()
        terminal_url = urlsplit(attach["terminal_websocket_url"])
        sent = asyncio.run(
            _invoke_websocket(
                path=terminal_url.path,
                query=terminal_url.query,
                cookie=f"sessionid={client.cookies['sessionid'].value}",
                incoming=[
                    {"type": "websocket.connect"},
                    {"type": "websocket.receive", "text": "whoami\n"},
                ],
            )
        )

    assert sent == [
        {"type": "websocket.accept", "subprotocol": None, "headers": []},
        {"type": "websocket.send", "text": "terminal ready", "bytes": None},
    ]
    assert upstream.received == ["whoami\n"]
    assert opened_urls == ["wss://fake.test/sandbox-14/terminal"]
    assert "fake.test" not in attach["terminal_websocket_url"]
    assert fake.calls == ["get_attach_endpoints", "get_attach_endpoints"]
