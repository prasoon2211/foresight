import time
from typing import Protocol, cast

import pytest
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from core.intake import create_manual_signal
from core.models import Org, Repo, RunState
from executor import FakeExecutor, FakeExecutorScript
from orchestration.executor_backend import use_executor
from orchestration.run_orchestrator import orchestrate_run
from orchestration.tasks import enqueue_run_orchestrator


class WorkerConnectorFactory(Protocol):
    def get_worker_connector(self) -> BaseAsyncConnector: ...


@pytest.mark.django_db(transaction=True)
def test_queued_run_starts_automatically_when_org_slot_frees() -> None:
    org = Org.objects.create(name="Acme", concurrency_cap=1)
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    _, first = create_manual_signal(
        repo=repo,
        title="First",
        body="Occupy the only slot.",
        enqueue_run=lambda run_id: run_id,
    )
    fake = FakeExecutor(FakeExecutorScript(interrupt_before_stream_once=True))
    with pytest.raises(RuntimeError, match="worker interrupted"):
        orchestrate_run(first.pk, fake)

    _, second = create_manual_signal(
        repo=repo,
        title="Second",
        body="Wait for the slot.",
        enqueue_run=enqueue_run_orchestrator,
    )
    connector = cast(WorkerConnectorFactory, app.connector)
    with use_executor(fake), app.replace_connector(connector.get_worker_connector()):
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )
        second.refresh_from_db()
        assert second.state == RunState.QUEUED
        assert len(fake.sandbox_specs) == 1

        orchestrate_run(first.pk, fake)
        time.sleep(1.1)
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.state == RunState.AWAITING_REVIEW
    assert second.state == RunState.AWAITING_REVIEW
    assert len(fake.sandbox_specs) == 2
