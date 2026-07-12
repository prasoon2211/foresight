import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from django.conf import settings

from executor import AgentMessage


def store_run_artifact(*, run_id: int, name: str, content: str) -> str:
    root = Path(settings.SESSION_EXPORT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"run-{run_id}-{name}"
    _atomic_write(destination, content)
    return str(destination)


def store_session_export(*, run_id: int, messages: Sequence[AgentMessage]) -> str:
    root = Path(settings.SESSION_EXPORT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"run-{run_id}.json"
    payload = {
        "run_id": run_id,
        "messages": [
            {
                "role": message.role,
                "text": message.text,
            }
            for message in messages
        ],
    }
    _atomic_write(destination, json.dumps(payload))
    return str(destination)


def _atomic_write(destination: Path, content: str) -> None:
    descriptor, temporary_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}-",
    )
    try:
        with os.fdopen(descriptor, "w") as export_file:
            export_file.write(content)
        os.replace(temporary_path, destination)
    except BaseException:
        Path(temporary_path).unlink(missing_ok=True)
        raise
