from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

SETUP_LOG_PATH = "/tmp/foresight/setup.log"


class SetupFailed(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class SandboxDied(Exception):
    pass


class TranscriptUnavailable(Exception):
    pass


class SnapshotBuildFailed(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


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
class SnapshotSpec:
    name: str
    base_image: str
    repo_url: str
    agent_version: str
    resources: Resources


@dataclass(frozen=True)
class SnapshotBuild:
    snapshot_id: str
    output: str


@dataclass(frozen=True)
class SandboxHandle:
    sandbox_id: str


@dataclass(frozen=True)
class SandboxRecord:
    handle: SandboxHandle
    labels: dict[str, str]

    @property
    def run_id(self) -> int | None:
        value = self.labels.get("run_id", "")
        return int(value) if value.isdigit() else None


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
    server_password: str = ""


@dataclass(frozen=True)
class AgentMessage:
    role: str
    text: str


@dataclass(frozen=True)
class AttachEndpoints:
    web_url: str
    api_url: str
    terminal_ws: str
    tui_command: str


@dataclass(frozen=True)
class AgentResult:
    status: str
    pr_url: str | None
    summary: str
    confidence: float


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    session_id: str | None = None


class Executor(Protocol):
    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle:
        """Create a sandbox carrying the supplied provider labels."""
        ...

    def launch_agent(
        self,
        handle: SandboxHandle,
        launch: AgentLaunch,
    ) -> AgentSession:
        """Launch once per sandbox; repeated calls return the existing session."""
        ...

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

    def get_session_messages(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> list[AgentMessage]: ...

    def read_file(self, handle: SandboxHandle, path: str) -> str | None: ...

    def destroy(self, handle: SandboxHandle) -> None: ...


class SandboxInventory(Protocol):
    def list_sandboxes(self) -> list[SandboxRecord]: ...


class DurableExecutor(Executor, SandboxInventory, Protocol):
    """Executor plus provider inventory for recovery and reconciliation."""

    executor_type: str

    def build_snapshot(self, spec: SnapshotSpec) -> SnapshotBuild: ...

    def archive(self, handle: SandboxHandle) -> None: ...

    def revive(self, handle: SandboxHandle) -> None: ...
