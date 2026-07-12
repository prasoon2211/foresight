from typing import Protocol

from core.models import Run


class SurfaceAdapter(Protocol):
    def notify_run_started(self, run: Run) -> None: ...

    def notify_run_finished(self, run: Run) -> None: ...
