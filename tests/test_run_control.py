import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.intake import create_manual_signal
from core.models import FailureReason, Org, OrgMembership, Repo, RunState
from executor import FakeExecutor, FakeExecutorScript
from orchestration.executor_backend import use_executor
from orchestration.run_orchestrator import orchestrate_run


@pytest.fixture
def org_context(client: Client) -> tuple[Client, Org, Repo]:
    user = get_user_model().objects.create_user(
        username="run-controller",
        email="run-controller@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(
        org=org,
        user=user,
        role=OrgMembership.Role.MEMBER,
    )
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    client.force_login(user)
    return client, org, repo


@pytest.mark.django_db
def test_stop_running_run_via_api_cancels_and_retains_sandbox(
    org_context: tuple[Client, Org, Repo],
) -> None:
    client, org, repo = org_context
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Stop this doomed run.",
        enqueue_run=lambda run_id: run_id,
    )
    stop_responses = []

    def stop_while_streaming() -> None:
        stop_responses.append(client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/stop"))

    fake = FakeExecutor(FakeExecutorScript(before_stream=stop_while_streaming))
    with use_executor(fake):
        orchestrate_run(run.pk, fake)

    response = stop_responses[0]

    assert response.status_code == 200
    assert response.json() == {
        "id": run.pk,
        "signal_id": run.signal_id,
        "state": RunState.FAILED,
        "failure_reason": FailureReason.CANCELED,
        "failure_detail": "",
        "result": None,
    }
    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.CANCELED
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "archive",
    ]


@pytest.mark.django_db
def test_stop_during_sandbox_creation_retains_newly_created_sandbox(
    org_context: tuple[Client, Org, Repo],
) -> None:
    client, org, repo = org_context
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Cancel while provisioning.",
        enqueue_run=lambda run_id: run_id,
    )

    def stop_after_creation() -> None:
        response = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/stop")
        assert response.status_code == 200

    fake = FakeExecutor(FakeExecutorScript(after_create=stop_after_creation))
    with use_executor(fake):
        orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.CANCELED
    assert fake.calls == ["create_sandbox", "archive"]
    assert len(fake.list_sandboxes()) == 1


@pytest.mark.django_db
def test_stop_during_agent_launch_stays_canceled(
    org_context: tuple[Client, Org, Repo],
) -> None:
    client, org, repo = org_context
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Cancel while the agent launches.",
        enqueue_run=lambda run_id: run_id,
    )

    def stop_after_launch() -> None:
        response = client.post(f"/api/orgs/{org.pk}/runs/{run.pk}/stop")
        assert response.status_code == 200

    fake = FakeExecutor(FakeExecutorScript(after_launch=stop_after_launch))
    with use_executor(fake):
        orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.CANCELED
    assert fake.calls == ["create_sandbox", "launch_agent", "archive"]


@pytest.mark.django_db(transaction=True)
def test_rerun_via_api_creates_fresh_run_and_sandbox(
    org_context: tuple[Client, Org, Repo],
) -> None:
    client, org, repo = org_context
    signal, old_run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Try again from scratch.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(interrupt_before_stream_once=True))
    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(old_run.pk, fake)
    with use_executor(fake):
        stop_response = client.post(f"/api/orgs/{org.pk}/runs/{old_run.pk}/stop")
        rerun_response = client.post(f"/api/orgs/{org.pk}/signals/{signal.pk}/rerun")

    assert stop_response.status_code == 200
    assert rerun_response.status_code == 201
    new_run_id = rerun_response.json()["id"]
    assert new_run_id != old_run.pk
    assert rerun_response.json()["state"] == RunState.QUEUED

    old_run.refresh_from_db()
    assert old_run.state == RunState.FAILED
    assert old_run.failure_reason == FailureReason.CANCELED

    orchestrate_run(new_run_id, fake)

    old_run.refresh_from_db()
    assert old_run.state == RunState.FAILED
    assert old_run.failure_reason == FailureReason.CANCELED
    assert len(fake.sandbox_specs) == 2
    assert fake.sandbox_specs[1].labels["run_id"] == str(new_run_id)
