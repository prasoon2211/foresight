from dataclasses import dataclass

from ninja import Schema

API_ERROR_STATUSES = frozenset({400, 401, 403, 404, 409, 422})


class ApiErrorOut(Schema):
    code: str
    message: str
    hint: str


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    hint: str
