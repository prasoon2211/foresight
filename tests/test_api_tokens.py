import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import ApiToken, Org, OrgMembership, Repo, RunState
from executor import AgentResult, FakeExecutor
from orchestration.executor_backend import use_executor
from orchestration.run_orchestrator import orchestrate_run


@pytest.mark.django_db(transaction=True)
def test_api_token_drives_signal_run_flow_and_revocation(client: Client) -> None:
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

    minted = client.post(
        f"/api/orgs/{org.id}/api-tokens",
        data={"name": "Local agent"},
        content_type="application/json",
    )
    assert minted.status_code == 201
    raw_token = minted.json()["token"]
    token = ApiToken.objects.get()
    assert raw_token.startswith("fst_")
    assert raw_token not in token.secret_hash
    listed = client.get(f"/api/orgs/{org.id}/api-tokens")
    listed_token = listed.json()[0]
    assert listed_token["id"] == token.id
    assert listed_token["name"] == "Local agent"
    assert listed_token["prefix"] == token.prefix
    assert listed_token["revoked_at"] is None
    assert "created_at" in listed_token
    assert "token" not in listed_token

    client.logout()
    authorization = f"Bearer {raw_token}"
    fake = FakeExecutor.succeeding(
        AgentResult(
            status="pr_opened",
            pr_url="https://github.com/acme/widgets/pull/17",
            summary="Fixed the widget race.",
            confidence=0.92,
        )
    )
    with use_executor(fake):
        created = client.post(
            f"/api/orgs/{org.id}/signals",
            data={
                "repo_id": repo.id,
                "title": "Fix widget race",
                "body": "Two updates can overwrite one another.",
            },
            content_type="application/json",
            headers={"Authorization": authorization},
        ).json()
        queued = client.get(
            f"/api/orgs/{org.id}/runs/{created['run_id']}",
            headers={"Authorization": authorization},
        )
        orchestrate_run(created["run_id"], fake)
        completed = client.get(
            f"/api/orgs/{org.id}/runs/{created['run_id']}",
            headers={"Authorization": authorization},
        )

    assert queued.json()["state"] == RunState.QUEUED
    assert completed.json()["state"] == RunState.AWAITING_REVIEW

    client.force_login(user)
    revoked = client.delete(f"/api/orgs/{org.id}/api-tokens/{token.id}")
    assert revoked.status_code == 204
    client.logout()

    rejected = client.get(
        f"/api/orgs/{org.id}/runs/{created['run_id']}",
        headers={"Authorization": authorization},
    )
    assert rejected.status_code == 401
    assert rejected.json() == {
        "code": "unauthorized",
        "message": "Authentication required.",
        "hint": "Use a session cookie or a valid org API token.",
    }
