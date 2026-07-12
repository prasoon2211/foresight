import uuid
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from core.models import (
    Repo,
    SetupVerificationStatus,
    SnapshotBuildStatus,
)
from executor import (
    DurableExecutor,
    EnvFile,
    Resources,
    SandboxSpec,
    SetupFailed,
    SnapshotBuildFailed,
    SnapshotSpec,
)
from executor.protocol import SETUP_LOG_PATH

SnapshotBuildEnqueuer = Callable[[int, str], object]

DEFAULT_RESOURCES = Resources(cpu=4, memory_gib=8, disk_gib=10)


@dataclass(frozen=True)
class SetupVerification:
    status: str
    output: str


def sandbox_spec_for_repo(repo: Repo, *, labels: dict[str, str]) -> SandboxSpec:
    return SandboxSpec(
        snapshot=repo.snapshot_id or repo.base_snapshot,
        env_files=[
            EnvFile(target_path=target_path, content=content)
            for target_path, content in repo.env.items()
        ],
        setup_script=repo.setup_script or None,
        labels={"managed_by": "foresight", "repo": repo.full_name, **labels},
        resources=DEFAULT_RESOURCES,
    )


def request_snapshot_build(
    *,
    repo: Repo,
    enqueue_build: SnapshotBuildEnqueuer,
) -> Repo:
    token = uuid.uuid4().hex
    with transaction.atomic():
        repo = Repo.objects.select_for_update().get(pk=repo.pk)
        repo.snapshot_build_status = SnapshotBuildStatus.BUILDING
        repo.snapshot_build_token = token
        repo.snapshot_build_output = ""
        repo.save(
            update_fields=[
                "snapshot_build_status",
                "snapshot_build_token",
                "snapshot_build_output",
            ]
        )
        enqueue_build(repo.pk, token)
    return repo


def build_repo_snapshot(
    *,
    repo_id: int,
    build_token: str,
    executor: DurableExecutor,
) -> None:
    repo = Repo.objects.get(pk=repo_id)
    if repo.snapshot_build_token != build_token:
        return
    spec = SnapshotSpec(
        name=f"foresight-repo-{repo.pk}-{build_token[:12]}",
        base_image=repo.base_snapshot,
        repo_url=f"https://github.com/{repo.full_name}.git",
        agent_version=settings.OPENCODE_VERSION,
        resources=DEFAULT_RESOURCES,
    )
    try:
        build = executor.build_snapshot(spec)
    except SnapshotBuildFailed as error:
        _finish_snapshot_build(
            repo_id=repo_id,
            build_token=build_token,
            status=SnapshotBuildStatus.FAILED,
            output=error.detail,
        )
        return
    except Exception as error:
        _finish_snapshot_build(
            repo_id=repo_id,
            build_token=build_token,
            status=SnapshotBuildStatus.FAILED,
            output=str(error),
        )
        return
    _finish_snapshot_build(
        repo_id=repo_id,
        build_token=build_token,
        status=SnapshotBuildStatus.READY,
        snapshot_id=build.snapshot_id,
        output=build.output,
    )


def _finish_snapshot_build(
    *,
    repo_id: int,
    build_token: str,
    status: SnapshotBuildStatus,
    output: str,
    snapshot_id: str = "",
) -> None:
    with transaction.atomic():
        repo = Repo.objects.select_for_update().get(pk=repo_id)
        if repo.snapshot_build_token != build_token:
            return
        repo.snapshot_build_status = status
        repo.snapshot_build_output = output
        if snapshot_id:
            repo.snapshot_id = snapshot_id
        repo.save(
            update_fields=[
                "snapshot_build_status",
                "snapshot_build_output",
                "snapshot_id",
            ]
        )


def verify_repo_setup(*, repo: Repo, executor: DurableExecutor) -> SetupVerification:
    if repo.snapshot_build_status != SnapshotBuildStatus.READY:
        return SetupVerification(
            status=SetupVerificationStatus.FAILED,
            output=f"repo snapshot is {repo.snapshot_build_status}",
        )
    try:
        handle = executor.create_sandbox(
            sandbox_spec_for_repo(repo, labels={"verify_setup": str(repo.pk)})
        )
    except SetupFailed as error:
        verification = SetupVerification(
            status=SetupVerificationStatus.FAILED,
            output=error.detail,
        )
    else:
        try:
            verification = SetupVerification(
                status=SetupVerificationStatus.SUCCESS,
                output=executor.read_file(handle, SETUP_LOG_PATH) or "",
            )
        finally:
            executor.destroy(handle)
    Repo.objects.filter(pk=repo.pk).update(
        setup_verification_status=verification.status,
        setup_verification_output=verification.output,
    )
    return verification
