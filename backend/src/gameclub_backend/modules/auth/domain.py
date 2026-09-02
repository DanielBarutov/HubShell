import dataclasses
import datetime
import enum


class SubjectType(enum.StrEnum):
    OPERATOR = "operator"
    DEVICE = "device"
    CLIENT = "client"


@dataclasses.dataclass(frozen=True)
class Principal:
    subject_id: str
    subject_type: SubjectType
    roles: frozenset[str]
    permissions: frozenset[str]
    device_id: str | None = None

    def can(self, permission: str) -> bool:
        return permission in self.permissions or "*" in self.permissions


@dataclasses.dataclass(frozen=True)
class RefreshTokenRecord:
    principal: Principal
    expires_at: datetime.datetime
