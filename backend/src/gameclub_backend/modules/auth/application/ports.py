import datetime
import typing

from gameclub_backend.modules.auth.domain import Principal, RefreshTokenRecord


class TokenService(typing.Protocol):
    def issue_access_token(self, principal: Principal) -> tuple[str, int]:
        """Issue an access token and return it with its lifetime in seconds."""

    def validate_access_token(self, token: str) -> Principal:
        """Validate a token and return its principal."""


class RefreshTokenRepository(typing.Protocol):
    async def save(
        self,
        token_hash: str,
        principal: Principal,
        expires_at: datetime.datetime,
    ) -> None:
        """Store a refresh token hash until its expiration."""

    async def consume(
        self,
        token_hash: str,
        now: datetime.datetime,
    ) -> RefreshTokenRecord | None:
        """Atomically consume a refresh token for rotation."""

    async def revoke(self, token_hash: str) -> None:
        """Revoke a refresh token hash."""
