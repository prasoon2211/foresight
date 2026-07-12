import re
from urllib.parse import unquote

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.test.utils import override_settings


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
@pytest.mark.django_db(transaction=True)
def test_user_signs_up_verifies_email_and_logs_in_through_headless_api(
    client: Client,
) -> None:
    signup = client.post(
        "/_allauth/browser/v1/auth/signup",
        data={"email": "owner@example.com", "password": "correct horse battery staple"},
        content_type="application/json",
    )

    assert signup.status_code == 401
    assert len(mail.outbox) == 1
    match = re.search(r"/verify-email/([^/\s]+)", str(mail.outbox[0].body))
    assert match is not None

    verification = client.post(
        "/_allauth/browser/v1/auth/email/verify",
        data={"key": unquote(match.group(1))},
        content_type="application/json",
    )
    assert verification.status_code == 401
    assert EmailAddress.objects.get(email="owner@example.com").verified

    assert client.delete("/_allauth/browser/v1/auth/session").status_code == 401
    login = client.post(
        "/_allauth/browser/v1/auth/login",
        data={
            "email": "owner@example.com",
            "password": "correct horse battery staple",
        },
        content_type="application/json",
    )

    assert login.status_code == 200
    assert login.json()["data"]["user"]["email"] == "owner@example.com"

    teammate_client = Client()
    teammate_signup = teammate_client.post(
        "/_allauth/browser/v1/auth/signup",
        data={"email": "teammate@example.com", "password": "another correct password"},
        content_type="application/json",
    )
    assert teammate_signup.status_code == 401
    teammate_key = re.search(r"/verify-email/([^/\s]+)", str(mail.outbox[1].body))
    assert teammate_key is not None
    teammate_client.post(
        "/_allauth/browser/v1/auth/email/verify",
        data={"key": unquote(teammate_key.group(1))},
        content_type="application/json",
    )

    org = client.post(
        "/api/orgs",
        data={"name": "Acme"},
        content_type="application/json",
    )
    invitation = client.post(
        f"/api/orgs/{org.json()['id']}/members",
        data={"email": "teammate@example.com", "role": "member"},
        content_type="application/json",
    )

    assert org.status_code == 201
    assert invitation.status_code == 201
    assert invitation.json()["role"] == "member"


@pytest.mark.django_db(transaction=True)
def test_authenticated_user_creates_org_and_becomes_admin(client: Client) -> None:
    user = get_user_model().objects.create_user(
        username="owner",
        email="owner@example.com",
        password="correct horse battery staple",
    )
    client.force_login(user)

    response = client.post(
        "/api/orgs",
        data={"name": "Acme"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "name": "Acme",
        "concurrency_cap": 3,
        "role": "admin",
    }


@pytest.mark.parametrize("role", ["admin", "member"])
@pytest.mark.django_db(transaction=True)
def test_org_admin_invites_existing_user_with_role(client: Client, role: str) -> None:
    users = get_user_model().objects
    owner = users.create_user(username="owner", email="owner@example.com")
    teammate = users.create_user(username="teammate", email="teammate@example.com")
    EmailAddress.objects.create(
        user=teammate,
        email=teammate.email,
        verified=True,
        primary=True,
    )
    client.force_login(owner)
    org_id = client.post(
        "/api/orgs",
        data={"name": "Acme"},
        content_type="application/json",
    ).json()["id"]

    response = client.post(
        f"/api/orgs/{org_id}/members",
        data={"email": teammate.email, "role": role},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json() == {
        "user_id": teammate.id,
        "email": "teammate@example.com",
        "role": role,
    }
    duplicate = client.post(
        f"/api/orgs/{org_id}/members",
        data={"email": teammate.email, "role": role},
        content_type="application/json",
    )
    assert duplicate.status_code == 409
    assert duplicate.json() == {
        "code": "already_a_member",
        "message": "That user is already an org member.",
        "hint": "Use the existing membership instead of inviting the user again.",
    }


@pytest.mark.django_db(transaction=True)
def test_inviting_unknown_email_returns_agent_legible_error(client: Client) -> None:
    owner = get_user_model().objects.create_user(
        username="owner",
        email="owner@example.com",
    )
    client.force_login(owner)
    org_id = client.post(
        "/api/orgs",
        data={"name": "Acme"},
        content_type="application/json",
    ).json()["id"]

    response = client.post(
        f"/api/orgs/{org_id}/members",
        data={"email": "unknown@example.com", "role": "member"},
        content_type="application/json",
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "user_not_found",
        "message": "No verified user has that email address.",
        "hint": "Ask the teammate to sign up and verify their email, then try again.",
    }


@pytest.mark.django_db(transaction=True)
def test_headless_auth_validation_errors_include_agent_hint(client: Client) -> None:
    response = client.post(
        "/_allauth/browser/v1/auth/login",
        data={"email": "missing@example.com", "password": "wrong password"},
        content_type="application/json",
    )

    payload = response.json()
    assert response.status_code == 400
    assert payload["code"] == "email_password_mismatch"
    assert payload["message"]
    assert payload["hint"] == "Correct the supplied credentials or account details, then try again."
