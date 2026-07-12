import logging

from django.db import connection
from procrastinate.contrib.django import app

from orchestration.executor_backend import get_executor
from orchestration.run_orchestrator import orchestrate_run

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
    orchestrate_run(run_id, get_executor())


def enqueue_run_orchestrator(run_id: int) -> int:
    """Enqueue a run pointer in the dispatch transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("run orchestrators must be enqueued inside transaction.atomic()")

    return run_orchestrator.defer(run_id=run_id)
