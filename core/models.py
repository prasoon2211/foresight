from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.fields.json import KeyTextTransform
from encrypted_fields.fields import EncryptedJSONField, EncryptedTextField

from core.harness import DEFAULT_HARNESS_PROMPT

DEFAULT_BASE_SNAPSHOT = "node:22-bookworm"


class IntakeState(models.TextChoices):
    RECEIVED = "received", "Received"
    DISPATCHED = "dispatched", "Dispatched"


class RunState(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROVISIONING = "provisioning", "Provisioning"
    RUNNING = "running", "Running"
    AWAITING_REVIEW = "awaiting_review", "Awaiting review"
    DONE = "done", "Done"
    FAILED = "failed", "Failed"


class SignalSource(models.TextChoices):
    MANUAL = "manual", "Manual"
    GITHUB_ISSUE = "github_issue", "GitHub issue"


class AgentRuntime(models.TextChoices):
    OPENCODE = "opencode", "OpenCode"


class ExecutorType(models.TextChoices):
    FAKE = "fake", "Fake"
    DAYTONA = "daytona", "Daytona"


class ResultStatus(models.TextChoices):
    PR_OPENED = "pr_opened", "PR opened"
    FAILED = "failed", "Failed"
    BLOCKED = "blocked", "Blocked"


class FailureReason(models.TextChoices):
    SETUP_FAILED = "setup_failed", "Setup failed"
    SANDBOX_DIED = "sandbox_died", "Sandbox died"
    AGENT_ERROR = "agent_error", "Agent error"
    AGENT_REPORTED_FAILED = "agent_reported_failed", "Agent reported failed"
    AGENT_REPORTED_BLOCKED = "agent_reported_blocked", "Agent reported blocked"
    NO_RESULT = "no_result", "No result"
    CANCELED = "canceled", "Canceled"


class SurfaceType(models.TextChoices):
    GITHUB = "github", "GitHub"


class SurfaceConnectionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"


class ConnectionStatus(models.TextChoices):
    CONNECTED = "connected", "Connected"
    DISCONNECTED = "disconnected", "Disconnected"


class SnapshotBuildStatus(models.TextChoices):
    BUILDING = "building", "Building"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class SetupVerificationStatus(models.TextChoices):
    NOT_RUN = "not_run", "Not run"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class Org(models.Model):
    name = models.CharField(max_length=200)
    agent_api_key = EncryptedTextField(blank=True, null=True)
    agent_base_url = EncryptedTextField(blank=True, null=True)
    concurrency_cap = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(concurrency_cap__gte=1),
                name="org_concurrency_cap_at_least_one",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def agent_credentials(self) -> dict[str, str]:
        credentials: dict[str, str] = {}
        if self.agent_api_key:
            credentials["ANTHROPIC_API_KEY"] = self.agent_api_key
        if self.agent_base_url:
            credentials["ANTHROPIC_BASE_URL"] = self.agent_base_url
        return credentials


class OrgMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="org_memberships",
    )
    role = models.CharField(max_length=20, choices=Role)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "user"],
                name="unique_org_membership",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.org}"


class ApiToken(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=200)
    prefix = models.CharField(max_length=12, unique=True)
    secret_hash = models.CharField(max_length=128)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_api_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.name} ({self.org})"


class SurfaceConnection(models.Model):
    org = models.ForeignKey(
        Org,
        on_delete=models.CASCADE,
        related_name="surface_connections",
    )
    type = models.CharField(max_length=30, choices=SurfaceType)
    status = models.CharField(
        max_length=20,
        choices=SurfaceConnectionStatus,
        default=SurfaceConnectionStatus.PENDING,
    )
    account_label = models.CharField(max_length=255)
    identity = models.JSONField(default=dict)
    credentials = EncryptedJSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                models.F("type"),
                KeyTextTransform("installation_id", "identity"),
                name="unique_surface_external_identity",
            )
        ]

    def __str__(self) -> str:
        return f"{self.type}: {self.account_label}"


class Repo(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="repos")
    surface_connection = models.ForeignKey(
        SurfaceConnection,
        on_delete=models.PROTECT,
        related_name="repos",
        null=True,
        blank=True,
    )
    full_name = models.CharField(max_length=255)
    default_branch = models.CharField(max_length=255, default="main")
    connection_status = models.CharField(
        max_length=20,
        choices=ConnectionStatus,
        default=ConnectionStatus.CONNECTED,
    )
    base_snapshot = models.CharField(max_length=500, default=DEFAULT_BASE_SNAPSHOT)
    setup_script = models.TextField(default="", blank=True)
    harness_prompt = models.TextField(default=DEFAULT_HARNESS_PROMPT)
    env = EncryptedJSONField(default=dict, blank=True)
    snapshot_build_status = models.CharField(
        max_length=20,
        choices=SnapshotBuildStatus,
        default=SnapshotBuildStatus.READY,
    )
    snapshot_id = models.CharField(max_length=255, blank=True)
    snapshot_build_token = models.CharField(max_length=32, blank=True)
    snapshot_build_output = models.TextField(blank=True)
    setup_verification_status = models.CharField(
        max_length=20,
        choices=SetupVerificationStatus,
        default=SetupVerificationStatus.NOT_RUN,
    )
    setup_verification_output = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "full_name"],
                name="unique_repo_full_name_per_org",
            )
        ]

    def __str__(self) -> str:
        return self.full_name


class Signal(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="signals")
    repo = models.ForeignKey(Repo, on_delete=models.PROTECT, related_name="signals")
    origin_connection = models.ForeignKey(
        SurfaceConnection,
        on_delete=models.PROTECT,
        related_name="origin_signals",
        null=True,
        blank=True,
    )
    origin_reference = models.JSONField(default=dict, blank=True)
    surface_state = models.JSONField(default=dict, blank=True)
    source = models.CharField(
        max_length=20,
        choices=SignalSource,
        default=SignalSource.MANUAL,
    )
    intake_state = models.CharField(
        max_length=20,
        choices=IntakeState,
        default=IntakeState.RECEIVED,
    )
    title = models.CharField(max_length=500)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.pk}: {self.title}"


class Run(models.Model):
    signal = models.ForeignKey(Signal, on_delete=models.CASCADE, related_name="runs")
    state = models.CharField(max_length=30, choices=RunState, default=RunState.QUEUED)
    agent_runtime = models.CharField(
        max_length=20,
        choices=AgentRuntime,
        default=AgentRuntime.OPENCODE,
    )
    executor_type = models.CharField(
        max_length=20,
        choices=ExecutorType,
        default=ExecutorType.FAKE,
    )
    sandbox_id = models.CharField(max_length=255, blank=True)
    agent_session_id = models.CharField(max_length=255, blank=True)
    agent_base_url = models.CharField(max_length=1000, blank=True)
    server_password = models.CharField(max_length=255, blank=True)
    branch_name = models.CharField(max_length=255, blank=True)
    result_status = models.CharField(max_length=30, choices=ResultStatus, blank=True)
    pr_url = models.URLField(max_length=500, blank=True)
    summary = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    pr_merged_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=40, choices=FailureReason, blank=True)
    failure_detail = models.TextField(blank=True)
    session_export_path = models.CharField(max_length=1000, blank=True)
    sandbox_archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["signal"],
                condition=models.Q(
                    state__in=[
                        RunState.QUEUED,
                        RunState.PROVISIONING,
                        RunState.RUNNING,
                        RunState.AWAITING_REVIEW,
                    ]
                ),
                name="one_active_run_per_signal",
            )
        ]

    def __str__(self) -> str:
        return f"Run {self.pk}"
