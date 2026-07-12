import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from executor import AgentMessage


class SessionExportUnavailable(Exception):
    pass


@dataclass(frozen=True)
class TranscriptMessage:
    role: str
    text: str


@dataclass(frozen=True)
class SessionTranscript:
    run_id: int
    messages: list[TranscriptMessage]


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


def load_session_export(*, run_id: int, path: str) -> SessionTranscript:
    try:
        payload = json.loads(Path(path).read_text())
        exported_run_id = payload["run_id"]
        raw_messages = payload["messages"]
        if exported_run_id != run_id or not isinstance(raw_messages, list):
            raise ValueError
        messages = [
            TranscriptMessage(role=str(message["role"]), text=str(message["text"]))
            for message in raw_messages
        ]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise SessionExportUnavailable from error
    return SessionTranscript(run_id=exported_run_id, messages=messages)


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
