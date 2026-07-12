from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

from executor import DurableExecutor, FakeExecutor

_override: ContextVar[DurableExecutor | None] = ContextVar("executor_override", default=None)


def get_executor() -> DurableExecutor:
    override = _override.get()
    if override is not None:
        return override
    if settings.EXECUTOR_TYPE == "daytona":
        from executor.daytona import DaytonaExecutor

        return DaytonaExecutor()
    if settings.EXECUTOR_TYPE != "fake":
        raise RuntimeError(f"unsupported executor type: {settings.EXECUTOR_TYPE}")
    return FakeExecutor()


@contextmanager
def use_executor(executor: DurableExecutor) -> Iterator[None]:
    token = _override.set(executor)
    try:
        yield
    finally:
        _override.reset(token)
