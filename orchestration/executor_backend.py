from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from executor import Executor, FakeExecutor

_default_executor = FakeExecutor()
_override: ContextVar[Executor | None] = ContextVar("executor_override", default=None)


def get_executor() -> Executor:
    return _override.get() or _default_executor


@contextmanager
def use_executor(executor: Executor) -> Iterator[None]:
    token = _override.set(executor)
    try:
        yield
    finally:
        _override.reset(token)
