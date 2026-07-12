import hashlib
import hmac
from pathlib import Path
from typing import Protocol, cast

import pytest
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import Client, override_settings
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from core.intake import StrandedSignal, dispatch_signal
from core.models import (
    ConnectionStatus,
    FailureReason,
    IntakeState,
    Org,
    OrgMembership,
    Repo,
    ResultStatus,
    RunState,
    Signal,
    SignalSource,
    SnapshotBuildStatus,
    SurfaceConnection,
    SurfaceConnectionStatus,
    SurfaceType,
)
from executor import AgentResult, FakeExecutor
from orchestration.executor_backend import use_executor
from surfaces.github import GitHubSurfaceAdapter
from surfaces.github_client import FakeGitHubClient, use_github_client

FIXTURES = Path(__file__).parent / "fixtures" / "github"
WEBHOOK_SECRET = "test-webhook-secret"


class WorkerConnectorFactory(Protocol):
    def get_worker_connector(self) -> BaseAsyncConnector: ...


def run_jobs() -> None:
    connector = cast(WorkerConnectorFactory, app.connector)
    with app.replace_connector(connector.get_worker_connector()):
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )


def post_webhook(client: Client, event: str, fixture: str) -> HttpResponse:
    body = (FIXTURES / fixture).read_bytes()
    signature = (
        "sha256="
        + hmac.new(
            WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
    )
    return cast(
        HttpResponse,
        client.post(
            "/api/webhooks/github",
            data=body,
            content_type="application/json",
            headers={
                "X-GitHub-Event": event,
                "X-Hub-Signature-256": signature,
            },
        ),
    )


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_github_webhook_rejects_a_bad_signature(client: Client) -> None:
    response = client.post(
        "/api/webhooks/github",
        data=b'{"zen":"Keep it logically awesome."}',
        content_type="application/json",
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": "sha256=bad",
        },
    )

    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_installation_webhooks_activate_connection_and_enable_selected_repos(
    client: Client,
) -> None:
    org = Org.objects.create(name="Acme")

    created_response = post_webhook(client, "installation", "installation_created.json")
    repos_response = post_webhook(
        client,
        "installation_repositories",
        "installation_repositories_added.json",
    )

    assert created_response.status_code == 202
    assert repos_response.status_code == 202
    connection = SurfaceConnection.objects.get(org=org)
    assert connection.status == SurfaceConnectionStatus.ACTIVE
    assert connection.identity == {
        "installation_id": 12345678,
        "account_id": 583231,
    }
    repo = Repo.objects.get(org=org, full_name="acme/widgets")
    assert repo.surface_connection == connection
    assert repo.connection_status == ConnectionStatus.CONNECTED
    assert repo.default_branch == "main"
    assert repo.base_snapshot == "node:22-bookworm"
    assert repo.snapshot_build_status == SnapshotBuildStatus.BUILDING
    assert repo.setup_script == ""
    assert repo.harness_prompt


@pytest.mark.django_db(transaction=True)
@override_settings(
    GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET,
    PUBLIC_BASE_URL="https://foresight.example",
)
def test_labeled_issue_runs_to_github_writeback_and_renotify_is_idempotent(
    client: Client,
) -> None:
    org = Org.objects.create(name="Acme")
    SurfaceConnection.objects.create(
        org=org,
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.PENDING,
        account_label="acme",
        identity={},
    )
    post_webhook(client, "installation", "installation_created.json")
    post_webhook(
        client,
        "installation_repositories",
        "installation_repositories_added.json",
    )
    fake_executor = FakeExecutor.succeeding(
        AgentResult(
            status=ResultStatus.PR_OPENED,
            pr_url="https://github.com/acme/widgets/pull/17",
            summary="Fixed the widget race.",
            confidence=0.92,
        )
    )
    fake_github = FakeGitHubClient()

    with use_executor(fake_executor), use_github_client(fake_github):
        run_jobs()
        response = post_webhook(client, "issues", "issues_labeled.json")
        assert response.status_code == 202
        signal = Signal.objects.get()
        run = signal.runs.get()
        assert signal.source == SignalSource.GITHUB_ISSUE
        assert signal.intake_state == IntakeState.DISPATCHED
        assert signal.origin_reference == {
            "issue_id": 987654321,
            "issue_number": 42,
            "url": "https://github.com/acme/widgets/issues/42",
        }
        assert run.state == RunState.QUEUED

        run_jobs()

        run.refresh_from_db()
        signal.refresh_from_db()
        assert run.state == RunState.AWAITING_REVIEW
        calls_after_run = list(fake_github.calls)
        adapter = GitHubSurfaceAdapter(fake_github)
        adapter.notify_run_started(run)
        adapter.notify_run_finished(run)
        merged_response = post_webhook(
            client,
            "pull_request",
            "pull_request_merged.json",
        )
        run.refresh_from_db()

    assert fake_github.calls == calls_after_run
    assert merged_response.status_code == 202
    assert run.state == RunState.DONE
    assert run.pr_merged_at is not None
    assert fake_github.comments == [
        (
            "acme/widgets",
            42,
            "Foresight started this run. "
            f"[Watch it](https://foresight.example/orgs/{org.pk}/runs/{run.pk}).",
        ),
        (
            "acme/widgets",
            42,
            "Foresight finished this run and opened "
            "[pull request #17](https://github.com/acme/widgets/pull/17).",
        ),
    ]
    assert fake_github.label_additions == [
        ("acme/widgets", 42, ("foresight:in-progress",)),
        ("acme/widgets", 42, ("foresight:pr-open",)),
    ]
    assert fake_github.label_removals == [
        ("acme/widgets", 42, "foresight:in-progress"),
    ]
    assert signal.surface_state == {
        "start": {
            "comment_id": 1,
            "labels": ["foresight:in-progress"],
        },
        "finish": {
            "comment_id": 2,
            "labels": ["foresight:pr-open"],
            "removed_labels": ["foresight:in-progress"],
        },
    }


