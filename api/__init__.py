from ninja import NinjaAPI, Schema

api = NinjaAPI(title="Foresight API", version="1.0.0")


class HealthResponse(Schema):
    status: str


@api.get("/health", response=HealthResponse, tags=["system"])
def health(request: object) -> HealthResponse:
    return HealthResponse(status="ok")


__all__ = ["api"]
