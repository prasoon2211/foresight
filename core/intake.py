import secrets
from collections.abc import Callable

from django.db import transaction

from core.models import IntakeState, Repo, Run, Signal, SignalSource

RunEnqueuer = Callable[[int], object]


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

    with transaction.atomic():
        run = Run.objects.create(
            signal=signal,
            server_password=secrets.token_urlsafe(32),
            branch_name=f"foresight/signal-{signal.pk}",
        )
        signal.intake_state = IntakeState.DISPATCHED
        signal.save(update_fields=["intake_state"])
        enqueue_run(run.pk)
    return run
