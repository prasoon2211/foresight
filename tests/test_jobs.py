import logging
from typing import Protocol, cast

import pytest
from asgiref.sync import async_to_sync
from django.db import transaction
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from orchestration.tasks import (
    enqueue_demo_job,
    enqueue_run_orchestrator,
    requeue_stalled_run_jobs,
    run_orchestrator,
)


class ForceTransactionRollback(Exception):
    pass


class WorkerConnectorFactory(Protocol):
    def get_worker_connector(self) -> BaseAsyncConnector: ...


@pytest.mark.django_db(transaction=True)
def test_demo_job_is_enqueued_in_transaction_and_run_in_process(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="orchestration.tasks")

    with pytest.raises(ForceTransactionRollback):
        with transaction.atomic():
            enqueue_demo_job(message="must roll back")
            raise ForceTransactionRollback

    with transaction.atomic():
        enqueue_demo_job(message="must execute")

    connector = cast(WorkerConnectorFactory, app.connector)
    with app.replace_connector(connector.get_worker_connector()):
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )

    demo_messages = [
        record.getMessage() for record in caplog.records if record.name == "orchestration.tasks"
    ]
    assert demo_messages == ["Demo job executed: must execute"]


@pytest.mark.django_db(transaction=True)
def test_stalled_run_job_is_requeued_with_same_run_pointer() -> None:
    with transaction.atomic():
        job_id = enqueue_run_orchestrator(42)

    async def simulate_worker_death() -> tuple[int, int]:
        async with app.open_async():
            worker_id = await app.job_manager.register_worker()
            claimed = await app.job_manager.fetch_job(queues=None, worker_id=worker_id)
            assert claimed is not None
            assert claimed.id == job_id

            await app.job_manager.prune_stalled_workers(seconds_since_heartbeat=-1)
            stalled = list(await app.job_manager.get_stalled_jobs(task_name=run_orchestrator.name))
            assert [job.id for job in stalled] == [job_id]

            await requeue_stalled_run_jobs.func(timestamp=0)
            replacement_worker_id = await app.job_manager.register_worker()
            retried = await app.job_manager.fetch_job(
                queues=None,
                worker_id=replacement_worker_id,
            )
            assert retried is not None
            assert retried.id is not None
            retried_run_id = retried.task_kwargs["run_id"]
            assert isinstance(retried_run_id, int)
            return retried.id, retried_run_id

    connector = cast(WorkerConnectorFactory, app.connector)
    with app.replace_connector(connector.get_worker_connector()):
        retried_job_id, retried_run_id = async_to_sync(simulate_worker_death)()

    assert retried_job_id == job_id
    assert retried_run_id == 42
