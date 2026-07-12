from enum import StrEnum

from django.db import transaction

from core.models import FailureReason, Org, ResultStatus, Run, RunState
from core.run_control import fail_run
from executor import (
    AgentLaunch,
    AgentSession,
    DurableExecutor,
    SandboxDied,
    SandboxHandle,
    SandboxSpec,
    SetupFailed,
)


class RunJobOutcome(StrEnum):
    FINISHED = "finished"
    POSTPONED = "postponed"


def orchestrate_run(run_id: int, executor: DurableExecutor) -> RunJobOutcome:
    """Advance one run, checkpointing each learned fact before continuing."""
    run = Run.objects.select_related("signal__repo", "signal__org").get(pk=run_id)
    if run.state in {RunState.AWAITING_REVIEW, RunState.DONE, RunState.FAILED}:
        return RunJobOutcome.FINISHED

    if not run.sandbox_id and run.state == RunState.PROVISIONING:
        matching_sandboxes = [
            sandbox for sandbox in executor.list_sandboxes() if sandbox.run_id == run.pk
        ]
        if matching_sandboxes:
            run.refresh_from_db(fields=["state"])
            if run.state == RunState.FAILED:
                for sandbox in matching_sandboxes:
                    executor.destroy(sandbox.handle)
                return RunJobOutcome.FINISHED
            run.sandbox_id = matching_sandboxes[0].handle.sandbox_id
            run.save(update_fields=["sandbox_id", "updated_at"])
            for duplicate in matching_sandboxes[1:]:
                executor.destroy(duplicate.handle)

    if not run.sandbox_id:
        if run.state == RunState.QUEUED:
            with transaction.atomic():
                run = (
                    Run.objects.select_for_update()
                    .select_related("signal__repo", "signal__org")
                    .get(pk=run_id)
                )
                if run.state != RunState.QUEUED:
                    return RunJobOutcome.FINISHED
                org = Org.objects.select_for_update().get(pk=run.signal.org_id)
                occupied_slots = Run.objects.filter(
                    signal__org_id=org.pk,
                    state__in=[RunState.PROVISIONING, RunState.RUNNING],
                ).exclude(pk=run.pk)
                if occupied_slots.count() >= org.concurrency_cap:
                    return RunJobOutcome.POSTPONED
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
            fail_run(
                run=run,
                executor=executor,
                reason=FailureReason.SETUP_FAILED,
                detail=error.detail,
            )
            return RunJobOutcome.FINISHED
        with transaction.atomic():
            run = (
                Run.objects.select_for_update()
                .select_related("signal__repo", "signal__org")
                .get(pk=run.pk)
            )
            canceled = run.state == RunState.FAILED
            if not canceled:
                run.sandbox_id = handle.sandbox_id
                run.save(update_fields=["sandbox_id", "updated_at"])
        if canceled:
            executor.destroy(handle)
            return RunJobOutcome.FINISHED

    run.refresh_from_db()
    if run.state == RunState.FAILED:
        return RunJobOutcome.FINISHED
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
        with transaction.atomic():
            run = Run.objects.select_for_update().get(pk=run.pk)
            canceled = run.state == RunState.FAILED
            if not canceled:
                run.agent_session_id = session.session_id
                run.agent_base_url = session.base_url
                run.state = RunState.RUNNING
                run.save(
                    update_fields=[
                        "agent_session_id",
                        "agent_base_url",
                        "state",
                        "updated_at",
                    ]
                )
        if canceled:
            return RunJobOutcome.FINISHED

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
                    return RunJobOutcome.FINISHED
                if event.session_id != session.session_id:
                    continue
                if event.kind == "session.error":
                    fail_run(
                        run=run,
                        executor=executor,
                        reason=FailureReason.AGENT_ERROR,
                    )
                    return RunJobOutcome.FINISHED
                if event.kind == "session.idle":
                    result = event.result
                    break
        except SandboxDied:
            fail_run(
                run=run,
                executor=executor,
                reason=FailureReason.SANDBOX_DIED,
            )
            return RunJobOutcome.FINISHED
        if result is None:
            fail_run(run=run, executor=executor, reason=FailureReason.NO_RESULT)
            return RunJobOutcome.FINISHED
        if result.status not in ResultStatus.values or (
            result.status == ResultStatus.PR_OPENED and not result.pr_url
        ):
            fail_run(run=run, executor=executor, reason=FailureReason.NO_RESULT)
            return RunJobOutcome.FINISHED

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

    run.refresh_from_db()
    if run.result_status == ResultStatus.FAILED:
        fail_run(
            run=run,
            executor=executor,
            reason=FailureReason.AGENT_REPORTED_FAILED,
        )
        return RunJobOutcome.FINISHED
    if run.result_status == ResultStatus.BLOCKED:
        fail_run(
            run=run,
            executor=executor,
            reason=FailureReason.AGENT_REPORTED_BLOCKED,
        )
        return RunJobOutcome.FINISHED

    with transaction.atomic():
        current_run = Run.objects.select_for_update().get(pk=run.pk)
        if current_run.state == RunState.FAILED:
            return RunJobOutcome.FINISHED
        current_run.state = RunState.AWAITING_REVIEW
        current_run.save(update_fields=["state", "updated_at"])
    return RunJobOutcome.FINISHED
