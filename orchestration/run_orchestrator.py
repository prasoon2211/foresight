from enum import StrEnum

from django.db import transaction

from core.harness import render_harness_prompt
from core.models import FailureReason, Org, ResultStatus, Run, RunState
from core.result_contract import ResultSource, resolve_result
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
from surfaces.github_client import get_github_client
from surfaces.protocol import SurfaceAdapter
from surfaces.registry import surface_adapter_for


class RunJobOutcome(StrEnum):
    FINISHED = "finished"
    POSTPONED = "postponed"


def _fail_and_notify(
    *,
    run: Run,
    executor: DurableExecutor,
    surface_adapter: SurfaceAdapter | None,
    reason: FailureReason,
    detail: str = "",
) -> None:
    failed_run = fail_run(
        run=run,
        executor=executor,
        reason=reason,
        detail=detail,
    )
    if surface_adapter is not None:
        surface_adapter.notify_run_finished(failed_run)


def orchestrate_run(run_id: int, executor: DurableExecutor) -> RunJobOutcome:
    """Advance one run, checkpointing each learned fact before continuing."""
    run = Run.objects.select_related(
        "signal__repo",
        "signal__org",
        "signal__origin_connection",
    ).get(pk=run_id)
    surface_adapter = surface_adapter_for(run.signal)
    if run.state in {RunState.AWAITING_REVIEW, RunState.DONE, RunState.FAILED}:
        if surface_adapter is not None and run.state != RunState.DONE:
            surface_adapter.notify_run_finished(run)
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
                if surface_adapter is not None:
                    surface_adapter.notify_run_finished(run)
                return RunJobOutcome.FINISHED
            run.sandbox_id = matching_sandboxes[0].handle.sandbox_id
            run.save(update_fields=["sandbox_id", "updated_at"])
            for duplicate in matching_sandboxes[1:]:
                executor.destroy(duplicate.handle)

    if run.sandbox_id and surface_adapter is not None:
        surface_adapter.notify_run_started(run)

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
        if surface_adapter is not None:
            surface_adapter.notify_run_started(run)
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
            _fail_and_notify(
                run=run,
                executor=executor,
                surface_adapter=surface_adapter,
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
            if surface_adapter is not None:
                surface_adapter.notify_run_finished(run)
            return RunJobOutcome.FINISHED

    run.refresh_from_db()
    if run.state == RunState.FAILED:
        if surface_adapter is not None:
            surface_adapter.notify_run_finished(run)
        return RunJobOutcome.FINISHED
    handle = SandboxHandle(sandbox_id=run.sandbox_id)
    if not run.agent_session_id:
        session = executor.launch_agent(
            handle,
            AgentLaunch(
                prompt=render_harness_prompt(run),
                model="fake/model",
                credentials=run.signal.org.agent_credentials(),
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
            if surface_adapter is not None:
                surface_adapter.notify_run_finished(run)
            return RunJobOutcome.FINISHED

    run.refresh_from_db()
    session = AgentSession(
        session_id=run.agent_session_id,
        base_url=run.agent_base_url,
    )
    synthesized_result = False
    if not run.result_status:
        session_completed = False
        try:
            for event in executor.stream_events(handle, session):
                run.refresh_from_db(fields=["state"])
                if run.state == RunState.FAILED:
                    if surface_adapter is not None:
                        surface_adapter.notify_run_finished(run)
                    return RunJobOutcome.FINISHED
                if event.session_id != session.session_id:
                    continue
                if event.kind == "session.error":
                    _fail_and_notify(
                        run=run,
                        executor=executor,
                        surface_adapter=surface_adapter,
                        reason=FailureReason.AGENT_ERROR,
                    )
                    return RunJobOutcome.FINISHED
                if event.kind == "session.idle":
                    session_completed = True
                    break
        except SandboxDied:
            _fail_and_notify(
                run=run,
                executor=executor,
                surface_adapter=surface_adapter,
                reason=FailureReason.SANDBOX_DIED,
            )
            return RunJobOutcome.FINISHED
        if not session_completed:
            _fail_and_notify(
                run=run,
                executor=executor,
                surface_adapter=surface_adapter,
                reason=FailureReason.NO_RESULT,
            )
            return RunJobOutcome.FINISHED

        repo_connection = run.signal.repo.surface_connection
        resolution = resolve_result(
            transcript=executor.get_session_messages(handle, session),
            result_file=executor.read_file(handle, "/tmp/foresight/result.json"),
            github_client=get_github_client() if repo_connection is not None else None,
            installation_id=(
                int(repo_connection.identity["installation_id"])
                if repo_connection is not None
                else None
            ),
            repo_full_name=run.signal.repo.full_name,
            branch_name=run.branch_name,
        )
        result = resolution.result

        run.result_status = result.status
        run.pr_url = result.pr_url or ""
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
        synthesized_result = resolution.source == ResultSource.SYNTHESIZED

    run.refresh_from_db()
    if synthesized_result:
        _fail_and_notify(
            run=run,
            executor=executor,
            surface_adapter=surface_adapter,
            reason=FailureReason.NO_RESULT,
        )
        return RunJobOutcome.FINISHED
    if run.result_status == ResultStatus.FAILED:
        _fail_and_notify(
            run=run,
            executor=executor,
            surface_adapter=surface_adapter,
            reason=FailureReason.AGENT_REPORTED_FAILED,
        )
        return RunJobOutcome.FINISHED
    if run.result_status == ResultStatus.BLOCKED:
        _fail_and_notify(
            run=run,
            executor=executor,
            surface_adapter=surface_adapter,
            reason=FailureReason.AGENT_REPORTED_BLOCKED,
        )
        return RunJobOutcome.FINISHED

    with transaction.atomic():
        current_run = Run.objects.select_for_update().get(pk=run.pk)
        if current_run.state != RunState.RUNNING:
            return RunJobOutcome.FINISHED
        current_run.state = RunState.AWAITING_REVIEW
        current_run.save(update_fields=["state", "updated_at"])
    if surface_adapter is not None:
        surface_adapter.notify_run_finished(current_run)
    return RunJobOutcome.FINISHED
