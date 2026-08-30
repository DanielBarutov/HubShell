import dataclasses
import enum


class ErrorCode(enum.StrEnum):
    INVALID_ARGUMENT = "invalid_argument"
    UNAUTHENTICATED = "unauthenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL = "internal"


@dataclasses.dataclass
class ApplicationError(Exception):
    code: ErrorCode
    message: str

    def __str__(self) -> str:
        return self.message
