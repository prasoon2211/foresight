import pytest

from core.intake import create_manual_signal
from core.models import FailureReason, Org, Repo, ResultStatus, RunState
from executor import (
    FakeExecutor,
    FakeExecutorScript,
    SandboxHandle,
    SandboxRecord,
)
from orchestration.run_orchestrator import orchestrate_run


@pytest.mark.django_db
def test_reinvocation_after_unrecorded_sandbox_creation_recovers_same_sandbox() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Resume after worker death.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(interrupt_after_create_once=True))

    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(run.pk, fake)
    run.refresh_from_db()
    assert run.sandbox_id == ""
    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.AWAITING_REVIEW
    assert len(fake.sandbox_specs) == 1
    assert len(fake.agent_launches) == 1


@pytest.mark.django_db
def test_reinvocation_replaces_partially_provisioned_sandbox() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Resume after setup was interrupted.",
        enqueue_run=lambda run_id: run_id,
    )
    run.state = RunState.PROVISIONING
    run.save(update_fields=["state"])
    fake = FakeExecutor(
        inventory=[
            SandboxRecord(
                handle=SandboxHandle("partial-sandbox"),
                labels={"run_id": str(run.pk)},
            )
        ]
    )

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.AWAITING_REVIEW
    assert run.sandbox_id != "partial-sandbox"
    assert fake.calls[:3] == ["list_sandboxes", "destroy", "create_sandbox"]


@pytest.mark.django_db
def test_reinvocation_after_unrecorded_agent_launch_recovers_same_session() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Resync after worker death.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(interrupt_after_launch_once=True))

    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(run.pk, fake)
    run.refresh_from_db()
    assert run.agent_session_id == ""
    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.AWAITING_REVIEW
    assert len(fake.sandbox_specs) == 1
    assert len(fake.agent_launches) == 1
    assert len(fake.streamed_sessions) == 1
    assert fake.streamed_sessions[0].session_id == run.agent_session_id


@pytest.mark.django_db
def test_reinvocation_after_synthesized_result_checkpoint_keeps_no_result_reason() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The agent did not report.",
        enqueue_run=lambda run_id: run_id,
    )
    run.state = RunState.RUNNING
    run.sandbox_id = "fake-sandbox-1"
    run.agent_session_id = "fake-session-1"
    run.agent_base_url = "fake://fake-sandbox-1"
    run.result_status = ResultStatus.FAILED
    run.summary = "Run produced no parseable result."
    run.confidence = 0
    run.failure_reason = FailureReason.NO_RESULT
    run.save()
    fake = FakeExecutor(
        inventory=[
            SandboxRecord(
                handle=SandboxHandle(run.sandbox_id),
                labels={"run_id": str(run.pk)},
            )
        ]
    )

    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.NO_RESULT
