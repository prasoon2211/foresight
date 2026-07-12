import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

from core.models import Org, OrgMembership, Repo


@pytest.fixture
def admin_client(client: Client) -> tuple[Client, Org]:
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
    client.force_login(user)
    return client, org


@pytest.mark.django_db(transaction=True)
def test_agent_credential_is_encrypted_and_write_only(
    admin_client: tuple[Client, Org],
) -> None:
    client, org = admin_client

    update = client.patch(
        f"/api/orgs/{org.id}",
        data={
            "agent_credential": {
                "api_key": "llm-secret-value",
                "base_url": "https://llm.example.test/v1",
            },
            "concurrency_cap": 7,
        },
        content_type="application/json",
    )

    assert update.status_code == 200
    assert update.json() == {
        "id": org.id,
        "name": "Acme",
        "concurrency_cap": 7,
        "has_agent_credential": True,
    }
    read = client.get(f"/api/orgs/{org.id}")
    assert read.json() == update.json()
    assert "agent_credential" not in read.json()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT agent_api_key, agent_base_url FROM core_org WHERE id = %s",
            [org.id],
        )
        stored_api_key, stored_base_url = cursor.fetchone()
    assert "llm-secret-value" not in stored_api_key
    assert "llm.example.test" not in stored_base_url


@pytest.mark.django_db(transaction=True)
def test_repo_env_is_encrypted_and_write_only(
    admin_client: tuple[Client, Org],
) -> None:
    client, org = admin_client
    repo = Repo.objects.create(org=org, full_name="acme/widgets")

    update = client.patch(
        f"/api/orgs/{org.id}/repos/{repo.id}",
        data={"env": {"ANTHROPIC_API_KEY": "repo-secret-value", "MODE": "test"}},
        content_type="application/json",
    )

    assert update.status_code == 200
    assert update.json() == {
        "id": repo.id,
        "full_name": "acme/widgets",
        "default_branch": "main",
        "connection_status": "connected",
        "has_env": True,
        "base_snapshot": "node:22-bookworm",
        "snapshot_build_status": "ready",
        "snapshot_build_output": "",
        "setup_verification_status": "not_run",
        "setup_verification_output": "",
    }
    read = client.get(f"/api/orgs/{org.id}/repos/{repo.id}")
    assert read.json() == update.json()
    assert "env" not in read.json()
    with connection.cursor() as cursor:
        cursor.execute("SELECT env FROM core_repo WHERE id = %s", [repo.id])
        stored_env = cursor.fetchone()[0]
    assert "repo-secret-value" not in stored_env
