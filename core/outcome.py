from collections.abc import Iterable

from core.models import IntakeState, RunState


def derive_outcome_status(
    intake_state: IntakeState | str,
    run_states: Iterable[RunState | str],
) -> str:
    """Derive a signal's user-facing status from its durable state."""
    if intake_state != IntakeState.DISPATCHED:
        return intake_state

    states = list(run_states)
    if RunState.DONE in states:
        return RunState.DONE
    if states:
        return states[-1]
    return IntakeState.DISPATCHED
