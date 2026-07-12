import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import ApiToken, Org


def mint_api_token(
    *,
    org: Org,
    name: str,
    created_by: User,
) -> tuple[ApiToken, str]:
    prefix = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    token = ApiToken.objects.create(
        org=org,
        name=name,
        prefix=prefix,
        secret_hash=make_password(secret),
        created_by=created_by,
    )
    return token, f"fst_{prefix}_{secret}"


def authenticate_api_token(raw_token: str) -> ApiToken | None:
    scheme, separator, remainder = raw_token.partition("_")
    prefix, secret_separator, secret = remainder.partition("_")
    if scheme != "fst" or not separator or not secret_separator:
        return None
    token = (
        ApiToken.objects.select_related("org", "created_by")
        .filter(prefix=prefix, revoked_at__isnull=True)
        .first()
    )
    if token is None or not check_password(secret, token.secret_hash):
        return None
    return token


def revoke_api_token(token: ApiToken) -> None:
    if token.revoked_at is None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
