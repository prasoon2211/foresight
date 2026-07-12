import pytest

from core.intake import create_manual_signal
from core.models import Org, Repo, RunState
from executor import FakeExecutor
from orchestration.run_orchestrator import orchestrate_run


@pytest.mark.django_db
def test_reinvocation_after_sandbox_checkpoint_does_not_create_another_sandbox() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Resume after worker death.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(interrupt_before_launch_once=True)

    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(run.pk, fake)
    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.AWAITING_REVIEW
    assert len(fake.sandbox_specs) == 1
    assert len(fake.agent_launches) == 1


@pytest.mark.django_db
def test_reinvocation_after_agent_checkpoint_reattaches_to_same_session() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Resync after worker death.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(interrupt_before_stream_once=True)

    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(run.pk, fake)
    orchestrate_run(run.pk, fake)

    run.refresh_from_db()
    assert run.state == RunState.AWAITING_REVIEW
    assert len(fake.sandbox_specs) == 1
    assert len(fake.agent_launches) == 1
    assert len(fake.streamed_sessions) == 1
    assert fake.streamed_sessions[0].session_id == run.agent_session_id
