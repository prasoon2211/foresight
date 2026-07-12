from core.models import IntakeState, RunState
from core.outcome import RunOutcome, derive_outcome_status


def test_outcome_status_mirrors_intake_before_dispatch() -> None:
    assert derive_outcome_status(IntakeState.RECEIVED, []) == IntakeState.RECEIVED


def test_outcome_status_reflects_latest_run_after_dispatch() -> None:
    assert (
        derive_outcome_status(
            IntakeState.DISPATCHED,
            [RunOutcome(RunState.FAILED), RunOutcome(RunState.QUEUED)],
        )
        == RunState.QUEUED
    )


def test_outcome_status_is_done_when_any_run_has_a_merged_pr() -> None:
    assert (
        derive_outcome_status(
            IntakeState.DISPATCHED,
            [
                RunOutcome(RunState.AWAITING_REVIEW, pr_merged=True),
                RunOutcome(RunState.FAILED),
            ],
        )
        == RunState.DONE
    )


def test_dispatched_signal_without_runs_remains_dispatched() -> None:
    assert derive_outcome_status(IntakeState.DISPATCHED, []) == IntakeState.DISPATCHED
