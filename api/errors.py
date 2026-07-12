from dataclasses import dataclass

from ninja import Schema


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
