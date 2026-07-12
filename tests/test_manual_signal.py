import json
from pathlib import Path
from typing import Protocol, cast

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from core.models import Org, OrgMembership, Repo, ResultStatus, Run, RunState
from executor import AgentEvent, AgentMessage, FakeExecutor, FakeExecutorScript
from orchestration.executor_backend import use_executor
from orchestration.run_orchestrator import orchestrate_run


class WorkerConnectorFactory(Protocol):
    def get_worker_connector(self) -> BaseAsyncConnector: ...


@pytest.mark.django_db(transaction=True)
def test_manual_signal_runs_to_awaiting_review_over_the_api(
    client: Client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SESSION_EXPORT_ROOT", tmp_path)
    user = get_user_model().objects.create_user(
        username="member",
        email="member@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(
        org=org,
        user=user,
        role=OrgMembership.Role.MEMBER,
    )
    repo = Repo.objects.create(
        org=org,
        full_name="acme/widgets",
        snapshot_id="snapshot-123",
        setup_script="uv sync",
        env={".env": "MODE=test\n"},
    )
    client.force_login(user)
    fake = FakeExecutor(
        FakeExecutorScript(
            event_batches=[[AgentEvent(kind="session.idle")]],
            session_messages=[
                AgentMessage(
                    role="assistant",
                    text=(
                        "Finished.\n```foresight-result\n"
                        '{"status":"pr_opened",'
                        '"pr_url":"https://github.com/acme/widgets/pull/17",'
                        '"summary":"Fixed the widget race.",'
                        '"confidence":0.92}\n```'
                    ),
                )
            ],
        )
    )

    with use_executor(fake):
        create_response = client.post(
            f"/api/orgs/{org.id}/signals",
            data={
                "repo_id": repo.id,
                "title": "Fix widget race",
                "body": "Two updates can overwrite one another.",
            },
            content_type="application/json",
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["intake_state"] == "dispatched"

        queued_response = client.get(f"/api/orgs/{org.id}/runs/{created['run_id']}")
        assert queued_response.status_code == 200
        assert queued_response.json()["state"] == RunState.QUEUED

        connector = cast(WorkerConnectorFactory, app.connector)
        with app.replace_connector(connector.get_worker_connector()):
            app.run_worker(
                wait=False,
                install_signal_handlers=False,
                listen_notify=False,
            )

        run_response = client.get(f"/api/orgs/{org.id}/runs/{created['run_id']}")
        signals_response = client.get(f"/api/orgs/{org.id}/signals")
        orchestrate_run(created["run_id"], fake)

    assert run_response.status_code == 200
    assert run_response.json() == {
        "id": created["run_id"],
        "signal_id": created["id"],
        "state": RunState.AWAITING_REVIEW,
        "failure_reason": "",
        "failure_detail": "",
        "result": {
            "status": ResultStatus.PR_OPENED,
            "pr_url": "https://github.com/acme/widgets/pull/17",
            "summary": "Fixed the widget race.",
            "confidence": 0.92,
        },
    }
    assert signals_response.status_code == 200
    assert signals_response.json() == [
        {
            "id": created["id"],
            "repo_id": repo.id,
            "source": "manual",
            "title": "Fix widget race",
            "body": "Two updates can overwrite one another.",
            "intake_state": "dispatched",
            "outcome_status": RunState.AWAITING_REVIEW,
            "stranded": False,
        }
    ]
    assert [call for call in fake.calls if call != "list_sandboxes"] == [
        "create_sandbox",
        "launch_agent",
        "stream_events",
        "get_session_messages",
        "archive",
    ]
    assert fake.sandbox_specs[0].labels == {
        "managed_by": "foresight",
        "run_id": str(created["run_id"]),
        "repo": "acme/widgets",
        "trigger": "manual",
    }
    assert fake.sandbox_specs[0].snapshot == "snapshot-123"
    assert fake.sandbox_specs[0].setup_script == "uv sync"
    assert fake.sandbox_specs[0].env_files[0].target_path == ".env"
    run_export = tmp_path / f"run-{created['run_id']}.json"
    assert run_export.exists()
    assert json.loads(run_export.read_text())["messages"][0]["role"] == "assistant"
    run = Run.objects.get(pk=created["run_id"])
    assert run.session_export_path == str(run_export)
    assert run.sandbox_archived_at is not None
    prompt = fake.agent_launches[0].prompt
    assert "- Signal: Fix widget race" in prompt
    assert "<signal_body>\nTwo updates can overwrite one another.\n</signal_body>" in prompt
    assert f"git checkout -b foresight/signal-{created['id']}-run-{created['run_id']}" in prompt
    assert fake.streamed_sessions[0].base_url == "fake://fake-sandbox-1"
