import json
from pathlib import Path
from typing import Any, cast

import pytest

from core.result_contract import ResultSource, resolve_result
from executor import AgentMessage, AgentResult, TranscriptUnavailable
from surfaces.github_client import FakeGitHubClient

FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"
FILE_RESULT = json.dumps(
    {
        "status": "blocked",
        "pr_url": None,
        "summary": "The environment is unavailable.",
        "confidence": 0.8,
    }
)


def load_transcript(name: str) -> list[AgentMessage]:
    raw_messages = cast(list[dict[str, Any]], json.loads((FIXTURES / name).read_text()))
    return [
        AgentMessage(
            role=str(message["info"]["role"]),
            text="".join(
                str(part["text"]) for part in message["parts"] if part.get("type") == "text"
            ),
        )
        for message in raw_messages
    ]


def unexpected_result_file_read() -> str | None:
    raise AssertionError("valid message result must not read the fallback file")


def unavailable_transcript() -> list[AgentMessage]:
    raise TranscriptUnavailable


def test_last_result_block_in_final_assistant_message_wins() -> None:
    github = FakeGitHubClient()
    result = resolve_result(
        read_transcript=lambda: load_transcript("result_block.json"),
        read_result_file=unexpected_result_file_read,
        find_open_pull_request=lambda: github.find_open_pull_request(
            123,
            "acme/widgets",
            "foresight/signal-1-run-1",
        ),
    )

    assert result.result == AgentResult(
        status="pr_opened",
        pr_url="https://github.com/acme/widgets/pull/17",
        summary="Fixed the widget race; full suite passes.",
        confidence=0.92,
    )
    assert result.source == ResultSource.MESSAGE
    assert github.pull_request_lookups == []


def test_malformed_result_block_falls_through_to_result_file() -> None:
    result = resolve_result(
        read_transcript=lambda: load_transcript("malformed_result_block.json"),
        read_result_file=lambda: FILE_RESULT,
        find_open_pull_request=lambda: None,
    )

    assert result.result == AgentResult(
        status="blocked",
        pr_url=None,
        summary="The environment is unavailable.",
        confidence=0.8,
    )
    assert result.source == ResultSource.FILE


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {
            "status": "unknown",
            "pr_url": None,
            "summary": "Unknown status.",
            "confidence": 0.5,
        },
        {
            "status": "pr_opened",
            "pr_url": "not a URI",
            "summary": "Bad URL.",
            "confidence": 0.5,
        },
        {
            "status": "pr_opened",
            "pr_url": "https://github.com/acme/widgets/pull/17 bad",
            "summary": "Malformed URL.",
            "confidence": 0.5,
        },
        {
            "status": "pr_opened",
            "pr_url": "https://[foo]/pull/17",
            "summary": "Malformed IPv6 host.",
            "confidence": 0.5,
        },
        {
            "status": "failed",
            "pr_url": None,
            "summary": "",
            "confidence": 0.5,
        },
        {
            "status": "failed",
            "pr_url": None,
            "summary": "Bad confidence.",
            "confidence": 1.1,
        },
        {
            "status": "failed",
            "pr_url": None,
            "summary": "Unexpected property.",
            "confidence": 0.5,
            "extra": True,
        },
    ],
)
def test_schema_invalid_blocks_fall_through_to_result_file(
    invalid_payload: dict[str, object],
) -> None:
    transcript = [
        AgentMessage(
            role="assistant",
            text=f"```foresight-result\n{json.dumps(invalid_payload)}\n```",
        )
    ]

    result = resolve_result(
        read_transcript=lambda: transcript,
        read_result_file=lambda: FILE_RESULT,
        find_open_pull_request=lambda: None,
    )

    assert result.result.status == "blocked"


def test_missing_channels_salvage_an_open_pull_request_from_the_run_branch() -> None:
    branch_name = "foresight/signal-1-run-1"
    pr_url = "https://github.com/acme/widgets/pull/17"
    github = FakeGitHubClient(
        open_pull_requests={("acme/widgets", branch_name): pr_url},
    )

    result = resolve_result(
        read_transcript=list,
        read_result_file=lambda: None,
        find_open_pull_request=lambda: github.find_open_pull_request(
            123,
            "acme/widgets",
            branch_name,
        ),
    )

    assert result.result == AgentResult(
        status="pr_opened",
        pr_url=pr_url,
        summary="Agent reporting failed; found an open pull request for the run branch.",
        confidence=0,
    )
    assert result.source == ResultSource.GITHUB
    assert github.pull_request_lookups == [(123, "acme/widgets", branch_name)]


def test_every_missing_channel_synthesizes_zero_confidence_failure() -> None:
    result = resolve_result(
        read_transcript=list,
        read_result_file=lambda: None,
        find_open_pull_request=lambda: None,
    )

    assert result.result == AgentResult(
        status="failed",
        pr_url=None,
        summary="Run produced no parseable result.",
        confidence=0,
    )
    assert result.source == ResultSource.SYNTHESIZED


def test_unreadable_transcript_falls_through_to_result_file() -> None:
    result = resolve_result(
        read_transcript=unavailable_transcript,
        read_result_file=lambda: FILE_RESULT,
        find_open_pull_request=lambda: None,
    )

    assert result.source == ResultSource.FILE


@pytest.mark.parametrize(
    "pr_uri",
    ["urn:example:pull-request:17", "file:///tmp/pull-request"],
)
def test_schema_accepts_an_absolute_non_http_uri(pr_uri: str) -> None:
    transcript = [
        AgentMessage(
            role="assistant",
            text=(
                "```foresight-result\n"
                f'{{"status":"pr_opened","pr_url":"{pr_uri}",'
                '"summary":"Opened the pull request.","confidence":0.9}\n'
                "```"
            ),
        )
    ]

    result = resolve_result(
        read_transcript=lambda: transcript,
        read_result_file=unexpected_result_file_read,
        find_open_pull_request=lambda: None,
    )

    assert result.source == ResultSource.MESSAGE
    assert result.result.pr_url == pr_uri
