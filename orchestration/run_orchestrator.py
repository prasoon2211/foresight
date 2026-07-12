from enum import StrEnum

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core.harness import render_harness_prompt
from core.models import FailureReason, Org, ResultStatus, Run, RunState
from core.result_contract import RESULT_SCHEMA, ResultSource, resolve_result
from core.run_control import fail_run
from core.session_exports import store_run_artifact, store_session_export
from core.snapshots import sandbox_spec_for_repo
from executor import (
    AgentLaunch,
    AgentSession,
    DurableExecutor,
    SandboxDied,
    SandboxHandle,
    SetupFailed,
)
from surfaces.github import find_open_pull_request_for_run
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
        run_sandboxes = [
            sandbox for sandbox in executor.list_sandboxes() if sandbox.run_id == run.pk
        ]
        matching_sandboxes = [
            sandbox
            for sandbox in run_sandboxes
            if sandbox.labels.get("provisioning_complete") == "true"
        ]
        for incomplete in run_sandboxes:
            if incomplete.labels.get("provisioning_complete") != "true":
                executor.destroy(incomplete.handle)
        if matching_sandboxes:
            run.refresh_from_db(fields=["state"])
            if run.state == RunState.FAILED:
                retained = matching_sandboxes[0]
                executor.archive(retained.handle)
                run.sandbox_id = retained.handle.sandbox_id
                run.sandbox_archived_at = timezone.now()
                run.save(
                    update_fields=[
                        "sandbox_id",
                        "sandbox_archived_at",
                        "updated_at",
                    ]
                )
                for sandbox in matching_sandboxes[1:]:
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
                run.executor_type = executor.executor_type
                run.save(update_fields=["state", "executor_type", "updated_at"])
        if surface_adapter is not None:
            surface_adapter.notify_run_started(run)
        try:
            handle = executor.create_sandbox(
                sandbox_spec_for_repo(
                    run.signal.repo,
                    labels={
                        "run_id": str(run.pk),
                        "trigger": run.signal.source,
                    },
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
            executor.archive(handle)
            run.sandbox_id = handle.sandbox_id
            run.sandbox_archived_at = timezone.now()
            run.save(
                update_fields=[
                    "sandbox_id",
                    "sandbox_archived_at",
                    "updated_at",
                ]
            )
            if surface_adapter is not None:
                surface_adapter.notify_run_finished(run)
            return RunJobOutcome.FINISHED

    run.refresh_from_db()
    if run.state == RunState.FAILED:
        if surface_adapter is not None:
            surface_adapter.notify_run_finished(run)
        return RunJobOutcome.FINISHED
    handle = SandboxHandle(sandbox_id=run.sandbox_id)
    if not run.setup_log_path:
        run.setup_log_path = store_run_artifact(
            run_id=run.pk,
            name="setup.log",
            content=executor.read_file(handle, "/tmp/foresight/setup.log") or "",
        )
        run.save(update_fields=["setup_log_path", "updated_at"])
    if not run.agent_session_id:
        session = executor.launch_agent(
            handle,
            AgentLaunch(
                prompt=render_harness_prompt(run),
                model=settings.OPENCODE_MODEL,
                credentials=run.signal.org.agent_credentials(),
                server_password=run.server_password,
                output_schema=RESULT_SCHEMA,
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
        server_password=run.server_password,
    )
    session_messages = None
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

        resolved_messages = executor.get_session_messages(handle, session)
        session_messages = resolved_messages
        resolution = resolve_result(
            read_transcript=lambda: resolved_messages,
            read_result_file=lambda: executor.read_file(
                handle,
                "/tmp/foresight/result.json",
            ),
            find_open_pull_request=lambda: find_open_pull_request_for_run(run),
        )
        result = resolution.result

        run.result_status = result.status
        run.pr_url = result.pr_url or ""
        run.summary = result.summary
        run.confidence = result.confidence
        if resolution.source == ResultSource.SYNTHESIZED:
            run.failure_reason = FailureReason.NO_RESULT
        elif result.status == ResultStatus.FAILED:
            run.failure_reason = FailureReason.AGENT_REPORTED_FAILED
        elif result.status == ResultStatus.BLOCKED:
            run.failure_reason = FailureReason.AGENT_REPORTED_BLOCKED
        run.save(
            update_fields=[
                "result_status",
                "pr_url",
                "summary",
                "confidence",
                "failure_reason",
                "updated_at",
            ]
        )

    run.refresh_from_db()
    if not run.session_export_path:
        if session_messages is None:
            session_messages = executor.get_session_messages(handle, session)
        run.session_export_path = store_session_export(
            run_id=run.pk,
            messages=session_messages,
        )
        run.save(update_fields=["session_export_path", "updated_at"])
    if run.failure_reason == FailureReason.NO_RESULT:
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

    if not run.agent_log_path:
        run.agent_log_path = store_run_artifact(
            run_id=run.pk,
            name="agent.log",
            content=executor.read_file(handle, "/tmp/foresight/agent.log") or "",
        )
        run.save(update_fields=["agent_log_path", "updated_at"])
    if run.sandbox_archived_at is None:
        executor.archive(handle)
        run.sandbox_archived_at = timezone.now()
        run.save(update_fields=["sandbox_archived_at", "updated_at"])

    with transaction.atomic():
        current_run = Run.objects.select_for_update().get(pk=run.pk)
        if current_run.state != RunState.RUNNING:
            return RunJobOutcome.FINISHED
        current_run.state = RunState.AWAITING_REVIEW
        current_run.save(update_fields=["state", "updated_at"])
    if surface_adapter is not None:
        surface_adapter.notify_run_finished(current_run)
    return RunJobOutcome.FINISHED