@pytest.mark.django_db(transaction=True)
@override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_uninstall_strands_signals_and_reinstall_unstrands_them(client: Client) -> None:
    user = get_user_model().objects.create_user(
        username="member",
        email="member@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(
        org=org,
        user=user,
        role=OrgMembership.Role.MEMBER,
    )
    connection = SurfaceConnection.objects.create(
        org=org,
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.PENDING,
        account_label="acme",
        identity={},
    )
    post_webhook(client, "installation", "installation_created.json")
    post_webhook(
        client,
        "installation_repositories",
        "installation_repositories_added.json",
    )
    repo = Repo.objects.get(org=org, full_name="acme/widgets")
    repo.snapshot_build_status = SnapshotBuildStatus.READY
    repo.save(update_fields=["snapshot_build_status"])
    signal = Signal.objects.create(
        org=org,
        repo=repo,
        source=SignalSource.GITHUB_ISSUE,
        title="Fix widget race",
        body="Two updates can overwrite one another.",
    )
    client.force_login(user)

    deleted_response = post_webhook(client, "installation", "installation_deleted.json")

    assert deleted_response.status_code == 202
    connection.refresh_from_db()
    repo.refresh_from_db()
    assert connection.status == SurfaceConnectionStatus.REVOKED
    assert repo.connection_status == ConnectionStatus.DISCONNECTED
    stranded_response = client.get(f"/api/orgs/{org.pk}/signals/{signal.pk}")
    assert stranded_response.status_code == 200
    assert stranded_response.json()["stranded"] is True
    with pytest.raises(StrandedSignal):
        dispatch_signal(signal=signal, enqueue_run=lambda run_id: run_id)

    reinstalled_response = post_webhook(
        client,
        "installation",
        "installation_reinstalled.json",
    )

    assert reinstalled_response.status_code == 202
    connection.refresh_from_db()
    repo.refresh_from_db()
    assert connection.status == SurfaceConnectionStatus.ACTIVE
    assert connection.identity["installation_id"] == 87654321
    assert repo.connection_status == ConnectionStatus.CONNECTED
    unstranded_response = client.get(f"/api/orgs/{org.pk}/signals/{signal.pk}")
    assert unstranded_response.status_code == 200
    assert unstranded_response.json()["stranded"] is False
    run = dispatch_signal(signal=signal, enqueue_run=lambda run_id: run_id)
    assert run.state == RunState.QUEUED


@pytest.mark.django_db
@override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_merged_pull_request_marks_run_and_signal_done(client: Client) -> None:
    user = get_user_model().objects.create_user(
        username="member",
        email="member@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(
        org=org,
        user=user,
        role=OrgMembership.Role.MEMBER,
    )
    connection = SurfaceConnection.objects.create(
        org=org,
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.ACTIVE,
        account_label="acme",
        identity={"installation_id": 12345678},
    )
    repo = Repo.objects.create(
        org=org,
        surface_connection=connection,
        full_name="acme/widgets",
    )
    signal = Signal.objects.create(
        org=org,
        repo=repo,
        origin_connection=connection,
        source=SignalSource.GITHUB_ISSUE,
        intake_state=IntakeState.DISPATCHED,
        title="Fix widget race",
        body="Two updates can overwrite one another.",
    )
    run = signal.runs.create(
        state=RunState.RUNNING,
        branch_name="foresight/signal-1",
    )
    client.force_login(user)

    response = post_webhook(client, "pull_request", "pull_request_merged.json")

    assert response.status_code == 202
    run.refresh_from_db()
    assert run.state == RunState.DONE
    assert run.pr_merged_at is not None
    signal_response = client.get(f"/api/orgs/{org.pk}/signals/{signal.pk}")
    assert signal_response.status_code == 200
    assert signal_response.json()["outcome_status"] == RunState.DONE


@pytest.mark.django_db(transaction=True)
@override_settings(GITHUB_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_failed_run_writeback_explains_failure_reason(client: Client) -> None:
    org = Org.objects.create(name="Acme")
    SurfaceConnection.objects.create(
        org=org,
        type=SurfaceType.GITHUB,
        status=SurfaceConnectionStatus.PENDING,
        account_label="acme",
        identity={"installation_id": 12345678},
    )
    post_webhook(client, "installation", "installation_created.json")
    post_webhook(
        client,
        "installation_repositories",
        "installation_repositories_added.json",
    )
    fake_executor = FakeExecutor.succeeding(
        AgentResult(
            status=ResultStatus.FAILED,
            pr_url="",
            summary="The agent could not resolve the issue.",
            confidence=0.2,
        )
    )
    fake_github = FakeGitHubClient()

    with use_executor(fake_executor), use_github_client(fake_github):
        run_jobs()
        response = post_webhook(client, "issues", "issues_labeled.json")
        assert response.status_code == 202
        run_jobs()

    run = Signal.objects.get().runs.get()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.AGENT_REPORTED_FAILED
    assert fake_github.comments == [
        (
            "acme/widgets",
            42,
            "Foresight started this run. "
            f"[Watch it](http://localhost:8000/orgs/{org.pk}/runs/{run.pk}).",
        ),
        (
            "acme/widgets",
            42,
            "Foresight could not complete this run. Failure reason: agent_reported_failed. "
            "The agent could not resolve the issue.",
        ),
    ]
    assert fake_github.label_additions == [
        ("acme/widgets", 42, ("foresight:in-progress",)),
    ]
    assert fake_github.label_removals == [
        ("acme/widgets", 42, "foresight:in-progress"),
    ]
