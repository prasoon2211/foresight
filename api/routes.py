from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.responses import Status

from api.schemas import (
    CreatedSignalOut,
    ManualSignalIn,
    RunOut,
    RunResultOut,
    SignalOut,
)
from core.intake import create_manual_signal, rerun_signal
from core.models import Repo, Run, Signal
from core.outcome import RunOutcome, derive_outcome_status
from core.run_control import stop_run
from orchestration.executor_backend import get_executor
from orchestration.tasks import enqueue_run_orchestrator

router = Router(tags=["signals", "runs"])


def _run_out(run: Run) -> RunOut:
    result = None
    if run.result_status:
        if run.confidence is None:
            raise RuntimeError("completed run result is missing confidence")
        result = RunResultOut(
            status=run.result_status,
            pr_url=run.pr_url,
            summary=run.summary,
            confidence=run.confidence,
        )
    return RunOut(
        id=run.pk,
        signal_id=run.signal_id,
        state=run.state,
        failure_reason=run.failure_reason,
        failure_detail=run.failure_detail,
        result=result,
    )


@router.post("/signals", response={201: CreatedSignalOut})
def create_signal(request: HttpRequest, payload: ManualSignalIn) -> Status[CreatedSignalOut]:
    repo = get_object_or_404(Repo, pk=payload.repo_id)
    signal, run = create_manual_signal(
        repo=repo,
        title=payload.title,
        body=payload.body,
        enqueue_run=enqueue_run_orchestrator,
    )
    return Status(
        201,
        CreatedSignalOut(
            id=signal.pk,
            run_id=run.pk,
            intake_state=signal.intake_state,
        ),
    )


@router.get("/signals", response=list[SignalOut])
def list_signals(request: HttpRequest) -> list[SignalOut]:
    return [
        SignalOut(
            id=signal.pk,
            repo_id=signal.repo_id,
            source=signal.source,
            title=signal.title,
            body=signal.body,
            intake_state=signal.intake_state,
            outcome_status=derive_outcome_status(
                signal.intake_state,
                (
                    RunOutcome(state=state, pr_merged=pr_merged_at is not None)
                    for state, pr_merged_at in signal.runs.order_by("created_at", "pk").values_list(
                        "state", "pr_merged_at"
                    )
                ),
            ),
        )
        for signal in Signal.objects.order_by("created_at", "pk")
    ]


@router.get("/runs/{run_id}", response=RunOut)
def get_run(request: HttpRequest, run_id: int) -> RunOut:
    run = get_object_or_404(Run, pk=run_id)
    return _run_out(run)


@router.post("/runs/{run_id}/stop", response=RunOut)
def stop_running_run(request: HttpRequest, run_id: int) -> RunOut:
    run = get_object_or_404(Run, pk=run_id)
    return _run_out(stop_run(run=run, executor=get_executor()))


@router.post("/signals/{signal_id}/rerun", response={201: RunOut})
def rerun(request: HttpRequest, signal_id: int) -> Status[RunOut]:
    signal = get_object_or_404(Signal, pk=signal_id)
    run = rerun_signal(signal=signal, enqueue_run=enqueue_run_orchestrator)
    return Status(201, _run_out(run))
