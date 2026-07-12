from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from core.intake import dispatch_signal
from core.models import (
    ConnectionStatus,
    Org,
    Repo,
    Run,
    RunState,
    Signal,
    SignalSource,
    SurfaceConnection,
    SurfaceConnectionStatus,
    SurfaceType,
)
from surfaces.github_client import GitHubClient, get_github_client

RunEnqueuer = Callable[[int], object]
IN_PROGRESS_LABEL = "foresight:in-progress"
PR_OPEN_LABEL = "foresight:pr-open"


def find_open_pull_request_for_run(run: Run) -> str | None:
    connection = run.signal.repo.surface_connection
    if connection is None or connection.type != SurfaceType.GITHUB:
        return None
    installation_id = connection.identity.get("installation_id")
    if installation_id is None:
        return None
    return get_github_client().find_open_pull_request(
        int(installation_id),
        run.signal.repo.full_name,
        run.branch_name,
    )


def process_webhook(
    *,
    event: str,
    payload: dict[str, Any],
    enqueue_run: RunEnqueuer,
) -> None:
    """Interpret one verified GitHub webhook as domain actions."""
    if event == "installation":
        _process_installation(payload)
    elif event == "installation_repositories":
        _process_installation_repositories(payload)
    elif event == "issues":
        _process_issues(payload, enqueue_run)
    elif event == "pull_request":
        _process_pull_request(payload)


def _process_installation(payload: dict[str, Any]) -> None:
    installation = payload["installation"]
    installation_id = installation["id"]
    account_label = installation["account"]["login"]
    connection = _find_connection(installation_id, account_label)
    if connection is None and payload["action"] == "created" and Org.objects.count() == 1:
        connection = SurfaceConnection.objects.create(
            org=Org.objects.get(),
            type=SurfaceType.GITHUB,
            status=SurfaceConnectionStatus.PENDING,
            account_label=account_label,
        )
    if connection is None:
        return

    if payload["action"] == "deleted":
        connection.status = SurfaceConnectionStatus.REVOKED
        connection.save(update_fields=["status"])
        connection.repos.update(connection_status=ConnectionStatus.DISCONNECTED)
        return

    if payload["action"] not in {"created", "new_permissions_accepted"}:
        return

    connection.status = SurfaceConnectionStatus.ACTIVE
    connection.account_label = account_label
    connection.identity = {
        "installation_id": installation_id,
        "account_id": installation["account"]["id"],
    }
    connection.save(update_fields=["status", "account_label", "identity"])
    _connect_repositories(connection, payload.get("repositories", []))


def _process_installation_repositories(payload: dict[str, Any]) -> None:
    installation = payload["installation"]
    connection = _find_connection(
        installation["id"],
        installation["account"]["login"],
    )
    if connection is None:
        return
    _connect_repositories(connection, payload.get("repositories_added", []))
    removed_names = [
        repository["full_name"] for repository in payload.get("repositories_removed", [])
    ]
    connection.repos.filter(full_name__in=removed_names).update(
        connection_status=ConnectionStatus.DISCONNECTED
    )


def _process_issues(
    payload: dict[str, Any],
    enqueue_run: RunEnqueuer,
) -> None:
    if payload.get("action") != "labeled" or payload.get("label", {}).get("name") != "foresight":
        return
    installation_id = payload["installation"]["id"]
    repository = payload["repository"]
    connection = SurfaceConnection.objects.filter(
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.ACTIVE,
        identity__installation_id=installation_id,
    ).first()
    if connection is None:
        return
    repo = Repo.objects.filter(
        surface_connection=connection,
        full_name=repository["full_name"],
        connection_status=ConnectionStatus.CONNECTED,
    ).first()
    if repo is None:
        return
    issue = payload["issue"]
    if Signal.objects.filter(
        source=SignalSource.GITHUB_ISSUE,
        origin_connection=connection,
        origin_reference__issue_id=issue["id"],
    ).exists():
        return
    with transaction.atomic():
        signal = Signal.objects.create(
            org=connection.org,
            repo=repo,
            origin_connection=connection,
            origin_reference={
                "issue_id": issue["id"],
                "issue_number": issue["number"],
                "url": issue["html_url"],
            },
            source=SignalSource.GITHUB_ISSUE,
            title=issue["title"],
            body=issue.get("body") or "",
        )
        dispatch_signal(signal=signal, enqueue_run=enqueue_run)


def _process_pull_request(payload: dict[str, Any]) -> None:
    pull_request = payload.get("pull_request", {})
    if (
        payload.get("action") != "closed"
        or not pull_request.get("merged")
        or not pull_request.get("merged_at")
    ):
        return
    connection = SurfaceConnection.objects.filter(
        type=SurfaceType.GITHUB,
        identity__installation_id=payload["installation"]["id"],
    ).first()
    if connection is None:
        return
    merged_at = parse_datetime(pull_request["merged_at"])
    if merged_at is None:
        return
    Run.objects.filter(
        signal__repo__surface_connection=connection,
        signal__repo__full_name=payload["repository"]["full_name"],
    ).filter(
        Q(pr_url=pull_request["html_url"]) | Q(branch_name=pull_request["head"]["ref"])
    ).update(
        pr_merged_at=merged_at,
        state=RunState.DONE,
    )


