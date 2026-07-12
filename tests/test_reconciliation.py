import pytest

from core.intake import create_manual_signal
from core.models import FailureReason, Org, Repo, RunState
from executor import (
    FakeExecutor,
    FakeExecutorScript,
    SandboxHandle,
    SandboxRecord,
    SandboxSpec,
)
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
    assert fake.calls == ["list_sandboxes", "list_sandboxes", "destroy"]


@pytest.mark.django_db
def test_reconciliation_rechecks_provider_before_failing_newly_checkpointed_run() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, run = create_manual_signal(
        repo=repo,
        title="Fix widgets",
        body="Checkpoint during the sweep.",
        enqueue_run=lambda run_id: run_id,
    )

    def checkpoint_sandbox_after_inventory_snapshot() -> None:
        handle = fake.create_sandbox(
            SandboxSpec(
                snapshot="repo:acme/widgets",
                git_ref="main",
                git_token=None,
                env_files=[],
                setup_script=None,
                labels={"run_id": str(run.pk)},
                resources=None,
            )
        )
        run.state = RunState.PROVISIONING
        run.sandbox_id = handle.sandbox_id
        run.save(update_fields=["state", "sandbox_id"])

    fake = FakeExecutor(
        FakeExecutorScript(after_list_once=checkpoint_sandbox_after_inventory_snapshot)
    )

    reconcile_sandboxes(fake)

    run.refresh_from_db()
    assert run.state == RunState.PROVISIONING
    assert fake.calls == ["list_sandboxes", "create_sandbox", "list_sandboxes"]
