import pytest

from core.intake import create_manual_signal
from core.models import FailureReason, Org, Repo, RunState
from executor import FakeExecutor, SandboxHandle, SandboxRecord
from orchestration.reconciliation import reconcile_sandboxes


@pytest.mark.django_db
def test_reconciliation_destroys_orphaned_sandbox() -> None:
    orphan = SandboxRecord(
        handle=SandboxHandle(sandbox_id="orphaned-sandbox"),
        labels={"run_id": "999999"},
    )
    fake = FakeExecutor(inventory=[orphan])

    reconcile_sandboxes(fake)

    assert fake.list_sandboxes() == []
    assert fake.calls == ["list_sandboxes", "destroy", "list_sandboxes"]


@pytest.mark.django_db
def test_reconciliation_fails_run_when_its_sandbox_disappears() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="The provider lost the sandbox.",
        enqueue_run=lambda run_id: run_id,
    )
    run.state = RunState.RUNNING
    run.sandbox_id = "missing-sandbox"
    run.agent_session_id = "missing-session"
    run.save(update_fields=["state", "sandbox_id", "agent_session_id"])
    fake = FakeExecutor()

    reconcile_sandboxes(fake)

    run.refresh_from_db()
    assert run.state == RunState.FAILED
    assert run.failure_reason == FailureReason.SANDBOX_DIED
    assert fake.calls == ["list_sandboxes", "destroy"]
