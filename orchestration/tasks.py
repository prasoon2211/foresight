import logging

from django.db import connection
from procrastinate.contrib.django import app

logger = logging.getLogger(__name__)


@app.task
def demo_job(message: str) -> None:
    logger.info("Demo job executed: %s", message)


def enqueue_demo_job(*, message: str) -> int:
    """Enqueue the scaffold probe atomically with the caller's database writes."""
    if not connection.in_atomic_block:
        raise RuntimeError("demo jobs must be enqueued inside transaction.atomic()")

    return demo_job.defer(message=message)
