from core.models import FailureReason, Run, RunState
from core.run_control import fail_run
from executor import DurableExecutor


def reconcile_sandboxes(executor: DurableExecutor) -> None:
    """Destroy provider sandboxes that have no live Run."""
    sandboxes = executor.list_sandboxes()
    run_ids = {sandbox.run_id for sandbox in sandboxes if sandbox.run_id is not None}
    states = dict(Run.objects.filter(pk__in=run_ids).values_list("pk", "state"))
    provider_sandbox_ids = {sandbox.handle.sandbox_id for sandbox in sandboxes}

    for sandbox in sandboxes:
        state = states.get(sandbox.run_id) if sandbox.run_id is not None else None
        if state is None or state in {RunState.DONE, RunState.FAILED}:
            executor.destroy(sandbox.handle)

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
