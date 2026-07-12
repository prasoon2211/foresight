import re
from pathlib import Path
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from core.models import Run


DEFAULT_HARNESS_PROMPT = (
    Path(__file__).with_name("default_harness_prompt.md").read_text().rstrip("\n") + "\n"
)
PROMPT_VARIABLE = re.compile(
    r"\{\{(signal_title|signal_body|signal_origin_url|repo_full_name|default_branch|branch_name)\}\}"
)


def render_harness_prompt(run: "Run") -> str:
    """Render the repo-owned prompt by replacing the six contract variables."""
    signal = run.signal
    repo = signal.repo
    origin_url = signal.origin_reference.get("url") or (
        f"{settings.PUBLIC_BASE_URL}/orgs/{signal.org_id}/signals/{signal.pk}"
    )
    variables = {
        "signal_title": signal.title,
        "signal_body": signal.body,
        "signal_origin_url": origin_url,
        "repo_full_name": repo.full_name,
        "default_branch": repo.default_branch,
        "branch_name": run.branch_name,
    }
    return PROMPT_VARIABLE.sub(lambda match: variables[match.group(1)], repo.harness_prompt)
