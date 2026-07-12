import os
import ssl
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest

from core.session_exports import store_session_export
from executor import (
    AgentLaunch,
    EnvFile,
    Resources,
    SandboxSpec,
    SnapshotSpec,
)
from executor.daytona import DaytonaExecutor

pytestmark = [
    pytest.mark.daytona,
    pytest.mark.skipif(
        os.getenv("RUN_DAYTONA_TESTS") != "1",
        reason="set RUN_DAYTONA_TESTS=1 for provider-credentialed tests",
    ),
]


def test_real_daytona_smoke_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.getenv("DAYTONA_API_KEY") or not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Daytona and OpenAI credentials are required")

    name = f"foresight-contract-{uuid.uuid4().hex[:12]}"
    executor = DaytonaExecutor()
    snapshot_id = ""
    handle = None
    try:
        snapshot = executor.build_snapshot(
            SnapshotSpec(
                name=name,
                base_image="node:22-bookworm",
                repo_url="https://github.com/octocat/Hello-World.git",
                agent_version="1.17.18",
                resources=Resources(cpu=4, memory_gib=8, disk_gib=10),
            )
        )
        snapshot_id = snapshot.snapshot_id
        assert snapshot.output

        handle = executor.create_sandbox(
            SandboxSpec(
                snapshot=snapshot_id,
                env_files=[
                    EnvFile(
                        "/workspace/repo/.foresight-contract",
                        "materialized-by-foresight\n",
                    )
                ],
                setup_script=(
                    "git fetch --all && "
                    'test "$(cat .foresight-contract)" = materialized-by-foresight && '
                    "printf setup-complete"
                ),
                labels={
                    "managed_by": "foresight",
                    "run_id": "13",
                    "smoke": name,
                },
                resources=Resources(cpu=4, memory_gib=8, disk_gib=10),
            )
        )
        assert executor.read_file(handle, "/tmp/foresight/setup.log") == "setup-complete"

        session = executor.launch_agent(
            handle,
            AgentLaunch(
                prompt=(
                    "Do not edit files. Reply with one short sentence confirming "
                    "that the Foresight Daytona smoke test completed."
                ),
                model="openai/gpt-4.1-mini",
                credentials={"OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]},
                server_password=uuid.uuid4().hex,
                output_schema=None,
            ),
        )
        events = list(executor.stream_events(handle, session))
        messages = executor.get_session_messages(handle, session)
        assert any(event.kind == "session.idle" for event in events)
        assert any(message.role == "assistant" and message.text for message in messages)

        monkeypatch.setattr(
            "django.conf.settings.SESSION_EXPORT_ROOT",
            tmp_path,
        )
        export_path = store_session_export(run_id=13, messages=messages)
        assert Path(export_path).is_file()

        endpoints = executor.get_attach_endpoints(handle, session)
        signed_url = urlsplit(endpoints.api_url)
        health_url = urlunsplit(
            signed_url._replace(path=f"{signed_url.path.rstrip('/')}/global/health")
        )
        with httpx.Client(verify=ssl.create_default_context()) as browser:
            health = browser.get(
                health_url,
                auth=("opencode", session.server_password),
                timeout=30,
            )
        assert health.status_code == 200
        assert endpoints.terminal_ws.startswith("wss://")
        assert (
            executor.read_file(
                handle,
                "/root/.local/share/opencode/auth.json",
            )
            is None
        )

        executor.archive(handle)
        executor.revive(handle)
        assert executor.read_file(handle, "/workspace/repo/.foresight-contract")
        executor.destroy(handle)
        handle = None
    finally:
        if handle is not None:
            executor.destroy(handle)
        if snapshot_id:
            executor.delete_snapshot(snapshot_id)
