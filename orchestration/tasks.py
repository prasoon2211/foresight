import logging

from django.db import connection
from django.utils import timezone
from procrastinate.contrib.django import app

from orchestration.executor_backend import get_executor
from orchestration.reconciliation import reconcile_sandboxes
from orchestration.run_orchestrator import RunJobOutcome, orchestrate_run

logger = logging.getLogger(__name__)


@app.task
def demo_job(message: str) -> None:
    logger.info("Demo job executed: %s", message)


def enqueue_demo_job(*, message: str) -> int:
    """Enqueue the scaffold probe atomically with the caller's database writes."""
    if not connection.in_atomic_block:
        raise RuntimeError("demo jobs must be enqueued inside transaction.atomic()")

    return demo_job.defer(message=message)


@app.task
def run_orchestrator(run_id: int) -> None:
    outcome = orchestrate_run(run_id, get_executor())
    if outcome == RunJobOutcome.POSTPONED:
        run_orchestrator.configure(schedule_in={"seconds": 1}).defer(run_id=run_id)


def enqueue_run_orchestrator(run_id: int) -> int:
    """Enqueue a run pointer in the dispatch transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("run orchestrators must be enqueued inside transaction.atomic()")

    return run_orchestrator.defer(run_id=run_id)


@app.periodic(cron="*/5 * * * *")
@app.task
def reconciliation_sweep(timestamp: int) -> None:
    del timestamp
    reconcile_sandboxes(get_executor())


@app.periodic(cron="* * * * *")
@app.task
async def requeue_stalled_run_jobs(timestamp: int) -> None:
    del timestamp
    stalled_jobs = await app.job_manager.get_stalled_jobs(task_name=run_orchestrator.name)
    for job in stalled_jobs:
        if job.id is not None:
            await app.job_manager.retry_job(job=job, retry_at=timezone.now())
