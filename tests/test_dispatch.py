import pytest

from core.intake import create_manual_signal
from core.models import Org, Repo, Run, Signal


class QueueUnavailable(Exception):
    pass


@pytest.mark.django_db(transaction=True)
def test_manual_signal_dispatch_rolls_back_when_enqueue_fails() -> None:
    org = Org.objects.create(name="Acme")
    repo = Repo.objects.create(org=org, full_name="acme/widgets")

    def fail_to_enqueue(run_id: int) -> object:
        raise QueueUnavailable

    with pytest.raises(QueueUnavailable):
        create_manual_signal(
            repo=repo,
            title="Fix widget race",
            body="Two updates can overwrite one another.",
            enqueue_run=fail_to_enqueue,
        )

    assert not Signal.objects.exists()
    assert not Run.objects.exists()
