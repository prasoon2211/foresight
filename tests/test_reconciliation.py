import pytest

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
