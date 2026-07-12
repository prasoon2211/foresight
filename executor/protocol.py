from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


class SetupFailed(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SandboxDied(Exception):
    pass


@dataclass(frozen=True)
class EnvFile:
    target_path: str
    content: str


@dataclass(frozen=True)
class Resources:
    cpu: int
    memory_gib: int
    disk_gib: int


@dataclass(frozen=True)
class SandboxSpec:
    snapshot: str
    env_files: list[EnvFile]
    setup_script: str | None
    labels: dict[str, str]
    resources: Resources | None


@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str


@dataclass(frozen=True)
class SandboxRecord:
    handle: SandboxHandle
    labels: dict[str, str]


@dataclass(frozen=True)
class AgentLaunch:
    prompt: str
    model: str
    credentials: dict[str, str]
    server_password: str
    output_schema: dict[str, object] | None


@dataclass(frozen=True)
class AgentSession:
    session_id: str
    base_url: str


@dataclass(frozen=True)
class AttachEndpoints:
    web_url: str
    api_url: str
    terminal_ws: str
    tui_command: str


@dataclass(frozen=True)
class AgentResult:
    status: str
    pr_url: str
    summary: str
    confidence: float


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    session_id: str | None = None
    result: AgentResult | None = None


class Executor(Protocol):
    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle: ...

    def launch_agent(
        self,
        handle: SandboxHandle,
        launch: AgentLaunch,
    ) -> AgentSession: ...

    def get_attach_endpoints(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> AttachEndpoints: ...

    def stream_events(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> Iterator[AgentEvent]: ...

    def destroy(self, handle: SandboxHandle) -> None: ...

    def list_sandboxes(self) -> list[SandboxRecord]: ...
