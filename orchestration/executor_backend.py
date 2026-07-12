from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from executor import DurableExecutor, FakeExecutor

_override: ContextVar[DurableExecutor | None] = ContextVar("executor_override", default=None)


def get_executor() -> DurableExecutor:
    return _override.get() or FakeExecutor()


@contextmanager
def use_executor(executor: DurableExecutor) -> Iterator[None]:
    token = _override.set(executor)
    try:
        yield
    finally:
        _override.reset(token)
