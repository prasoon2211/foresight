import secrets
from collections.abc import Callable

from django.db import transaction

from core.models import (
    ConnectionStatus,
    IntakeState,
    Repo,
    Run,
    RunState,
    Signal,
    SignalSource,
    SnapshotBuildStatus,
)

RunEnqueuer = Callable[[int], object]


class StrandedSignal(Exception):
    pass


class SnapshotNotReady(Exception):
    pass


def _create_run(signal: Signal) -> Run:
    run = Run.objects.create(
        signal=signal,
        server_password=secrets.token_urlsafe(32),
    )
    run.branch_name = f"foresight/signal-{signal.pk}-run-{run.pk}"
    run.save(update_fields=["branch_name"])
    return run


def _refuse_stranded(signal: Signal) -> None:
    if (
        Repo.objects.values_list("connection_status", flat=True).get(pk=signal.repo_id)
        == ConnectionStatus.DISCONNECTED
    ):
        raise StrandedSignal("cannot dispatch a signal whose repo is disconnected")


def _refuse_unready_snapshot(signal: Signal) -> None:
    status, output = Repo.objects.values_list(
        "snapshot_build_status",
        "snapshot_build_output",
    ).get(pk=signal.repo_id)
    if status != SnapshotBuildStatus.READY:
        detail = f": {output}" if output else ""
        raise SnapshotNotReady(f"repo snapshot is {status}{detail}")


def create_manual_signal(
    *,
    repo: Repo,
    title: str,
    body: str,
    enqueue_run: RunEnqueuer,
) -> tuple[Signal, Run]:
    with transaction.atomic():
        signal = Signal.objects.create(
            org=repo.org,
            repo=repo,
            source=SignalSource.MANUAL,
            title=title,
            body=body,
        )
        run = dispatch_signal(signal=signal, enqueue_run=enqueue_run)
    return signal, run


def dispatch_signal(*, signal: Signal, enqueue_run: RunEnqueuer) -> Run:
    """End intake and atomically publish a queued run."""
    if signal.intake_state != IntakeState.RECEIVED:
        raise ValueError("only received signals can be dispatched")
    _refuse_stranded(signal)
    _refuse_unready_snapshot(signal)

    with transaction.atomic():
        run = _create_run(signal)
        signal.intake_state = IntakeState.DISPATCHED
        signal.save(update_fields=["intake_state"])
        enqueue_run(run.pk)
    return run


def rerun_signal(*, signal: Signal, enqueue_run: RunEnqueuer) -> Run:
    """Create and publish a fresh run for a dispatched signal."""
    if signal.intake_state != IntakeState.DISPATCHED:
        raise ValueError("only dispatched signals can be re-run")
    _refuse_stranded(signal)
    _refuse_unready_snapshot(signal)

    with transaction.atomic():
        if signal.runs.filter(
            state__in=[
                RunState.QUEUED,
                RunState.PROVISIONING,
                RunState.RUNNING,
                RunState.AWAITING_REVIEW,
            ]
        ).exists():
            raise ValueError("signal already has an active run")
        run = _create_run(signal)
        enqueue_run(run.pk)
    return run
