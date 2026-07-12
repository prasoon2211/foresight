from allauth.account.models import EmailAddress
from django.contrib.auth.models import User
from django.db import transaction

from core.models import Org, OrgMembership


class InviteeNotFound(Exception):
    pass


def create_org(*, name: str, owner: User) -> tuple[Org, OrgMembership]:
    with transaction.atomic():
        org = Org.objects.create(name=name)
        membership = OrgMembership.objects.create(
            org=org,
            user=owner,
            role=OrgMembership.Role.ADMIN,
        )
    return org, membership


def invite_org_member(
    *,
    org: Org,
    email: str,
    role: str,
) -> OrgMembership:
    address = (
        EmailAddress.objects.select_related("user")
        .filter(email__iexact=email, verified=True)
        .first()
    )
    if address is None:
        raise InviteeNotFound
    return OrgMembership.objects.create(org=org, user=address.user, role=role)


def update_org_settings(
    *,
    org: Org,
    agent_api_key: str | None,
    agent_base_url: str | None,
    concurrency_cap: int | None,
) -> Org:
    fields: list[str] = []
    if agent_api_key is not None:
        org.agent_api_key = agent_api_key
        org.agent_base_url = agent_base_url
        fields.extend(["agent_api_key", "agent_base_url"])
    if concurrency_cap is not None:
        org.concurrency_cap = concurrency_cap
        fields.append("concurrency_cap")
    if fields:
        org.save(update_fields=fields)
    return org
