import logging
from typing import Protocol, cast

import pytest
from django.db import transaction
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from orchestration.tasks import enqueue_demo_job


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
