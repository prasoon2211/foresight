from datetime import datetime
from typing import Literal

from ninja import Field, Schema


class OrgCreateIn(Schema):
    name: str


class OrgOut(Schema):
    id: int
    name: str
    concurrency_cap: int
    role: str


class OrgMemberIn(Schema):
    email: str
    role: Literal["admin", "member"]


class OrgMemberOut(Schema):
    user_id: int
    email: str
    role: str


class AgentCredentialIn(Schema):
    api_key: str = Field(min_length=1)
    base_url: str = ""


class OrgSettingsIn(Schema):
    agent_credential: AgentCredentialIn | None = None
    concurrency_cap: int | None = Field(default=None, ge=1)


class OrgSettingsOut(Schema):
    id: int
    name: str
    concurrency_cap: int
    has_agent_credential: bool


class RepoSettingsIn(Schema):
    env: dict[str, str]


class RepoOut(Schema):
    id: int
    full_name: str
    default_branch: str
    has_env: bool


class ApiTokenCreateIn(Schema):
    name: str = Field(min_length=1, max_length=200)


class ApiTokenCreatedOut(Schema):
    id: int
    name: str
    prefix: str
    token: str
    created_at: datetime


class ApiTokenOut(Schema):
    id: int
    name: str
    prefix: str
    created_at: datetime
    revoked_at: datetime | None


class ManualSignalIn(Schema):
    repo_id: int
    title: str
    body: str


class CreatedSignalOut(Schema):
    id: int
    run_id: int
    intake_state: str


class SignalOut(Schema):
    id: int
    repo_id: int
    source: str
    title: str
    body: str
    intake_state: str
    outcome_status: str
    stranded: bool


class RunResultOut(Schema):
    status: str
    pr_url: str
    summary: str
    confidence: float


class RunOut(Schema):
    id: int
    signal_id: int
    state: str
    result: RunResultOut | None
