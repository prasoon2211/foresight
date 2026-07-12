from core.models import Repo


def update_repo_env(*, repo: Repo, env: dict[str, str]) -> Repo:
    repo.env = env
    repo.save(update_fields=["env"])
    return repo
