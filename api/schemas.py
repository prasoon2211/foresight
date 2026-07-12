from ninja import Schema


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
