from typing import cast

import pytest
from django.db import transaction
from procrastinate.contrib.django import app
from procrastinate.contrib.django.django_connector import DjangoConnector
from procrastinate.contrib.django.models import ProcrastinateJob

from orchestration.tasks import enqueue_demo_job


class RollBackDemoJob(Exception):
    pass


@pytest.mark.django_db(transaction=True)
def test_demo_job_is_enqueued_in_transaction_and_run_in_process() -> None:
    with pytest.raises(RollBackDemoJob):
        with transaction.atomic():
            enqueue_demo_job(message="must roll back")
            raise RollBackDemoJob

    assert not ProcrastinateJob.objects.exists()

    with transaction.atomic():
        job_id = enqueue_demo_job(message="must execute")

    queued_job = ProcrastinateJob.objects.get(id=job_id)
    assert queued_job.status == "todo"

    django_connector = cast(DjangoConnector, app.connector)
    with app.replace_connector(django_connector.get_worker_connector()):
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )

    queued_job.refresh_from_db()
    assert queued_job.status == "succeeded"
