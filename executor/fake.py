from collections import deque
from collections.abc import Iterable, Iterator
from dataclasses import replace

from executor.protocol import (
    AgentEvent,
    AgentLaunch,
    AgentResult,
    AgentSession,
    AttachEndpoints,
    SandboxHandle,
    SandboxSpec,
)

DEFAULT_RESULT = AgentResult(
    status="pr_opened",
    pr_url="https://example.test/foresight/pull/1",
    summary="Fake executor completed the signal.",
    confidence=1.0,
)


class FakeExecutor:
    """Scriptable, in-memory implementation of the executor boundary."""

    def __init__(self, scripts: Iterable[Iterable[AgentEvent]] | None = None) -> None:
        self._scripts = deque([list(script) for script in scripts] if scripts else [])
        self._use_default_script = scripts is None
        self._next_sandbox = 1
        self._next_session = 1
        self._destroyed: set[str] = set()
        self.calls: list[str] = []
        self.sandbox_specs: list[SandboxSpec] = []
        self.agent_launches: list[AgentLaunch] = []
        self.streamed_sessions: list[AgentSession] = []

    @classmethod
    def succeeding(cls, result: AgentResult) -> "FakeExecutor":
        return cls([[AgentEvent(kind="session.idle", result=result)]])

    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle:
        self.calls.append("create_sandbox")
        self.sandbox_specs.append(spec)
        handle = SandboxHandle(sandbox_id=f"fake-sandbox-{self._next_sandbox}")
        self._next_sandbox += 1
        return handle

    def launch_agent(
        self,
        handle: SandboxHandle,
        launch: AgentLaunch,
    ) -> AgentSession:
        self.calls.append("launch_agent")
        self.agent_launches.append(launch)
        session = AgentSession(
            session_id=f"fake-session-{self._next_session}",
            base_url=f"fake://{handle.sandbox_id}",
        )
        self._next_session += 1
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
        self.calls.append("stream_events")
        self.streamed_sessions.append(session)
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
