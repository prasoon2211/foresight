import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from jsonschema import Draft7Validator, FormatChecker

from executor import AgentMessage, AgentResult, TranscriptUnavailable

RESULT_BLOCK = re.compile(r"```foresight-result\s*\n(.*?)\n```", re.DOTALL)
RESULT_STATUSES = {"pr_opened", "failed", "blocked"}
RESULT_SCHEMA: dict[str, object] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["status", "pr_url", "summary", "confidence"],
    "additionalProperties": False,
    "properties": {
        "status": {"enum": sorted(RESULT_STATUSES)},
        "pr_url": {"type": ["string", "null"], "format": "uri"},
        "summary": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
RESULT_VALIDATOR = Draft7Validator(RESULT_SCHEMA, format_checker=FormatChecker())
NO_RESULT = AgentResult(
    status="failed",
    pr_url=None,
    summary="Run produced no parseable result.",
    confidence=0,
)


class ResultSource(StrEnum):
    MESSAGE = "message"
    FILE = "file"
    GITHUB = "github"
    SYNTHESIZED = "synthesized"


@dataclass(frozen=True)
class ResolvedResult:
    result: AgentResult
    source: ResultSource


def resolve_result(
    *,
    read_transcript: Callable[[], list[AgentMessage]],
    read_result_file: Callable[[], str | None],
    find_open_pull_request: Callable[[], str | None],
) -> ResolvedResult:
    """Resolve a run result through the contract's ordered reporting channels."""
    try:
        transcript = read_transcript()
    except TranscriptUnavailable:
        transcript = []
    message_result = _result_from_final_assistant_message(transcript)
    if message_result is not None:
        return ResolvedResult(message_result, ResultSource.MESSAGE)

    file_result = _parse_result(read_result_file())
    if file_result is not None:
        return ResolvedResult(file_result, ResultSource.FILE)

    pr_url = find_open_pull_request()
    if pr_url is not None:
        return ResolvedResult(
            AgentResult(
                status="pr_opened",
                pr_url=pr_url,
                summary=("Agent reporting failed; found an open pull request for the run branch."),
                confidence=0,
            ),
            ResultSource.GITHUB,
        )

    return ResolvedResult(NO_RESULT, ResultSource.SYNTHESIZED)


def _result_from_final_assistant_message(transcript: list[AgentMessage]) -> AgentResult | None:
    for message in reversed(transcript):
        if message.role != "assistant":
            continue
        matches = RESULT_BLOCK.findall(message.text)
        return _parse_result(matches[-1]) if matches else None
    return None


def _parse_result(raw: str | None) -> AgentResult | None:
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or not RESULT_VALIDATOR.is_valid(payload):
        return None

    status = payload["status"]
    pr_url = payload["pr_url"]
    summary = payload["summary"]
    confidence = payload["confidence"]
    assert isinstance(status, str)
    assert pr_url is None or isinstance(pr_url, str)
    assert isinstance(summary, str)
    assert isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
    if status == "pr_opened" and pr_url is None:
        return None
    if status != "pr_opened" and pr_url is not None:
        return None
    return AgentResult(
        status=status,
        pr_url=pr_url,
        summary=summary,
        confidence=float(confidence),
    )
