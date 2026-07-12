from dataclasses import dataclass

from django.contrib.auth.models import User
from django.http import HttpRequest
from ninja.security import APIKeyCookie, HttpBearer

from core.api_tokens import authenticate_api_token
from core.models import ApiToken, Org, OrgMembership


@dataclass(frozen=True)
class OrgAccess:
    org: Org
    actor: User
    role: str


class AuthenticatedRequest(HttpRequest):
    auth: User | ApiToken


class SessionAuth(APIKeyCookie):
    param_name = "sessionid"

    def authenticate(self, request: HttpRequest, key: str | None) -> User | None:
        if key and request.user.is_authenticated:
            return request.user
        return None


class ApiTokenAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> ApiToken | None:
        return authenticate_api_token(token)


session_auth = SessionAuth()
api_token_auth = ApiTokenAuth()
org_auth = [session_auth, api_token_auth]


def resolve_org_access(request: AuthenticatedRequest, org_id: int) -> OrgAccess | None:
    identity = request.auth
    if isinstance(identity, ApiToken):
        if identity.org_id != org_id:
            return None
        return OrgAccess(
            org=identity.org,
            actor=identity.created_by,
            role=OrgMembership.Role.ADMIN,
        )
    membership = (
        OrgMembership.objects.select_related("org").filter(org_id=org_id, user=identity).first()
    )
    if membership is None:
        return None
    return OrgAccess(
        org=membership.org,
        actor=membership.user,
        role=membership.role,
    )
