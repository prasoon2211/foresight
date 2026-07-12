from collections.abc import Iterable
from dataclasses import dataclass

from core.models import ConnectionStatus, IntakeState, RunState


@dataclass(frozen=True)
class RunOutcome:
    state: RunState | str
    pr_merged: bool = False


def derive_stranded(repo_connection_status: ConnectionStatus | str) -> bool:
    return repo_connection_status == ConnectionStatus.DISCONNECTED


def derive_outcome_status(
    intake_state: IntakeState | str,
    runs: Iterable[RunOutcome],
) -> str:
    """Derive a signal's user-facing status from its durable state."""
    if intake_state != IntakeState.DISPATCHED:
        return intake_state

    outcomes = list(runs)
    if any(outcome.pr_merged for outcome in outcomes):
        return RunState.DONE
    if outcomes:
        return outcomes[-1].state
    return IntakeState.DISPATCHED
