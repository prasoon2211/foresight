import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote

from django.conf import settings
from django.core import signing
from django.utils import timezone

from core.models import Run
from executor import AgentSession, AttachEndpoints, DurableExecutor, SandboxHandle

TERMINAL_TICKET_SALT = "foresight.run-terminal"
TERMINAL_TICKET_MAX_AGE_SECONDS = 300
ATTACH_ENDPOINT_TTL_SECONDS = 3600


@dataclass(frozen=True)
class BrowserAttachEndpoints:
    web_url: str
    api_url: str
    web_username: str
    web_password: str
    expires_at: datetime
    terminal_websocket_url: str
    tui_command: str


def is_attachable(run: Run) -> bool:
    return bool(run.sandbox_id and run.agent_session_id and run.sandbox_archived_at is None)


def is_revivable(run: Run) -> bool:
    archived_at = run.sandbox_archived_at
    return bool(
        run.sandbox_id
        and archived_at is not None
        and archived_at >= timezone.now() - timedelta(days=settings.SANDBOX_RETENTION_DAYS)
    )


def revive_run_sandbox(*, run: Run, executor: DurableExecutor) -> Run:
    executor.revive(SandboxHandle(sandbox_id=run.sandbox_id))
    run.sandbox_archived_at = None
    run.save(update_fields=["sandbox_archived_at", "updated_at"])
    return run


def terminal_ticket_is_valid(*, ticket: str, org_id: int, run_id: int) -> bool:
    try:
        payload = signing.loads(
            ticket,
            salt=TERMINAL_TICKET_SALT,
            max_age=TERMINAL_TICKET_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("org_id") == org_id
        and payload.get("run_id") == run_id
    )


def mint_attach_endpoints(
    *,
    run: Run,
    org_id: int,
    executor: DurableExecutor,
) -> BrowserAttachEndpoints:
    endpoints = executor.get_attach_endpoints(
        SandboxHandle(sandbox_id=run.sandbox_id),
        AgentSession(
            session_id=run.agent_session_id,
            base_url=run.agent_base_url,
            server_password=run.server_password,
        ),
    )
    return _browser_endpoints(run=run, org_id=org_id, endpoints=endpoints)


def _browser_endpoints(
    *,
    run: Run,
    org_id: int,
    endpoints: AttachEndpoints,
) -> BrowserAttachEndpoints:
    ticket = signing.dumps(
        {
            "org_id": org_id,
            "run_id": run.pk,
            "nonce": secrets.token_urlsafe(16),
        },
        salt=TERMINAL_TICKET_SALT,
        compress=True,
    )
    websocket_base = settings.PUBLIC_BASE_URL.replace("https://", "wss://", 1).replace(
        "http://", "ws://", 1
    )
    terminal_path = f"/api/orgs/{org_id}/runs/{run.pk}/terminal"
    return BrowserAttachEndpoints(
        web_url=endpoints.web_url,
        api_url=endpoints.api_url,
        web_username="opencode",
        web_password=run.server_password,
        expires_at=timezone.now() + timedelta(seconds=ATTACH_ENDPOINT_TTL_SECONDS),
        terminal_websocket_url=f"{websocket_base}{terminal_path}?ticket={quote(ticket)}",
        tui_command=endpoints.tui_command,
    )
