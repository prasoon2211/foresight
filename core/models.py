from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from encrypted_fields.fields import EncryptedJSONField, EncryptedTextField


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


class Org(models.Model):
    name = models.CharField(max_length=200)
    agent_api_key = EncryptedTextField(blank=True, null=True)
    agent_base_url = EncryptedTextField(blank=True, null=True)
    concurrency_cap = models.PositiveIntegerField(
        default=3,
        validators=[MinValueValidator(1)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


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


class Repo(models.Model):
    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="repos")
    full_name = models.CharField(max_length=255)
    default_branch = models.CharField(max_length=255, default="main")
    env = EncryptedJSONField(default=dict, blank=True)
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
