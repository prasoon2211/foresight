from core.models import ResultStatus, Run, RunState
from executor import (
    AgentLaunch,
    AgentSession,
    Executor,
    SandboxHandle,
    SandboxSpec,
)


def orchestrate_run(run_id: int, executor: Executor) -> None:
    """Advance one run, checkpointing each learned fact before continuing."""
    run = Run.objects.select_related("signal__repo").get(pk=run_id)
    if run.state in {RunState.AWAITING_REVIEW, RunState.DONE, RunState.FAILED}:
        return

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
            raise RuntimeError("agent session became idle without a structured result")
        if result.status != ResultStatus.PR_OPENED:
            raise RuntimeError(f"happy-path orchestrator cannot handle result {result.status!r}")

        run.result_status = result.status
        run.pr_url = result.pr_url
        run.summary = result.summary
        run.confidence = result.confidence
        run.state = RunState.AWAITING_REVIEW
        run.save(
            update_fields=[
                "result_status",
                "pr_url",
                "summary",
                "confidence",
                "state",
                "updated_at",
            ]
        )
