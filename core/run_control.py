from django.db import transaction

from core.models import FailureReason, Run, RunState
from executor import Executor, SandboxHandle


def stop_run(*, run: Run, executor: Executor) -> Run:
    """Cancel an executing run and tear down its sandbox."""
    with transaction.atomic():
        run = Run.objects.select_for_update().get(pk=run.pk)
        if run.state not in {
            RunState.QUEUED,
            RunState.PROVISIONING,
            RunState.RUNNING,
        }:
            raise ValueError("only queued, provisioning, or running runs can be stopped")
        run.state = RunState.FAILED
        run.failure_reason = FailureReason.CANCELED
        run.save(update_fields=["state", "failure_reason", "updated_at"])

    if run.sandbox_id:
        executor.destroy(SandboxHandle(sandbox_id=run.sandbox_id))
    return run
