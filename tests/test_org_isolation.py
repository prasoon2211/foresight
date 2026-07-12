import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import Org, OrgMembership, Repo, Run, Signal


@pytest.mark.django_db(transaction=True)
def test_member_gets_not_found_for_other_org_signals_and_runs(client: Client) -> None:
    user = get_user_model().objects.create_user(
        username="member-a",
        email="member-a@example.com",
    )
    org_a = Org.objects.create(name="Org A")
    OrgMembership.objects.create(
        org=org_a,
        user=user,
        role=OrgMembership.Role.MEMBER,
    )
    org_b = Org.objects.create(name="Org B")
    repo_b = Repo.objects.create(org=org_b, full_name="org-b/widgets")
    signal_b = Signal.objects.create(
        org=org_b,
        repo=repo_b,
        title="Private signal",
        body="Must not leak.",
    )
    run_b = Run.objects.create(signal=signal_b)
    client.force_login(user)

    signal_response = client.get(f"/api/orgs/{org_b.id}/signals/{signal_b.id}")
    run_response = client.get(f"/api/orgs/{org_b.id}/runs/{run_b.id}")
    stop_response = client.post(f"/api/orgs/{org_b.id}/runs/{run_b.id}/stop")
    rerun_response = client.post(f"/api/orgs/{org_b.id}/signals/{signal_b.id}/rerun")

    for response in [signal_response, run_response, stop_response, rerun_response]:
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
