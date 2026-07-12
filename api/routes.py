from django.contrib.auth.models import User
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.responses import Status

from api.auth import (
    AuthenticatedRequest,
    OrgAccess,
    org_auth,
    resolve_org_access,
    session_auth,
)
from api.errors import ApiError
from api.schemas import (
    ApiTokenCreatedOut,
    ApiTokenCreateIn,
    ApiTokenOut,
    CreatedSignalOut,
    ManualSignalIn,
    OrgCreateIn,
    OrgMemberIn,
    OrgMemberOut,
    OrgOut,
    OrgSettingsIn,
    OrgSettingsOut,
    RepoOut,
    RepoSettingsIn,
    RunOut,
    RunResultOut,
    SignalOut,
)
from core.api_tokens import mint_api_token, revoke_api_token
from core.intake import create_manual_signal
from core.models import ApiToken, OrgMembership, Repo, Run, Signal
from core.organizations import create_org, invite_org_member, update_org_settings
from core.outcome import RunOutcome, derive_outcome_status
from core.repositories import update_repo_env
from orchestration.tasks import enqueue_run_orchestrator

router = Router(tags=["orgs", "signals", "runs"])


def get_org_access(request: AuthenticatedRequest, org_id: int) -> OrgAccess:
    access = resolve_org_access(request, org_id)
    if access is None:
        raise Http404
    return access


def require_admin(access: OrgAccess) -> None:
    if access.role != OrgMembership.Role.ADMIN:
        raise ApiError(
            status_code=403,
            code="admin_required",
            message="This action requires an org admin.",
            hint="Ask an org admin to perform this action.",
        )


def signal_out(signal: Signal) -> SignalOut:
    return SignalOut(
        id=signal.pk,
        repo_id=signal.repo_id,
        source=signal.source,
        title=signal.title,
        body=signal.body,
        intake_state=signal.intake_state,
        outcome_status=derive_outcome_status(
            signal.intake_state,
            (
                RunOutcome(state=state, pr_merged=pr_merged_at is not None)
                for state, pr_merged_at in signal.runs.order_by("created_at", "pk").values_list(
                    "state", "pr_merged_at"
                )
            ),
        ),
    )


@router.post("/orgs", auth=session_auth, response={201: OrgOut})
def create_organization(
    request: AuthenticatedRequest,
    payload: OrgCreateIn,
) -> Status[OrgOut]:
    if not isinstance(request.auth, User):
        raise ApiError(
            status_code=401,
            code="unauthorized",
            message="A user session is required to create an org.",
            hint="Log in with a verified account, then try again.",
        )
    org, membership = create_org(name=payload.name, owner=request.auth)
    return Status(
        201,
        OrgOut(
            id=org.pk,
            name=org.name,
            concurrency_cap=org.concurrency_cap,
            role=membership.role,
        ),
    )


@router.post(
    "/orgs/{org_id}/members",
    auth=org_auth,
    response={201: OrgMemberOut},
)
def invite_member(
    request: AuthenticatedRequest,
    org_id: int,
    payload: OrgMemberIn,
) -> Status[OrgMemberOut]:
    access = get_org_access(request, org_id)
    require_admin(access)
    invited = invite_org_member(
        org=access.org,
        email=payload.email,
        role=payload.role,
    )
    return Status(
        201,
        OrgMemberOut(
            user_id=invited.user_id,
            email=invited.user.email,
            role=invited.role,
        ),
    )


@router.get(
    "/orgs/{org_id}",
    auth=org_auth,
    response=OrgSettingsOut,
)
def get_organization(
    request: AuthenticatedRequest,
    org_id: int,
) -> OrgSettingsOut:
    org = get_org_access(request, org_id).org
    return OrgSettingsOut(
        id=org.pk,
        name=org.name,
        concurrency_cap=org.concurrency_cap,
        has_agent_credential=bool(org.agent_api_key),
    )


@router.patch(
    "/orgs/{org_id}",
    auth=org_auth,
    response=OrgSettingsOut,
)
def change_organization_settings(
    request: AuthenticatedRequest,
    org_id: int,
    payload: OrgSettingsIn,
) -> OrgSettingsOut:
    access = get_org_access(request, org_id)
    require_admin(access)
    credential = payload.agent_credential
    org = update_org_settings(
        org=access.org,
        agent_api_key=credential.api_key if credential else None,
        agent_base_url=credential.base_url if credential else None,
        concurrency_cap=payload.concurrency_cap,
    )
    return OrgSettingsOut(
        id=org.pk,
        name=org.name,
        concurrency_cap=org.concurrency_cap,
        has_agent_credential=bool(org.agent_api_key),
    )


@router.get(
    "/orgs/{org_id}/repos/{repo_id}",
    auth=org_auth,
    response=RepoOut,
)
def get_repo(
    request: AuthenticatedRequest,
    org_id: int,
    repo_id: int,
) -> RepoOut:
    get_org_access(request, org_id)
    repo = get_object_or_404(Repo, pk=repo_id, org_id=org_id)
    return RepoOut(
        id=repo.pk,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        has_env=bool(repo.env),
    )


