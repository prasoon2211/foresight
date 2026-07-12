from executor import (
    AgentLaunch,
    EnvFile,
    FakeExecutor,
    FakeExecutorScript,
    Resources,
    SandboxSpec,
    SnapshotSpec,
)


def test_fake_executor_satisfies_the_runtime_contract() -> None:
    executor = FakeExecutor(FakeExecutorScript(setup_output="setup complete"))
    snapshot = executor.build_snapshot(
        SnapshotSpec(
            name="contract-snapshot",
            base_image="node:22-bookworm",
            repo_url="https://github.com/octocat/Hello-World.git",
            agent_version="1.17.18",
            resources=Resources(cpu=4, memory_gib=8, disk_gib=10),
        )
    )
    handle = executor.create_sandbox(
        SandboxSpec(
            snapshot=snapshot.snapshot_id,
            git_ref="master",
            git_token=None,
            env_files=[EnvFile("/workspace/repo/.env", "MODE=contract\n")],
            setup_script="printf 'setup complete'",
            labels={"managed_by": "foresight", "run_id": "13"},
            resources=Resources(cpu=4, memory_gib=8, disk_gib=10),
        )
    )
    session = executor.launch_agent(
        handle,
        AgentLaunch(
            prompt="Return a trivial result.",
            model="openai/gpt-4.1-mini",
            credentials={"OPENAI_API_KEY": "not-a-real-key"},
            server_password="contract-password",
            output_schema=None,
        ),
    )

    events = list(executor.stream_events(handle, session))
    endpoints = executor.get_attach_endpoints(handle, session)
    messages = executor.get_session_messages(handle, session)
    executor.archive(handle)
    executor.revive(handle)
    executor.destroy(handle)

    assert snapshot.output
    assert executor.read_file(handle, "/tmp/foresight/setup.log") == "setup complete"
    assert events[-1].kind == "session.idle"
    assert events[-1].session_id == session.session_id
    assert endpoints.web_url.startswith("https://")
    assert endpoints.terminal_ws.startswith("wss://")
    assert messages[-1].role == "assistant"
    assert executor.list_sandboxes() == []
