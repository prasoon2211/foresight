from core.models import FailureReason, ResultStatus, Run, RunState
from executor import (
    AgentLaunch,
    AgentSession,
    Executor,
    SandboxHandle,
    SandboxSpec,
)
from surfaces.registry import surface_adapter_for


def orchestrate_run(run_id: int, executor: Executor) -> None:
    """Advance one run, checkpointing each learned fact before continuing."""
    run = Run.objects.select_related(
        "signal__repo",
        "signal__org",
        "signal__origin_connection",
    ).get(pk=run_id)
    if run.state in {RunState.AWAITING_REVIEW, RunState.DONE, RunState.FAILED}:
        return

    surface_adapter = surface_adapter_for(run.signal)
    if surface_adapter is not None:
        surface_adapter.notify_run_started(run)

    if not run.sandbox_id:
        if run.state == RunState.QUEUED:
            run.state = RunState.PROVISIONING
            run.save(update_fields=["state", "updated_at"])
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
                credentials=run.signal.org.agent_credentials(),
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
        result = next(
            (
                event.result
                for event in executor.stream_events(handle, session)
                if event.kind == "session.idle"
                and event.session_id == session.session_id
                and event.result is not None
            ),
            None,
        )
        if result is None:
            run.state = RunState.FAILED
            run.failure_reason = FailureReason.NO_RESULT
            run.summary = "Run produced no structured result."
        else:
            run.result_status = result.status
            run.pr_url = result.pr_url
            run.summary = result.summary
            run.confidence = result.confidence
            if result.status == ResultStatus.PR_OPENED:
                run.state = RunState.AWAITING_REVIEW
            else:
                run.state = RunState.FAILED
                if result.status == ResultStatus.FAILED:
                    run.failure_reason = FailureReason.AGENT_REPORTED_FAILED
                elif result.status == ResultStatus.BLOCKED:
                    run.failure_reason = FailureReason.AGENT_REPORTED_BLOCKED
                else:
                    raise ValueError(f"unsupported result status: {result.status}")
        run.save(
            update_fields=[
                "result_status",
                "pr_url",
                "summary",
                "confidence",
                "state",
                "failure_reason",
                "updated_at",
            ]
        )
        if surface_adapter is not None:
            surface_adapter.notify_run_finished(run)
