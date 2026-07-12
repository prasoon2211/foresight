from django.db import transaction

from core.models import FailureReason, Run, RunState
from executor import Executor, SandboxHandle


def fail_run(
    *,
    run: Run,
    executor: Executor,
    reason: FailureReason,
    detail: str = "",
    allowed_states: set[str] | None = None,
) -> Run:
    """Persist a failed Run and idempotently tear down its sandbox."""
    with transaction.atomic():
        run = Run.objects.select_for_update().get(pk=run.pk)
        if allowed_states is not None and run.state not in allowed_states:
            raise ValueError("only queued, provisioning, or running runs can be stopped")
        if run.state != RunState.FAILED:
            run.state = RunState.FAILED
            run.failure_reason = reason
            run.failure_detail = detail
            run.save(update_fields=["state", "failure_reason", "failure_detail", "updated_at"])

    if run.sandbox_id:
        executor.destroy(SandboxHandle(sandbox_id=run.sandbox_id))
    return run


def stop_run(*, run: Run, executor: Executor) -> Run:
    """Cancel an executing run and tear down its sandbox."""
    return fail_run(
        run=run,
        executor=executor,
        reason=FailureReason.CANCELED,
        allowed_states={
            RunState.QUEUED,
            RunState.PROVISIONING,
            RunState.RUNNING,
        },
    )
