from core.models import Run, RunState
from executor import Executor


def reconcile_sandboxes(executor: Executor) -> None:
    """Destroy provider sandboxes that have no live Run."""
    sandboxes = executor.list_sandboxes()
    run_ids = {
        int(run_id)
        for sandbox in sandboxes
        if (run_id := sandbox.labels.get("run_id", "")).isdigit()
    }
    states = dict(Run.objects.filter(pk__in=run_ids).values_list("pk", "state"))

    for sandbox in sandboxes:
        run_id = sandbox.labels.get("run_id", "")
        state = states.get(int(run_id)) if run_id.isdigit() else None
        if state is None or state in {RunState.DONE, RunState.FAILED}:
            executor.destroy(sandbox.handle)
