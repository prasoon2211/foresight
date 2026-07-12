from django.http import Http404, HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from ninja import NinjaAPI, Schema
from ninja.errors import AuthenticationError, HttpError, ValidationError

from api.errors import ApiError, ApiErrorOut
from api.routes import router

api = NinjaAPI(title="Foresight API", version="1.0.0")
api.add_router("", router)


def error_response(
    request: HttpRequest,
    status_code: int,
    code: str,
    message: str,
    hint: str,
) -> HttpResponse:
    return api.create_response(
        request,
        ApiErrorOut(code=code, message=message, hint=hint),
        status=status_code,
    )


@api.exception_handler(ApiError)
def handle_api_error(request: HttpRequest, exc: ApiError) -> HttpResponse:
    return error_response(
        request,
        exc.status_code,
        exc.code,
        exc.message,
        exc.hint,
    )


@api.exception_handler(AuthenticationError)
def handle_authentication_error(
    request: HttpRequest,
    exc: AuthenticationError,
) -> HttpResponse:
    return error_response(
        request,
        401,
        "unauthorized",
        "Authentication required.",
        "Use a session cookie or a valid org API token.",
    )


@api.exception_handler(Http404)
def handle_not_found(request: HttpRequest, exc: Http404) -> HttpResponse:
    return error_response(
        request,
        404,
        "not_found",
        "The requested resource was not found.",
        "Check the resource ID and org, then try again.",
    )


@api.exception_handler(ValidationError)
def handle_validation_error(
    request: HttpRequest,
    exc: ValidationError,
) -> HttpResponse:
    return error_response(
        request,
        422,
        "invalid_request",
        "The request could not be validated.",
        "Check the documented fields and values, then try again.",
    )


@api.exception_handler(HttpError)
def handle_http_error(request: HttpRequest, exc: HttpError) -> HttpResponse:
    return error_response(
        request,
        exc.status_code,
        "request_rejected",
        str(exc),
        "Correct the request and try again.",
    )


class HealthResponse(Schema):
    status: str


class CsrfResponse(Schema):
    csrf_token: str


@api.get("/csrf", response=CsrfResponse, tags=["system"])
def csrf(request: HttpRequest) -> CsrfResponse:
    return CsrfResponse(csrf_token=get_token(request))


@api.get("/health", response=HealthResponse, tags=["system"])
def health(request: object) -> HealthResponse:
    return HealthResponse(status="ok")


__all__ = ["api"]
