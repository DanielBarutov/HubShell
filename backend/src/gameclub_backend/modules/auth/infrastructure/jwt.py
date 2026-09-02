import datetime
import secrets

import jwt

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType


class InvalidTokenError(ValueError):
    """Raised when a JWT cannot be trusted."""


class JwtTokenService:
    def __init__(self, settings: Settings) -> None:
        if not settings.jwt_secret:
            raise ValueError("GAMECLUB_JWT_SECRET is required for JWT operations")
        self._settings = settings

    def issue_access_token(self, principal: Principal) -> tuple[str, int]:
        now = datetime.datetime.now(datetime.UTC)
        expires_at = now + datetime.timedelta(seconds=self._settings.jwt_access_ttl_seconds)
        payload = {
            "sub": principal.subject_id,
            "subject_type": principal.subject_type.value,
            "roles": sorted(principal.roles),
            "permissions": sorted(principal.permissions),
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "iat": now,
            "exp": expires_at,
            "jti": secrets.token_urlsafe(16),
        }
        if principal.device_id:
            payload["device_id"] = principal.device_id
        token = jwt.encode(payload, self._settings.jwt_secret, algorithm="HS256")
        return token, self._settings.jwt_access_ttl_seconds

    def validate_access_token(self, token: str) -> Principal:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                options={"require": ["sub", "subject_type", "iat", "exp", "jti"]},
            )
        except jwt.PyJWTError as error:
            raise InvalidTokenError("Invalid access token") from error

        try:
            subject_type = SubjectType(payload["subject_type"])
            subject_id = str(payload["sub"])
            roles = frozenset(str(role) for role in payload.get("roles", []))
            permissions = frozenset(
                str(permission) for permission in payload.get("permissions", [])
            )
        except (KeyError, TypeError, ValueError) as error:
            raise InvalidTokenError("Invalid access token claims") from error

        return Principal(
            subject_id=subject_id,
            subject_type=subject_type,
            roles=roles,
            permissions=permissions,
            device_id=(str(payload["device_id"]) if payload.get("device_id") else None),
        )