def _find_connection(
    installation_id: int,
    account_label: str,
) -> SurfaceConnection | None:
    connection = SurfaceConnection.objects.filter(
        type=SurfaceType.GITHUB,
        identity__installation_id=installation_id,
    ).first()
    if connection is not None:
        return connection
    connection = SurfaceConnection.objects.filter(
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.REVOKED,
        account_label=account_label,
    ).first()
    if connection is not None:
        return connection
    pending = SurfaceConnection.objects.filter(
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.PENDING,
    )
    if pending.count() == 1:
        return pending.first()
    return None


def _connect_repositories(
    connection: SurfaceConnection,
    repositories: list[dict[str, Any]],
) -> None:
    for repository in repositories:
        repo, _ = Repo.objects.get_or_create(
            org=connection.org,
            full_name=repository["full_name"],
            defaults={
                "surface_connection": connection,
                "default_branch": repository.get("default_branch", "main"),
            },
        )
        repo.surface_connection = connection
        repo.default_branch = repository.get("default_branch", repo.default_branch)
        repo.connection_status = ConnectionStatus.CONNECTED
        repo.save(
            update_fields=[
                "surface_connection",
                "default_branch",
                "connection_status",
            ]
        )


class GitHubSurfaceAdapter:
    """Own GitHub issue write-back and its opaque signal surface state."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    def notify_run_started(self, run: Run) -> None:
        with transaction.atomic():
            signal = self._locked_signal(run)
            state = dict(signal.surface_state)
            start = dict(state.get("start", {}))
            installation_id, issue_number = self._origin(signal)
            if "comment_id" not in start:
                start["comment_id"] = self.client.post_issue_comment(
                    installation_id,
                    signal.repo.full_name,
                    issue_number,
                    (
                        "Foresight started this run. "
                        f"[Watch it]({settings.PUBLIC_BASE_URL}/orgs/"
                        f"{signal.org_id}/runs/{run.pk})."
                    ),
                )
                start["labels"] = []
                state["start"] = start
                self._save_state(signal, state)
            if IN_PROGRESS_LABEL not in start["labels"]:
                self.client.add_issue_labels(
                    installation_id,
                    signal.repo.full_name,
                    issue_number,
                    (IN_PROGRESS_LABEL,),
                )
                start["labels"].append(IN_PROGRESS_LABEL)
                state["start"] = start
                self._save_state(signal, state)

    def notify_run_finished(self, run: Run) -> None:
        if run.state not in {RunState.AWAITING_REVIEW, RunState.FAILED}:
            return
        with transaction.atomic():
            signal = self._locked_signal(run)
            state = dict(signal.surface_state)
            finish = dict(state.get("finish", {}))
            installation_id, issue_number = self._origin(signal)
            if "comment_id" not in finish:
                finish["comment_id"] = self.client.post_issue_comment(
                    installation_id,
                    signal.repo.full_name,
                    issue_number,
                    self._finish_comment(run),
                )
                finish["labels"] = []
                finish["removed_labels"] = []
                state["finish"] = finish
                self._save_state(signal, state)
            if run.state == RunState.AWAITING_REVIEW and PR_OPEN_LABEL not in finish["labels"]:
                self.client.add_issue_labels(
                    installation_id,
                    signal.repo.full_name,
                    issue_number,
                    (PR_OPEN_LABEL,),
                )
                finish["labels"].append(PR_OPEN_LABEL)
                state["finish"] = finish
                self._save_state(signal, state)
            if IN_PROGRESS_LABEL not in finish["removed_labels"]:
                self.client.remove_issue_label(
                    installation_id,
                    signal.repo.full_name,
                    issue_number,
                    IN_PROGRESS_LABEL,
                )
                finish["removed_labels"].append(IN_PROGRESS_LABEL)
                state["finish"] = finish
                self._save_state(signal, state)

    @staticmethod
    def _locked_signal(run: Run) -> Signal:
        return (
            Signal.objects.select_for_update(of=("self",))
            .select_related(
                "repo",
                "origin_connection",
            )
            .get(pk=run.signal_id)
        )

    @staticmethod
    def _origin(signal: Signal) -> tuple[int, int]:
        if signal.origin_connection is None:
            raise ValueError("GitHub signals require an origin surface connection")
        return (
            int(signal.origin_connection.identity["installation_id"]),
            int(signal.origin_reference["issue_number"]),
        )

    @staticmethod
    def _save_state(signal: Signal, state: dict[str, Any]) -> None:
        signal.surface_state = state
        signal.save(update_fields=["surface_state"])

    @staticmethod
    def _finish_comment(run: Run) -> str:
        if run.state == RunState.FAILED:
            reason = run.failure_reason or "unknown"
            explanation = run.failure_detail or run.summary
            comment = f"Foresight could not complete this run. Failure reason: {reason}"
            if explanation:
                comment += f". {explanation}"
            return comment
        pull_number = run.pr_url.rstrip("/").rsplit("/", 1)[-1]
        return (
            f"Foresight finished this run and opened [pull request #{pull_number}]({run.pr_url})."
        )
