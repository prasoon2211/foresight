import json
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse


class AllauthErrorHintMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if (
            not request.path.startswith("/_allauth/")
            or response.status_code < 400
            or not response.get("Content-Type", "").startswith("application/json")
        ):
            return response
        payload: dict[str, Any] = json.loads(response.content)
        errors = payload.get("errors")
        if not errors:
            return response
        first_error = errors[0]
        payload.update(
            code=first_error.get("code", "authentication_error"),
            message=first_error.get("message", "Authentication failed."),
            hint="Correct the supplied credentials or account details, then try again.",
        )
        response.content = json.dumps(payload)
        return response
