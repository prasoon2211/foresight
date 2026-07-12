from core.models import IntakeState, RunState
from core.outcome import derive_outcome_status


def test_outcome_status_mirrors_intake_before_dispatch() -> None:
    assert derive_outcome_status(IntakeState.RECEIVED, []) == IntakeState.RECEIVED


def test_outcome_status_reflects_latest_run_after_dispatch() -> None:
    assert (
        derive_outcome_status(
            IntakeState.DISPATCHED,
            [RunState.FAILED, RunState.QUEUED],
        )
        == RunState.QUEUED
    )


def test_outcome_status_is_done_when_any_run_is_done() -> None:
    assert (
        derive_outcome_status(
            IntakeState.DISPATCHED,
            [RunState.DONE, RunState.FAILED],
        )
        == RunState.DONE
    )


def test_dispatched_signal_without_runs_remains_dispatched() -> None:
    assert derive_outcome_status(IntakeState.DISPATCHED, []) == IntakeState.DISPATCHED
