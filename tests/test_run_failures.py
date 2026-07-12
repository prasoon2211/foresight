import pytest

from core.intake import create_manual_signal
from core.models import FailureReason, Org, Repo, ResultStatus, RunState
from executor import AgentEvent, AgentResult, FakeExecutor, FakeExecutorScript
from orchestration.run_orchestrator import orchestrate_run


@pytest.mark.django_db
def test_setup_failure_records_reason_and_output() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The setup must run first.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(setup_failure="uv sync exited 1"))

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.SETUP_FAILED
    assert run.failure_detail == "uv sync exited 1"
    assert fake.calls == ["create_sandbox"]


@pytest.mark.django_db
def test_sandbox_death_mid_stream_records_reason_and_tears_down() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The sandbox disappears.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(sandbox_dies=True))

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.SANDBOX_DIED
    assert fake.calls == ["create_sandbox", "launch_agent", "stream_events", "destroy"]


@pytest.mark.django_db
def test_agent_session_error_records_reason_and_retains_sandbox() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The agent runtime errors.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(event_batches=[[AgentEvent(kind="session.error")]]))

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.AGENT_ERROR
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "archive",
    ]


@pytest.mark.django_db
def test_agent_reported_failure_records_reason_and_result() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The agent cannot resolve it.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor.succeeding(
        AgentResult(
            status=ResultStatus.FAILED,
            pr_url="",
            summary="The upstream API is undocumented.",
            confidence=0.95,
        )
    )

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.AGENT_REPORTED_FAILED
    assert run.result_status == ResultStatus.FAILED
    assert run.summary == "The upstream API is undocumented."
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "archive",
    ]


@pytest.mark.django_db
def test_agent_reported_blocked_records_reason_and_result() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The environment blocks progress.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor.succeeding(
        AgentResult(
            status=ResultStatus.BLOCKED,
            pr_url="",
            summary="The required service is unreachable.",
            confidence=1.0,
        )
    )

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.AGENT_REPORTED_BLOCKED
    assert run.result_status == ResultStatus.BLOCKED
    assert run.summary == "The required service is unreachable."
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "archive",
    ]


@pytest.mark.django_db
def test_idle_session_without_result_records_reason_and_retains_sandbox() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The agent goes idle without reporting.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(event_batches=[[AgentEvent(kind="session.idle")]]))

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.NO_RESULT
    assert run.result_status == ResultStatus.FAILED
    assert run.pr_url == ""
    assert run.summary == "Run produced no parseable result."
    assert run.confidence == 0
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "read_file",
        "archive",
    ]


@pytest.mark.django_db
def test_success_result_without_pr_url_records_no_result() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="A success must identify its pull request.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor.succeeding(
        AgentResult(
            status=ResultStatus.PR_OPENED,
            pr_url="",
            summary="Claimed success without a pull request.",
            confidence=0.8,
        )
    )

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.NO_RESULT
    assert run.result_status == ResultStatus.FAILED
    assert run.summary == "Run produced no parseable result."
    assert run.confidence == 0
    assert fake.calls == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "read_file",
        "archive",
    ]
