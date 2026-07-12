from django.utils import timezone

from core.models import FailureReason, Run, RunState
from core.run_control import fail_run
from executor import DurableExecutor


def reconcile_sandboxes(executor: DurableExecutor) -> None:
    """Destroy provider sandboxes that have no live Run."""
    sandboxes = executor.list_sandboxes()
    run_ids = {sandbox.run_id for sandbox in sandboxes if sandbox.run_id is not None}
    runs = {
        run.pk: run
        for run in Run.objects.filter(pk__in=run_ids).only(
            "pk",
            "state",
            "sandbox_archived_at",
        )
    }
    provider_sandbox_ids = {sandbox.handle.sandbox_id for sandbox in sandboxes}

    for sandbox in sandboxes:
        run = runs.get(sandbox.run_id) if sandbox.run_id is not None else None
        if run is None:
            executor.destroy(sandbox.handle)
        elif run.state in {RunState.DONE, RunState.FAILED} and run.sandbox_archived_at is None:
            executor.archive(sandbox.handle)
            run.sandbox_archived_at = timezone.now()
            run.save(update_fields=["sandbox_archived_at", "updated_at"])

    missing_runs = (
        Run.objects.filter(
            state__in=[RunState.PROVISIONING, RunState.RUNNING],
        )
        .exclude(sandbox_id="")
        .exclude(sandbox_id__in=provider_sandbox_ids)
    )
    if missing_runs:
        provider_sandbox_ids.update(
            sandbox.handle.sandbox_id for sandbox in executor.list_sandboxes()
        )
    for run in missing_runs:
        if run.sandbox_id in provider_sandbox_ids:
            continue
        fail_run(
            run=run,
            executor=executor,
            reason=FailureReason.SANDBOX_DIED,
        )
