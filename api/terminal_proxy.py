import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from importlib import import_module
from typing import Protocol
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from asgiref.typing import (
    ASGI3Application,
    ASGIReceiveCallable,
    ASGISendCallable,
    Scope,
    WebSocketAcceptEvent,
    WebSocketCloseEvent,
    WebSocketScope,
    WebSocketSendEvent,
)
from django.conf import settings
from django.contrib.sessions.backends.base import SessionBase
from django.db import close_old_connections
from websockets.asyncio.client import connect

from api.run_room import terminal_ticket_is_valid
from core.api_tokens import authenticate_api_token
from core.models import ApiToken, OrgMembership, Run
from executor import AgentSession, SandboxHandle
from orchestration.executor_backend import get_executor

TERMINAL_PATH = re.compile(r"^/api/orgs/(?P<org_id>\d+)/runs/(?P<run_id>\d+)/terminal$")


class TerminalSocket(Protocol):
    async def send(self, message: str | bytes) -> None: ...

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


@asynccontextmanager
async def open_terminal_connection(url: str) -> AsyncIterator[TerminalSocket]:
    async with connect(url) as websocket:
        yield websocket


class ForesightAsgiApplication:
    def __init__(self, http_application: ASGI3Application) -> None:
        self._http_application = http_application

    async def __call__(
        self,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        if scope["type"] != "websocket":
            await self._http_application(scope, receive, send)
            return
        websocket_scope = scope
        match = TERMINAL_PATH.fullmatch(websocket_scope["path"])
        query = parse_qs(websocket_scope["query_string"].decode())
        if match is None:
            await _close(send, 4404)
            return
        org_id = int(match.group("org_id"))
        run_id = int(match.group("run_id"))
        tickets = query.get("ticket", [])
        if not tickets or not terminal_ticket_is_valid(
            ticket=tickets[0],
            org_id=org_id,
            run_id=run_id,
        ):
            await _close(send, 4401)
            return
        authenticated, run = await _authenticated_run(websocket_scope, org_id=org_id, run_id=run_id)
        if not authenticated:
            await _close(send, 4401)
            return
        if run is None:
            await _close(send, 4404)
            return
        if not run.sandbox_id or not run.agent_session_id or run.sandbox_archived_at is not None:
            await _close(send, 4409)
            return
        terminal_url = await sync_to_async(_provider_terminal_url)(run)
        try:
            async with open_terminal_connection(terminal_url) as upstream:
                event = await receive()
                if event["type"] != "websocket.connect":
                    return
                await send(
                    WebSocketAcceptEvent(
                        type="websocket.accept",
                        subprotocol=None,
                        headers=[],
                    )
                )
                await _proxy(receive=receive, send=send, upstream=upstream)
        except OSError:
            await _close(send, 1011)


async def _authenticated_run(
    scope: WebSocketScope,
    *,
    org_id: int,
    run_id: int,
) -> tuple[bool, Run | None]:
    headers = dict(scope["headers"])
    authorization = headers.get(b"authorization", b"").decode()
    if authorization.startswith("Bearer "):
        token = await sync_to_async(_authenticate_token)(authorization.removeprefix("Bearer "))
        if token is None:
            return False, None
        return True, await sync_to_async(_token_run)(token, org_id, run_id)

    session_key = _session_key(headers.get(b"cookie", b"").decode())
    if not session_key:
        return False, None
    session_store = import_module(settings.SESSION_ENGINE).SessionStore(session_key=session_key)
    user_id = await sync_to_async(_session_user_id)(session_store)
    if user_id is None:
        return False, None
    return True, await sync_to_async(_member_run)(int(user_id), org_id, run_id)


def _session_key(cookie_header: str) -> str:
    cookies = SimpleCookie()
    cookies.load(cookie_header)
    session = cookies.get(settings.SESSION_COOKIE_NAME)
    return session.value if session else ""


def _token_run(token: ApiToken, org_id: int, run_id: int) -> Run | None:
    try:
        if token.org_id != org_id:
            return None
        return Run.objects.filter(pk=run_id, signal__org_id=org_id).first()
    finally:
        close_old_connections()


def _member_run(user_id: int, org_id: int, run_id: int) -> Run | None:
    try:
        if not OrgMembership.objects.filter(user_id=user_id, org_id=org_id).exists():
            return None
        return Run.objects.filter(pk=run_id, signal__org_id=org_id).first()
    finally:
        close_old_connections()


def _authenticate_token(raw_token: str) -> ApiToken | None:
    try:
        return authenticate_api_token(raw_token)
    finally:
        close_old_connections()


def _session_user_id(session: SessionBase) -> str | None:
    try:
        user_id = session.get("_auth_user_id")
        return str(user_id) if user_id is not None else None
    finally:
        close_old_connections()


def _provider_terminal_url(run: Run) -> str:
    endpoints = get_executor().get_attach_endpoints(
        SandboxHandle(sandbox_id=run.sandbox_id),
        AgentSession(
            session_id=run.agent_session_id,
            base_url=run.agent_base_url,
            server_password=run.server_password,
        ),
    )
    return endpoints.terminal_ws


async def _proxy(
    *,
    receive: ASGIReceiveCallable,
    send: ASGISendCallable,
    upstream: TerminalSocket,
) -> None:
    browser_task = asyncio.create_task(_browser_to_provider(receive, upstream))
    provider_task = asyncio.create_task(_provider_to_browser(send, upstream))
    done, pending = await asyncio.wait(
        {browser_task, provider_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    for task in done:
        task.result()


async def _browser_to_provider(
    receive: ASGIReceiveCallable,
    upstream: TerminalSocket,
) -> None:
    while True:
        event = await receive()
        if event["type"] == "websocket.disconnect":
            return
        if event["type"] != "websocket.receive":
            continue
        binary = event.get("bytes")
        text = event.get("text")
        if binary is not None:
            await upstream.send(binary)
        elif text is not None:
            await upstream.send(text)


async def _provider_to_browser(
    send: ASGISendCallable,
    upstream: TerminalSocket,
) -> None:
    async for message in upstream:
        if isinstance(message, bytes):
            await send(WebSocketSendEvent(type="websocket.send", bytes=message, text=None))
        else:
            await send(WebSocketSendEvent(type="websocket.send", text=message, bytes=None))


async def _close(send: ASGISendCallable, code: int) -> None:
    await send(WebSocketCloseEvent(type="websocket.close", code=code, reason=""))
