from core.models import Signal, SurfaceType
from surfaces.github import GitHubSurfaceAdapter
from surfaces.github_client import get_github_client
from surfaces.protocol import SurfaceAdapter


def surface_adapter_for(signal: Signal) -> SurfaceAdapter | None:
    connection = signal.origin_connection
    if connection is None:
        return None
    if connection.type == SurfaceType.GITHUB:
        return GitHubSurfaceAdapter(get_github_client())
    raise ValueError(f"unsupported surface type: {connection.type}")