@router.patch(
    "/orgs/{org_id}/repos/{repo_id}",
    auth=org_auth,
    response=RepoOut,
)
def change_repo_settings(
    request: AuthenticatedRequest,
    org_id: int,
    repo_id: int,
    payload: RepoSettingsIn,
) -> RepoOut:
    get_org_access(request, org_id)
    repo = get_object_or_404(Repo, pk=repo_id, org_id=org_id)
    update_repo_env(repo=repo, env=payload.env)
    return RepoOut(
        id=repo.pk,
        full_name=repo.full_name,
        default_branch=repo.default_branch,
        has_env=bool(repo.env),
    )


@router.post(
    "/orgs/{org_id}/api-tokens",
    auth=org_auth,
    response={201: ApiTokenCreatedOut},
)
def create_api_token(
    request: AuthenticatedRequest,
    org_id: int,
    payload: ApiTokenCreateIn,
) -> Status[ApiTokenCreatedOut]:
    access = get_org_access(request, org_id)
    require_admin(access)
    token, raw_token = mint_api_token(
        org=access.org,
        name=payload.name,
        created_by=access.actor,
    )
    return Status(
        201,
        ApiTokenCreatedOut(
            id=token.pk,
            name=token.name,
            prefix=token.prefix,
            token=raw_token,
            created_at=token.created_at,
        ),
    )


@router.get(
    "/orgs/{org_id}/api-tokens",
    auth=org_auth,
    response=list[ApiTokenOut],
)
def list_api_tokens(
    request: AuthenticatedRequest,
    org_id: int,
) -> list[ApiTokenOut]:
    access = get_org_access(request, org_id)
    require_admin(access)
    return [
        ApiTokenOut(
            id=token.pk,
            name=token.name,
            prefix=token.prefix,
            created_at=token.created_at,
            revoked_at=token.revoked_at,
        )
        for token in access.org.api_tokens.order_by("created_at", "pk")
    ]


@router.delete(
    "/orgs/{org_id}/api-tokens/{token_id}",
    auth=org_auth,
    response={204: None},
)
def delete_api_token(
    request: AuthenticatedRequest,
    org_id: int,
    token_id: int,
) -> Status[None]:
    access = get_org_access(request, org_id)
    require_admin(access)
    token = get_object_or_404(ApiToken, pk=token_id, org=access.org)
    revoke_api_token(token)
    return Status(204, None)


@router.post(
    "/orgs/{org_id}/signals",
    auth=org_auth,
    response={201: CreatedSignalOut},
)
def create_signal(
    request: AuthenticatedRequest,
    org_id: int,
    payload: ManualSignalIn,
) -> Status[CreatedSignalOut]:
    get_org_access(request, org_id)
    repo = get_object_or_404(Repo, pk=payload.repo_id, org_id=org_id)
    signal, run = create_manual_signal(
        repo=repo,
        title=payload.title,
        body=payload.body,
        enqueue_run=enqueue_run_orchestrator,
    )
    return Status(
        201,
        CreatedSignalOut(
            id=signal.pk,
            run_id=run.pk,
            intake_state=signal.intake_state,
        ),
    )


@router.get(
    "/orgs/{org_id}/signals",
    auth=org_auth,
    response=list[SignalOut],
)
def list_signals(
    request: AuthenticatedRequest,
    org_id: int,
) -> list[SignalOut]:
    get_org_access(request, org_id)
    return [
        signal_out(signal)
        for signal in Signal.objects.filter(org_id=org_id).order_by("created_at", "pk")
    ]


@router.get(
    "/orgs/{org_id}/signals/{signal_id}",
    auth=org_auth,
    response=SignalOut,
)
def get_signal(
    request: AuthenticatedRequest,
    org_id: int,
    signal_id: int,
) -> SignalOut:
    get_org_access(request, org_id)
    return signal_out(get_object_or_404(Signal, pk=signal_id, org_id=org_id))


@router.get(
    "/orgs/{org_id}/runs/{run_id}",
    auth=org_auth,
    response=RunOut,
)
def get_run(
    request: AuthenticatedRequest,
    org_id: int,
    run_id: int,
) -> RunOut:
    get_org_access(request, org_id)
    run = get_object_or_404(Run, pk=run_id, signal__org_id=org_id)
    result = None
    if run.result_status:
        if run.confidence is None:
            raise RuntimeError("completed run result is missing confidence")
        result = RunResultOut(
            status=run.result_status,
            pr_url=run.pr_url,
            summary=run.summary,
            confidence=run.confidence,
        )
    return RunOut(
        id=run.pk,
        signal_id=run.signal_id,
        state=run.state,
        result=result,
    )
