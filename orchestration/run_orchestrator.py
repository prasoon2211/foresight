from enum import StrEnum

from django.db import transaction

from core.models import FailureReason, Org, ResultStatus, Run, RunState
from executor import (
    AgentLaunch,
    AgentResult,
    AgentSession,
    Executor,
    SandboxDied,
    SandboxHandle,
    SandboxSpec,
    SetupFailed,
)


class OrchestrationOutcome(StrEnum):
    COMPLETED = "completed"
    POSTPONED = "postponed"


def _fail_run(
    run: Run,
    executor: Executor,
    reason: FailureReason,
    *,
    detail: str = "",
) -> None:
    run.state = RunState.FAILED
    run.failure_reason = reason
    run.failure_detail = detail
    run.save(update_fields=["state", "failure_reason", "failure_detail", "updated_at"])
    if run.sandbox_id:
        executor.destroy(SandboxHandle(sandbox_id=run.sandbox_id))


def _record_result(run: Run, result: AgentResult) -> None:
    run.result_status = result.status
    run.pr_url = result.pr_url
    run.summary = result.summary
    run.confidence = result.confidence
    run.save(
        update_fields=[
            "result_status",
            "pr_url",
            "summary",
            "confidence",
            "updated_at",
        ]
    )


def orchestrate_run(run_id: int, executor: Executor) -> OrchestrationOutcome:
    """Advance one run, checkpointing each learned fact before continuing."""
    run = Run.objects.select_related("signal__repo", "signal__org").get(pk=run_id)
    if run.state in {RunState.AWAITING_REVIEW, RunState.DONE, RunState.FAILED}:
        return OrchestrationOutcome.COMPLETED

    if not run.sandbox_id:
        if run.state == RunState.QUEUED:
            with transaction.atomic():
                run = (
                    Run.objects.select_for_update()
                    .select_related("signal__repo", "signal__org")
                    .get(pk=run_id)
                )
                org = Org.objects.select_for_update().get(pk=run.signal.org_id)
                occupied_slots = Run.objects.filter(
                    signal__org_id=org.pk,
                    state__in=[RunState.PROVISIONING, RunState.RUNNING],
                ).exclude(pk=run.pk)
                if occupied_slots.count() >= org.concurrency_cap:
                    return OrchestrationOutcome.POSTPONED
                run.state = RunState.PROVISIONING
                run.save(update_fields=["state", "updated_at"])
        try:
            handle = executor.create_sandbox(
                SandboxSpec(
                    snapshot=f"repo:{run.signal.repo.full_name}",
                    env_files=[],
                    setup_script=None,
                    labels={
                        "run_id": str(run.pk),
                        "repo": run.signal.repo.full_name,
                        "trigger": run.signal.source,
                    },
                    resources=None,
                )
            )
        except SetupFailed as error:
            _fail_run(
                run,
                executor,
                FailureReason.SETUP_FAILED,
                detail=error.detail,
            )
            return OrchestrationOutcome.COMPLETED
        run.sandbox_id = handle.sandbox_id
        run.save(update_fields=["sandbox_id", "updated_at"])

    run.refresh_from_db()
    handle = SandboxHandle(sandbox_id=run.sandbox_id)
    if not run.agent_session_id:
        session = executor.launch_agent(
            handle,
            AgentLaunch(
                prompt=f"{run.signal.title}\n\n{run.signal.body}",
                model="fake/model",
                credentials={},
                server_password=run.server_password,
                output_schema={
                    "type": "object",
                    "required": ["status", "pr_url", "summary", "confidence"],
                },
            ),
        )
        run.agent_session_id = session.session_id
        run.agent_base_url = session.base_url
        run.state = RunState.RUNNING
        run.save(update_fields=["agent_session_id", "agent_base_url", "state", "updated_at"])

    run.refresh_from_db()
    session = AgentSession(
        session_id=run.agent_session_id,
        base_url=run.agent_base_url,
    )
    if not run.result_status:
        result = None
        try:
            for event in executor.stream_events(handle, session):
                run.refresh_from_db(fields=["state"])
                if run.state == RunState.FAILED:
                    return OrchestrationOutcome.COMPLETED
                if event.session_id != session.session_id:
                    continue
                if event.kind == "session.error":
                    _fail_run(run, executor, FailureReason.AGENT_ERROR)
                    return OrchestrationOutcome.COMPLETED
                if event.kind == "session.idle":
                    result = event.result
                    break
        except SandboxDied:
            _fail_run(run, executor, FailureReason.SANDBOX_DIED)
            return OrchestrationOutcome.COMPLETED
        if result is None:
            _fail_run(run, executor, FailureReason.NO_RESULT)
            return OrchestrationOutcome.COMPLETED
        _record_result(run, result)
        if result.status == ResultStatus.FAILED:
            _fail_run(run, executor, FailureReason.AGENT_REPORTED_FAILED)
            return OrchestrationOutcome.COMPLETED
        if result.status == ResultStatus.BLOCKED:
            _fail_run(run, executor, FailureReason.AGENT_REPORTED_BLOCKED)
            return OrchestrationOutcome.COMPLETED
        if result.status != ResultStatus.PR_OPENED:
            raise RuntimeError(f"orchestrator cannot handle result {result.status!r}")

        run.state = RunState.AWAITING_REVIEW
        run.save(
            update_fields=[
                "state",
                "updated_at",
            ]
        )
    return OrchestrationOutcome.COMPLETED
