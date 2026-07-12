import json
import shlex
import sys
import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import httpx
from daytona import (
    CreateSandboxFromSnapshotParams,
    CreateSnapshotParams,
    Daytona,
    DaytonaError,
    Image,
    ListSandboxesQuery,
    SandboxState,
)
from daytona import (
    Resources as DaytonaResources,
)

from executor.protocol import (
    SETUP_LOG_PATH,
    AgentEvent,
    AgentLaunch,
    AgentMessage,
    AgentSession,
    AttachEndpoints,
    SandboxDied,
    SandboxHandle,
    SandboxRecord,
    SandboxSpec,
    SetupFailed,
    SnapshotBuild,
    SnapshotBuildFailed,
    SnapshotSpec,
)

WORKSPACE = "/workspace/repo"
AGENT_PORT = 4096
ARCHIVE_RETENTION_MINUTES = 14 * 24 * 60


class DaytonaExecutor:
    """Daytona provider binding for the Foresight executor boundary."""

    executor_type = "daytona"

    def __init__(self, client: Daytona | None = None) -> None:
        self._daytona = client or Daytona()
        self._http = httpx.Client(timeout=httpx.Timeout(connect=30, read=30, write=30, pool=30))
        self._event_streams: dict[str, tuple[Any, httpx.Response]] = {}

    def build_snapshot(self, spec: SnapshotSpec) -> SnapshotBuild:
        logs: list[str] = []
        commands = [
            (
                "apt-get update && DEBIAN_FRONTEND=noninteractive "
                "apt-get install -y --no-install-recommends "
                "ca-certificates curl git docker.io docker-compose fuse-overlayfs && "
                "rm -rf /var/lib/apt/lists/*"
            ),
            f"npm install --global opencode-ai@{shlex.quote(spec.agent_version)}",
        ]
        if spec.clone_token is None:
            commands.append(f"git clone --depth=1 {shlex.quote(spec.repo_url)} {WORKSPACE}")
        image = Image.base(spec.base_image).run_commands(*commands)
        if spec.clone_token is None:
            image = image.workdir(WORKSPACE)
        base_name = f"{spec.name}-toolchain" if spec.clone_token else spec.name
        resources = DaytonaResources(
            cpu=spec.resources.cpu,
            memory=spec.resources.memory_gib,
            disk=spec.resources.disk_gib,
        )
        try:
            snapshot = self._daytona.snapshot.create(
                CreateSnapshotParams(
                    name=base_name,
                    image=image,
                    resources=resources,
                ),
                on_logs=logs.append,
                timeout=0,
            )
            if spec.clone_token is not None:
                snapshot = self._clone_private_repo_snapshot(
                    spec=spec,
                    toolchain_snapshot=snapshot,
                )
        except DaytonaError as error:
            detail = "".join(logs) or str(error)
            raise SnapshotBuildFailed(detail) from error
        return SnapshotBuild(
            snapshot_id=snapshot.name,
            output="".join(logs) or f"Snapshot {snapshot.name} built.",
        )

    def _clone_private_repo_snapshot(
        self,
        *,
        spec: SnapshotSpec,
        toolchain_snapshot: Any,
    ) -> Any:
        sandbox = self._daytona.create(
            CreateSandboxFromSnapshotParams(
                snapshot=toolchain_snapshot.name,
                auto_stop_interval=0,
            ),
            timeout=120,
        )
        try:
            response = sandbox.process.exec(
                (
                    "git -c http.extraHeader="
                    "'Authorization: Bearer '\"$FORESIGHT_CLONE_TOKEN\" "
                    f"clone --depth=1 {shlex.quote(spec.repo_url)} {WORKSPACE}"
                ),
                env={"FORESIGHT_CLONE_TOKEN": spec.clone_token or ""},
                timeout=300,
            )
            if response.exit_code != 0:
                raise SnapshotBuildFailed(response.result or "private clone failed")
            sandbox.stop(timeout=120)
            sandbox._experimental_create_snapshot(spec.name, timeout=600)
            return self._daytona.snapshot.get(spec.name)
        finally:
            sandbox.delete(timeout=120)
            self._daytona.snapshot.delete(toolchain_snapshot)

    def create_sandbox(self, spec: SandboxSpec) -> SandboxHandle:
        sandbox = self._daytona.create(
            CreateSandboxFromSnapshotParams(
                snapshot=spec.snapshot,
                labels=spec.labels,
                auto_stop_interval=0,
                auto_delete_interval=ARCHIVE_RETENTION_MINUTES,
            ),
            timeout=120,
        )
        handle = SandboxHandle(sandbox_id=sandbox.id)
        try:
            sandbox.process.exec("mkdir -p /tmp/foresight")
            self._ensure_docker(sandbox)
            for env_file in spec.env_files:
                parent = env_file.target_path.rsplit("/", 1)[0]
                if parent:
                    sandbox.process.exec(f"mkdir -p {shlex.quote(parent)}")
                sandbox.fs.upload_file(
                    env_file.content.encode(),
                    env_file.target_path,
                )
            git_environment = (
                {"FORESIGHT_GIT_TOKEN": spec.git_token} if spec.git_token is not None else None
            )
            authorization = (
                "-c http.extraHeader='Authorization: Bearer '\"$FORESIGHT_GIT_TOKEN\" "
                if spec.git_token is not None
                else ""
            )
            git_ref = shlex.quote(spec.git_ref)
            sync = sandbox.process.exec(
                (
                    f"git {authorization}fetch --prune origin {git_ref} && "
                    f"git checkout -B {git_ref} FETCH_HEAD"
                ),
                cwd=WORKSPACE,
                env=git_environment,
                timeout=300,
            )
            if sync.exit_code != 0:
                raise SetupFailed(sync.result or "failed to fetch latest repo code")
            output = sync.result
            if spec.setup_script:
                response = sandbox.process.exec(
                    spec.setup_script,
                    cwd=WORKSPACE,
                    timeout=1800,
                )
                output = f"{output}{response.result}"
                if response.exit_code != 0:
                    raise SetupFailed(output or f"setup exited {response.exit_code}")
            sandbox.fs.upload_file(output.encode(), SETUP_LOG_PATH)
            sandbox.set_labels({**spec.labels, "provisioning_complete": "true"})
        except SetupFailed:
            self._retire_failed_sandbox(sandbox, spec)
            raise
        except DaytonaError as error:
            self._retire_failed_sandbox(sandbox, spec)
            raise SetupFailed(str(error)) from error
        return handle

    @staticmethod
    def _retire_failed_sandbox(sandbox: Any, spec: SandboxSpec) -> None:
        if "run_id" not in spec.labels:
            sandbox.delete()
            return
        sandbox.set_auto_delete_interval(ARCHIVE_RETENTION_MINUTES)
        sandbox.stop(timeout=120)
        sandbox.archive()

    @staticmethod
    def _ensure_docker(sandbox: Any) -> None:
        if sandbox.process.exec("docker info >/dev/null 2>&1", timeout=15).exit_code == 0:
            return
        sandbox.process.exec(
            (
                "nohup dockerd --host=unix:///var/run/docker.sock "
                "--storage-driver=fuse-overlayfs "
                ">/tmp/foresight/dockerd.log 2>&1 </dev/null &"
            ),
            timeout=30,
        )
        for _ in range(30):
            if sandbox.process.exec("docker info >/dev/null 2>&1", timeout=15).exit_code == 0:
                return
            time.sleep(1)
        log = sandbox.fs.download_file("/tmp/foresight/dockerd.log")
        detail = log.decode() if log else "Docker daemon did not become ready"
        raise SetupFailed(detail)

    def launch_agent(
        self,
        handle: SandboxHandle,
        launch: AgentLaunch,
    ) -> AgentSession:
        sandbox = self._sandbox(handle)
        preview = sandbox.get_preview_link(AGENT_PORT)
        headers = {"x-daytona-preview-token": preview.token}
        auth = ("opencode", launch.server_password)
        if not self._healthy(preview.url, headers, auth):
            environment = {
                **launch.credentials,
                "OPENCODE_SERVER_PASSWORD": launch.server_password,
                "OPENCODE_PERMISSION": '{"*":"allow"}',
            }
            command = (
                "nohup opencode serve --hostname 0.0.0.0 "
                f"--port {AGENT_PORT} "
                ">/tmp/foresight/agent.log 2>&1 </dev/null &"
            )
            sandbox.process.exec(
                command,
                cwd=WORKSPACE,
                env=environment,
                timeout=30,
            )
            self._wait_until_healthy(preview.url, headers, auth)

        title = f"Foresight {handle.sandbox_id}"
        session_id = self._existing_session(preview.url, headers, auth, title)
        prompt_submitted = session_id is not None and self._session_has_user_message(
            preview.url,
            headers,
            auth,
            session_id,
        )
        if session_id is None:
            response = self._http.post(
                f"{preview.url.rstrip('/')}/session",
                headers=headers,
                auth=auth,
                json={"title": title},
            )
            response.raise_for_status()
            session_id = str(response.json()["id"])
        if not prompt_submitted:
            event_stream = self._http.stream(
                "GET",
                f"{preview.url.rstrip('/')}/global/event",
                headers=headers,
                auth=auth,
                timeout=httpx.Timeout(connect=30, read=None, write=30, pool=30),
            )
            event_response = event_stream.__enter__()
            provider_id, model_id = launch.model.split("/", 1)
            prompt: dict[str, Any] = {
                "model": {
                    "providerID": provider_id,
                    "modelID": model_id,
                },
                "parts": [{"type": "text", "text": launch.prompt}],
            }
            if launch.output_schema is not None:
                prompt["format"] = {
                    "type": "json_schema",
                    "schema": launch.output_schema,
                }
            try:
                event_response.raise_for_status()
                self._event_streams[session_id] = (event_stream, event_response)
                response = self._http.post(
                    f"{preview.url.rstrip('/')}/session/{quote(session_id, safe='')}/prompt_async",
                    headers=headers,
                    auth=auth,
                    json=prompt,
                )
                response.raise_for_status()
            except BaseException:
                self._event_streams.pop(session_id, None)
                event_stream.__exit__(*sys.exc_info())
                raise
        return AgentSession(
            session_id=session_id,
            base_url=preview.url,
            server_password=launch.server_password,
        )

    def get_attach_endpoints(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> AttachEndpoints:
        sandbox = self._sandbox(handle)
        signed = sandbox.create_signed_preview_url(
            AGENT_PORT,
            expires_in_seconds=3600,
        )
        pty_id = f"foresight-{session.session_id}"
        existing = {pty.id for pty in sandbox.process.list_pty_sessions()}
        if pty_id not in existing:
            pty = sandbox.process.create_pty_session(pty_id, cwd=WORKSPACE)
            pty.disconnect()
        toolbox_url = str(sandbox.toolbox_proxy_url).rstrip("/")
        terminal_ws = (
            (f"{toolbox_url}/process/pty/{quote(pty_id, safe='')}/connect")
            .replace("https://", "wss://", 1)
            .replace("http://", "ws://", 1)
        )
        attach_url = shlex.quote(signed.url)
        return AttachEndpoints(
            web_url=signed.url,
            api_url=signed.url,
            terminal_ws=terminal_ws,
            tui_command=(
                f"opencode attach {attach_url} --session "
                f"{shlex.quote(session.session_id)} -p "
                f"{shlex.quote(session.server_password)}"
            ),
        )

    def stream_events(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> Iterator[AgentEvent]:
        headers = self._preview_headers(handle)
        failures = 0
        first_connection = True
        while failures < 5:
            if not first_connection and self._session_completed(handle, session):
                yield AgentEvent(kind="session.idle", session_id=session.session_id)
                return
            try:
                pending = self._event_streams.pop(session.session_id, None)
                if pending is None:
                    event_stream = self._http.stream(
                        "GET",
                        f"{session.base_url.rstrip('/')}/global/event",
                        headers=headers,
                        auth=("opencode", session.server_password),
                        timeout=httpx.Timeout(connect=30, read=None, write=30, pool=30),
                    )
                    response = event_stream.__enter__()
                else:
                    event_stream, response = pending
                try:
                    response.raise_for_status()
                    first_connection = False
                    failures = 0
                    data_lines: list[str] = []
                    for line in response.iter_lines():
                        if line.startswith("data:"):
                            data_lines.append(line.removeprefix("data:").lstrip())
                            continue
                        if line or not data_lines:
                            continue
                        event = self._normalize_event("\n".join(data_lines))
                        data_lines = []
                        if event is None:
                            continue
                        yield event
                        if event.kind == "server.connected" and self._session_completed(
                            handle, session
                        ):
                            yield AgentEvent(
                                kind="session.idle",
                                session_id=session.session_id,
                            )
                            return
                        if event.session_id == session.session_id and event.kind in {
                            "session.idle",
                            "session.error",
                        }:
                            return
                finally:
                    event_stream.__exit__(None, None, None)
            except (httpx.HTTPError, json.JSONDecodeError):
                failures += 1
            else:
                failures += 1
            if self._session_completed(handle, session):
                yield AgentEvent(kind="session.idle", session_id=session.session_id)
                return
            time.sleep(min(2**failures, 10))
        raise SandboxDied("OpenCode event stream could not be recovered")

    def get_session_messages(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> list[AgentMessage]:
        response = self._http.get(
            f"{session.base_url.rstrip('/')}/session/{quote(session.session_id, safe='')}/message",
            headers=self._preview_headers(handle),
            auth=("opencode", session.server_password),
        )
        response.raise_for_status()
        messages: list[AgentMessage] = []
        for item in response.json():
            info = item.get("info", item)
            role = info.get("role")
            text = "\n".join(
                str(part.get("text", ""))
                for part in item.get("parts", [])
                if part.get("type") == "text" and part.get("text")
            )
            if role and text:
                messages.append(AgentMessage(role=str(role), text=text))
        return messages

    def read_file(self, handle: SandboxHandle, path: str) -> str | None:
        try:
            content = self._sandbox(handle).fs.download_file(path)
        except DaytonaError:
            return None
        return content.decode() if content is not None else None

    def archive(self, handle: SandboxHandle) -> None:
        sandbox = self._sandbox(handle)
        if sandbox.state == SandboxState.ARCHIVED:
            return
        sandbox.set_auto_delete_interval(ARCHIVE_RETENTION_MINUTES)
        if sandbox.state != SandboxState.STOPPED:
            sandbox.stop(timeout=120)
        sandbox.archive()

    def revive(self, handle: SandboxHandle) -> None:
        sandbox = self._sandbox(handle)
        if sandbox.state != SandboxState.STARTED:
            sandbox.start(timeout=180)

    def destroy(self, handle: SandboxHandle) -> None:
        try:
            self._sandbox(handle).delete(timeout=120)
        except DaytonaError as error:
            if "not found" not in str(error).lower():
                raise

    def list_sandboxes(self) -> list[SandboxRecord]:
        return [
            SandboxRecord(
                handle=SandboxHandle(sandbox_id=sandbox.id),
                labels=dict(sandbox.labels or {}),
            )
            for sandbox in self._daytona.list(
                ListSandboxesQuery(labels={"managed_by": "foresight"})
            )
        ]

    def delete_snapshot(self, snapshot_id: str) -> None:
        try:
            snapshot = self._daytona.snapshot.get(snapshot_id)
            self._daytona.snapshot.delete(snapshot)
        except DaytonaError as error:
            if "not found" not in str(error).lower():
                raise

    def _sandbox(self, handle: SandboxHandle) -> Any:
        return self._daytona.get(handle.sandbox_id)

    def _healthy(
        self,
        base_url: str,
        headers: dict[str, str],
        auth: tuple[str, str],
    ) -> bool:
        try:
            response = self._http.get(
                f"{base_url.rstrip('/')}/global/health",
                headers=headers,
                auth=auth,
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _wait_until_healthy(
        self,
        base_url: str,
        headers: dict[str, str],
        auth: tuple[str, str],
    ) -> None:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if self._healthy(base_url, headers, auth):
                return
            time.sleep(1)
        raise SandboxDied("OpenCode server did not become healthy")

    def _existing_session(
        self,
        base_url: str,
        headers: dict[str, str],
        auth: tuple[str, str],
        title: str,
    ) -> str | None:
        response = self._http.get(
            f"{base_url.rstrip('/')}/session",
            headers=headers,
            auth=auth,
        )
        response.raise_for_status()
        for session in response.json():
            if session.get("title") == title:
                return str(session["id"])
        return None

    def _session_has_user_message(
        self,
        base_url: str,
        headers: dict[str, str],
        auth: tuple[str, str],
        session_id: str,
    ) -> bool:
        response = self._http.get(
            f"{base_url.rstrip('/')}/session/{quote(session_id, safe='')}/message",
            headers=headers,
            auth=auth,
        )
        response.raise_for_status()
        return any(item.get("info", item).get("role") == "user" for item in response.json())

    def _session_completed(
        self,
        handle: SandboxHandle,
        session: AgentSession,
    ) -> bool:
        try:
            response = self._http.get(
                f"{session.base_url.rstrip('/')}/session/status",
                headers=self._preview_headers(handle),
                auth=("opencode", session.server_password),
            )
            response.raise_for_status()
            status = response.json().get(session.session_id, {})
            status_type = status.get("type") if isinstance(status, dict) else status
            return status_type == "idle" and bool(self.get_session_messages(handle, session))
        except (DaytonaError, httpx.HTTPError):
            return False

    def _preview_headers(self, handle: SandboxHandle) -> dict[str, str]:
        preview = self._sandbox(handle).get_preview_link(AGENT_PORT)
        return {"x-daytona-preview-token": preview.token}

    @staticmethod
    def _normalize_event(raw_data: str) -> AgentEvent | None:
        envelope = json.loads(raw_data)
        payload = envelope.get("payload", envelope)
        kind = payload.get("type")
        if not kind:
            return None
        properties = payload.get("properties", {})
        session_id = (
            properties.get("sessionID")
            or properties.get("sessionId")
            or properties.get("session_id")
        )
        status = properties.get("status", {})
        if kind == "session.status" and isinstance(status, dict):
            if status.get("type") == "idle":
                kind = "session.idle"
        return AgentEvent(
            kind=str(kind),
            session_id=str(session_id) if session_id else None,
        )
