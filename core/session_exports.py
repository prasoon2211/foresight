import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from django.conf import settings

from executor import AgentMessage


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
    descriptor, temporary_path = tempfile.mkstemp(dir=root, prefix=f".run-{run_id}-")
    try:
        with os.fdopen(descriptor, "w") as export_file:
            json.dump(payload, export_file)
        os.replace(temporary_path, destination)
    except BaseException:
        Path(temporary_path).unlink(missing_ok=True)
        raise
    return str(destination)
