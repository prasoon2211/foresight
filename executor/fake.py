from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, replace

from executor.protocol import (
    AgentEvent,
    AgentLaunch,
    AgentResult,
    AgentSession,
    AttachEndpoints,
    SandboxDied,
    SandboxHandle,
    SandboxRecord,
    SandboxSpec,
    SetupFailed,
)

DEFAULT_RESULT = AgentResult(
    status="pr_opened",
    pr_url="https://example.test/foresight/pull/1",
    summary="Fake executor completed the signal.",
    confidence=1.0,
)


@dataclass(frozen=True)
class FakeExecutorScript:
    event_batches: Iterable[Iterable[AgentEvent]] | None = None
    setup_failure: str | None = None
    sandbox_dies: bool = False
    interrupt_before_launch_once: bool = False
    interrupt_before_stream_once: bool = False
    interrupt_after_create_once: bool = False
    interrupt_after_launch_once: bool = False
    before_stream: Callable[[], None] | None = None
    after_create: Callable[[], None] | None = None
    after_launch: Callable[[], None] | None = None
    after_list_once: Callable[[], None] | None = None


class FakeExecutor:
    """Scriptable, in-memory implementation of the executor boundary."""

    def __init__(
        self,
        script: FakeExecutorScript | None = None,
        *,
        inventory: Iterable[SandboxRecord] = (),
    ) -> None:
        script = script or FakeExecutorScript()
        event_batches = script.event_batches
        self._scripts = deque([list(events) for events in event_batches] if event_batches else [])
        self._use_default_script = event_batches is None
        self._setup_failure = script.setup_failure
        self._sandbox_dies = script.sandbox_dies
        self._interrupt_before_launch_once = script.interrupt_before_launch_once
        self._interrupt_before_stream_once = script.interrupt_before_stream_once
        self._interrupt_after_create_once = script.interrupt_after_create_once
        self._interrupt_after_launch_once = script.interrupt_after_launch_once
        self._before_stream = script.before_stream
        self._after_create = script.after_create
        self._after_launch = script.after_launch
        self._after_list_once = script.after_list_once
        self._next_sandbox = 1
        self._next_session = 1
        self._destroyed: set[str] = set()
        self._inventory = {item.handle.sandbox_id: item for item in inventory}
        self._sessions: dict[str, AgentSession] = {}
        self.calls: list[str] = []
        self.sandbox_specs: list[SandboxSpec] = []
        self.agent_launches: list[AgentLaunch] = []
        self.streamed_sessions: list[AgentSession] = []

    @classmethod
    def succeeding(cls, result: AgentResult) -> "FakeExecutor":
        return cls(
            FakeExecutorScript(event_batches=[[AgentEvent(kind="session.idle", result=result)]])
        )

    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle:
        self.calls.append("create_sandbox")
        self.sandbox_specs.append(spec)
        if self._setup_failure is not None:
            raise SetupFailed(self._setup_failure)
        handle = SandboxHandle(sandbox_id=f"fake-sandbox-{self._next_sandbox}")
        self._next_sandbox += 1
        self._inventory[handle.sandbox_id] = SandboxRecord(
            handle=handle,
            labels=dict(spec.labels),
        )
        if self._after_create is not None:
            self._after_create()
        if self._interrupt_after_create_once:
            self._interrupt_after_create_once = False
            raise RuntimeError("worker interrupted")
        return handle

    def launch_agent(
        self,
        handle: SandboxHandle,
        launch: AgentLaunch,
    ) -> AgentSession:
        if self._interrupt_before_launch_once:
            self._interrupt_before_launch_once = False
            raise RuntimeError("worker interrupted")
        self.calls.append("launch_agent")
        if handle.sandbox_id in self._sessions:
            return self._sessions[handle.sandbox_id]
        self.agent_launches.append(launch)
        session = AgentSession(
            session_id=f"fake-session-{self._next_session}",
            base_url=f"fake://{handle.sandbox_id}",
        )
        self._sessions[handle.sandbox_id] = session
        self._next_session += 1
        if self._after_launch is not None:
            self._after_launch()
        if self._interrupt_after_launch_once:
            self._interrupt_after_launch_once = False
            raise RuntimeError("worker interrupted")
        return session

    def get_attach_endpoints(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> AttachEndpoints:
        self.calls.append("get_attach_endpoints")
        return AttachEndpoints(
            web_url=f"https://fake.test/{handle.sandbox_id}/web",
            api_url=f"https://fake.test/{handle.sandbox_id}/api",
            terminal_ws=f"wss://fake.test/{handle.sandbox_id}/terminal",
            tui_command=(
                f"opencode attach fake://{handle.sandbox_id} --session {session.session_id}"
            ),
        )

    def stream_events(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> Iterator[AgentEvent]:
        if self._interrupt_before_stream_once:
            self._interrupt_before_stream_once = False
            raise RuntimeError("worker interrupted")
        self.calls.append("stream_events")
        self.streamed_sessions.append(session)
        if self._before_stream is not None:
            self._before_stream()
        if self._sandbox_dies:
            raise SandboxDied
        if self._scripts:
            events = self._scripts.popleft()
        elif self._use_default_script:
            events = [AgentEvent(kind="session.idle", result=DEFAULT_RESULT)]
        else:
            raise RuntimeError("FakeExecutor has no script for this run")

        return iter(
            replace(event, session_id=session.session_id) if event.session_id is None else event
            for event in events
        )

    def destroy(self, handle: SandboxHandle) -> None:
        self.calls.append("destroy")
        self._destroyed.add(handle.sandbox_id)
        self._inventory.pop(handle.sandbox_id, None)

    def list_sandboxes(self) -> list[SandboxRecord]:
        self.calls.append("list_sandboxes")
        inventory = list(self._inventory.values())
        if self._after_list_once is not None:
            callback = self._after_list_once
            self._after_list_once = None
            callback()
        return inventory
