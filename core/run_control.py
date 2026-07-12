from django.db import transaction
from django.utils import timezone

from core.models import FailureReason, Run, RunState
from core.session_exports import store_run_artifact, store_session_export
from executor import AgentSession, DurableExecutor, SandboxHandle


def fail_run(
    *,
    run: Run,
    executor: DurableExecutor,
    reason: FailureReason,
    detail: str = "",
    allowed_states: set[str] | None = None,
) -> Run:
    """Persist a failed Run, harvest its session, and retain its sandbox."""
    with transaction.atomic():
        run = Run.objects.select_for_update().get(pk=run.pk)
        if allowed_states is not None and run.state not in allowed_states:
            raise ValueError("only queued, provisioning, or running runs can be stopped")
        if run.state != RunState.FAILED:
            run.state = RunState.FAILED
            run.failure_reason = reason
            run.failure_detail = detail
            run.save(update_fields=["state", "failure_reason", "failure_detail", "updated_at"])

    if not run.sandbox_id:
        return run
    handle = SandboxHandle(sandbox_id=run.sandbox_id)
    if reason != FailureReason.SANDBOX_DIED and not run.setup_log_path:
        run.setup_log_path = store_run_artifact(
            run_id=run.pk,
            name="setup.log",
            content=executor.read_file(handle, "/tmp/foresight/setup.log") or "",
        )
        run.save(update_fields=["setup_log_path", "updated_at"])
    if reason != FailureReason.SANDBOX_DIED and run.agent_session_id and not run.agent_log_path:
        run.agent_log_path = store_run_artifact(
            run_id=run.pk,
            name="agent.log",
            content=executor.read_file(handle, "/tmp/foresight/agent.log") or "",
        )
        run.save(update_fields=["agent_log_path", "updated_at"])
    if (
        reason != FailureReason.SANDBOX_DIED
        and run.agent_session_id
        and not run.session_export_path
    ):
        session = AgentSession(
            session_id=run.agent_session_id,
            base_url=run.agent_base_url,
            server_password=run.server_password,
        )
        try:
            messages = executor.get_session_messages(handle, session)
        except Exception as error:
            messages = []
            unavailable = f"Session transcript unavailable: {type(error).__name__}"
            run.failure_detail = "\n".join(
                part for part in [run.failure_detail, unavailable] if part
            )
        run.session_export_path = store_session_export(
            run_id=run.pk,
            messages=messages,
        )
        run.save(
            update_fields=[
                "session_export_path",
                "failure_detail",
                "updated_at",
            ]
        )
    if reason == FailureReason.SANDBOX_DIED:
        executor.destroy(handle)
    elif run.sandbox_archived_at is None:
        executor.archive(handle)
        run.sandbox_archived_at = timezone.now()
        run.save(update_fields=["sandbox_archived_at", "updated_at"])
    return run


def stop_run(*, run: Run, executor: DurableExecutor) -> Run:
    """Cancel an executing run and retain its sandbox."""
    return fail_run(
        run=run,
        executor=executor,
        reason=FailureReason.CANCELED,
        allowed_states={
            RunState.QUEUED,
            RunState.PROVISIONING,
            RunState.RUNNING,
        },
    )
