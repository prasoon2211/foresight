from typing import Protocol, cast

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from procrastinate.connector import BaseAsyncConnector
from procrastinate.contrib.django import app

from core.intake import SnapshotNotReady, create_manual_signal
from core.models import Org, OrgMembership, Repo, SnapshotBuildStatus
from executor import FakeExecutor, FakeExecutorScript
from orchestration.executor_backend import use_executor


class WorkerConnectorFactory(Protocol):
    def get_worker_connector(self) -> BaseAsyncConnector: ...


def run_jobs() -> None:
    connector = cast(WorkerConnectorFactory, app.connector)
    with app.replace_connector(connector.get_worker_connector()):
        app.run_worker(
            wait=False,
            install_signal_handlers=False,
            listen_notify=False,
        )


@pytest.fixture
def admin_repo(client: Client) -> tuple[Client, Repo]:
    user = get_user_model().objects.create_user(
        username="owner",
        email="owner@example.com",
    )
    org = Org.objects.create(name="Acme")
    OrgMembership.objects.create(
        org=org,
        user=user,
        role=OrgMembership.Role.ADMIN,
    )
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    client.force_login(user)
    return client, repo


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (SnapshotBuildStatus.BUILDING, ""),
        (SnapshotBuildStatus.FAILED, "base image is unavailable"),
    ],
)
def test_snapshot_status_gates_dispatch(status: str, detail: str) -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(
        org=org,
        full_name="acme/widgets",
        snapshot_build_status=status,
        snapshot_build_output=detail,
    )

    with pytest.raises(SnapshotNotReady, match=status):
        create_manual_signal(
            repo=repo,
            title="Fix widget race",
            body="Two updates can overwrite one another.",
            enqueue_run=lambda _: None,
        )


@pytest.mark.django_db(transaction=True)
def test_manual_snapshot_rebuild_reports_status_and_build_output(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    fake = FakeExecutor()

    with use_executor(fake):
        response = client.post(f"/api/orgs/{repo.org_id}/repos/{repo.id}/snapshots")
        assert response.status_code == 202
        assert response.json()["snapshot_build_status"] == SnapshotBuildStatus.BUILDING
        run_jobs()

    repo.refresh_from_db()
    assert repo.snapshot_build_status == SnapshotBuildStatus.READY
    assert repo.snapshot_id == "fake-snapshot-1"
    assert repo.snapshot_build_output == "Fake snapshot built."
    assert fake.snapshot_specs[0].repo_url == "https://github.com/acme/widgets.git"


@pytest.mark.django_db(transaction=True)
def test_failed_snapshot_build_records_provider_output(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    fake = FakeExecutor(FakeExecutorScript(snapshot_failure="base image is unavailable"))

    with use_executor(fake):
        response = client.post(f"/api/orgs/{repo.org_id}/repos/{repo.id}/snapshots")
        assert response.status_code == 202
        run_jobs()

    repo.refresh_from_db()
    assert repo.snapshot_build_status == SnapshotBuildStatus.FAILED
    assert repo.snapshot_build_output == "base image is unavailable"


@pytest.mark.django_db
def test_manual_signal_api_explains_snapshot_gate(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    repo.snapshot_build_status = SnapshotBuildStatus.BUILDING
    repo.save(update_fields=["snapshot_build_status"])

    response = client.post(
        f"/api/orgs/{repo.org_id}/signals",
        data={
            "repo_id": repo.pk,
            "title": "Fix widget race",
            "body": "Two updates can overwrite one another.",
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    assert response.json()["code"] == "snapshot_not_ready"
    assert "building" in response.json()["message"]


@pytest.mark.django_db(transaction=True)
def test_changing_base_image_automatically_rebuilds_snapshot(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    fake = FakeExecutor()

    with use_executor(fake):
        response = client.patch(
            f"/api/orgs/{repo.org_id}/repos/{repo.id}",
            data={"base_snapshot": "ubuntu:24.04"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["snapshot_build_status"] == SnapshotBuildStatus.BUILDING
        run_jobs()

    repo.refresh_from_db()
    assert repo.base_snapshot == "ubuntu:24.04"
    assert repo.snapshot_build_status == SnapshotBuildStatus.READY
    assert fake.snapshot_specs[0].base_image == "ubuntu:24.04"


@pytest.mark.django_db
def test_verify_setup_reports_success_without_launching_an_agent(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    repo.snapshot_id = "snapshot-123"
    repo.setup_script = "printf setup-ok"
    repo.save(update_fields=["snapshot_id", "setup_script"])
    fake = FakeExecutor(FakeExecutorScript(setup_output="setup-ok"))

    with use_executor(fake):
        response = client.post(f"/api/orgs/{repo.org_id}/repos/{repo.id}/verify-setup")

    assert response.status_code == 200
    assert response.json() == {"status": "success", "output": "setup-ok"}
    assert fake.calls == ["create_sandbox", "read_file", "destroy"]
    assert fake.sandbox_specs[0].setup_script == "printf setup-ok"


@pytest.mark.django_db
def test_verify_setup_reports_failure_output_without_launching_an_agent(
    admin_repo: tuple[Client, Repo],
) -> None:
    client, repo = admin_repo
    repo.snapshot_id = "snapshot-123"
    repo.save(update_fields=["snapshot_id"])
    fake = FakeExecutor(FakeExecutorScript(setup_failure="dependency install failed"))

    with use_executor(fake):
        response = client.post(f"/api/orgs/{repo.org_id}/repos/{repo.id}/verify-setup")

    assert response.status_code == 200
    assert response.json() == {
        "status": "failed",
        "output": "dependency install failed",
    }
    assert fake.calls == ["create_sandbox"]
