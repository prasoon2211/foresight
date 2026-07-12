import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from core.models import Org, OrgMembership


@pytest.mark.django_db(transaction=True)
def test_member_cannot_manage_tokens_or_agent_credential(client: Client) -> None:
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
    client.force_login(user)

    token_response = client.post(
        f"/api/orgs/{org.id}/api-tokens",
        data={"name": "Forbidden token"},
        content_type="application/json",
    )
    credential_response = client.patch(
        f"/api/orgs/{org.id}",
        data={"agent_credential": {"api_key": "must-not-be-written"}},
        content_type="application/json",
    )

    expected = {
        "code": "admin_required",
        "message": "This action requires an org admin.",
        "hint": "Ask an org admin to perform this action.",
    }
    assert token_response.status_code == 403
    assert token_response.json() == expected
    assert credential_response.status_code == 403
    assert credential_response.json() == expected
    org.refresh_from_db()
    assert org.agent_api_key is None
