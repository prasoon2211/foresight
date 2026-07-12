import pytest
from django.db import IntegrityError, transaction

from core.models import Org, Repo, Run, RunState, Signal


@pytest.mark.django_db
def test_database_rejects_a_second_active_run_for_one_signal() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")
    signal = Signal.objects.create(
        org=org,
        repo=repo,
        title="Fix widget",
        body="The widget is broken.",
    )
    Run.objects.create(signal=signal)

    with pytest.raises(IntegrityError), transaction.atomic():
        Run.objects.create(signal=signal)

    Run.objects.update(state=RunState.FAILED)
    replacement = Run.objects.create(signal=signal)
    assert replacement.state == RunState.QUEUED
