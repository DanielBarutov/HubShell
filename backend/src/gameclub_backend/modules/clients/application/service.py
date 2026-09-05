import dataclasses
import datetime
import hashlib
import secrets
import uuid
from collections.abc import Mapping, Sequence

from gameclub_backend.application.errors import ApplicationError, ErrorCode
from gameclub_backend.modules.clients.application.ports import ClientRepository, Clock
from gameclub_backend.modules.clients.domain import (
    BalanceOperation,
    BalanceOperationType,
    Client,
    Nickname,
    PhoneNumber,
    normalize_phone,
)
from gameclub_backend.modules.payment_methods.domain import PaymentPart, normalize_payment_parts


class UtcClock:
    def now(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC)


class ClientService:
    def __init__(self, repository: ClientRepository, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or UtcClock()

    async def create(
        self,
        nickname: str,
        phone: str | None = None,
        discount_category: str | None = None,
    ) -> Client:
        try:
            normalized_nickname = Nickname(nickname).value
        except ValueError as error:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                str(error),
            ) from error
        try:
            normalized_phone = PhoneNumber(phone).value if phone else None
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error

        now = self._clock.now()
        client = Client(
            id=uuid.uuid4(),
            nickname=normalized_nickname,
            phone=normalized_phone or None,
            discount_category=discount_category,
            balance_cents=0,
            balance_bonus=0,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.save(client)

    async def register_portal(
        self,
        nickname: str,
        phone: str,
        password: str,
    ) -> Client:
        normalized_nickname = nickname.strip()
        normalized_phone = phone.strip()
        self._validate_portal_password(password)
        try:
            Nickname(normalized_nickname)
            canonical_phone = PhoneNumber(normalized_phone).value
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        if await self._repository.get_by_nickname(normalized_nickname) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Nickname is already registered")
        if await self._repository.get_by_phone(canonical_phone) is not None:
            raise ApplicationError(ErrorCode.CONFLICT, "Phone is already registered")

        now = self._clock.now()
        client = Client(
            id=uuid.uuid4(),
            nickname=normalized_nickname,
            phone=canonical_phone,
            discount_category=None,
            balance_cents=0,
            balance_bonus=0,
            created_at=now,
            updated_at=now,
            password_hash=self._hash_password(password),
        )
        return await self._repository.save(client)

    async def authenticate_portal(self, identifier: str, password: str) -> Client:
        self._validate_portal_password(password)
        normalized_identifier = identifier.strip()
        if not normalized_identifier:
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid client credentials")
        client = await self._repository.get_by_nickname(normalized_identifier)
        if client is None:
            canonical_phone = normalize_phone(normalized_identifier)
            if len(canonical_phone) == 11 and canonical_phone.startswith("7"):
                client = await self._repository.get_by_phone(canonical_phone)
        if (
            client is None
            or client.blocked_at is not None
            or not self._verify_password(password, client.password_hash)
        ):
            raise ApplicationError(ErrorCode.UNAUTHENTICATED, "Invalid client credentials")
        return client

    async def update(
        self,
        client_id: uuid.UUID,
        nickname: str,
        phone: str | None = None,
        discount_category: str | None = None,
    ) -> Client:
        client = await self.get(client_id)
        try:
            normalized_nickname = Nickname(nickname).value
            normalized_phone = PhoneNumber(phone).value if phone else None
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        return await self._repository.save(
            dataclasses.replace(
                client,
                nickname=normalized_nickname,
                phone=normalized_phone or None,
                discount_category=discount_category.strip() if discount_category else None,
                updated_at=self._clock.now(),
            )
        )

    async def delete(self, client_id: uuid.UUID) -> None:
        client = await self.get(client_id)
        await self._repository.save(dataclasses.replace(client, blocked_at=self._clock.now()))

    async def reset_password(self, client_id: uuid.UUID) -> str:
        client = await self.get(client_id)
        temporary_password = secrets.token_urlsafe(9)
        password_hash = self._hash_password(temporary_password)
        await self._repository.save(
            dataclasses.replace(
                client,
                password_hash=password_hash,
                updated_at=self._clock.now(),
            )
        )
        return temporary_password

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )
        return f"scrypt${salt.hex()}${digest.hex()}"

    @staticmethod
    def _verify_password(password: str, encoded: str | None) -> bool:
        if not encoded or not encoded.startswith("scrypt$"):
            return False
        try:
            _, salt_hex, digest_hex = encoded.split("$", maxsplit=2)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=2**14,
                r=8,
                p=1,
            )
        except (TypeError, ValueError):
            return False
        return secrets.compare_digest(actual, expected)

    @staticmethod
    def _validate_portal_password(password: str) -> None:
        if not password.strip() or not 4 <= len(password) <= 128:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Password must contain from 4 to 128 characters",
            )

    async def search(self, query: str, field: str) -> list[Client]:
        normalized_query = query.strip().lower()
        if field not in {"nickname", "phone"}:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Search field must be nickname or phone",
            )
        if field == "nickname" and len(normalized_query) < 3:
            raise ApplicationError(
                ErrorCode.INVALID_ARGUMENT,
                "Nickname search starts at 3 characters",
            )
        if field == "phone":
            normalized_query = normalize_phone(normalized_query)
            if len(normalized_query) < 4:
                raise ApplicationError(
                    ErrorCode.INVALID_ARGUMENT,
                    "Phone search starts at 4 digits",
                )
        return await self._repository.search(normalized_query, field)

    async def list_clients(self) -> list[Client]:
        return await self._repository.list_clients()

    async def get(self, client_id: uuid.UUID) -> Client:
        client = await self._repository.get(client_id)
        if client is None:
            raise ApplicationError(ErrorCode.NOT_FOUND, "Client not found")
        return client

    async def list_operations(
        self,
        client_id: uuid.UUID,
        limit: int = 50,
    ) -> list[BalanceOperation]:
        await self.get(client_id)
        bounded_limit = max(1, min(limit, 100))
        return await self._repository.list_operations(client_id, bounded_limit)

    async def top_up(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        bonus_amount: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
        payment_parts: Sequence[PaymentPart | Mapping[str, object]] | None = None,
    ) -> tuple[Client, BalanceOperation]:
        normalized_key = self._required_idempotency_key(idempotency_key)
        normalized_reason = reason.strip()
        normalized_actor = actor_id.strip()
        try:
            normalized_parts = normalize_payment_parts(payment_parts, amount_cents)
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        existing = await self._repository.get_operation_by_key(normalized_key)
        if existing is not None:
            self._validate_existing_operation(
                existing,
                client_id=client_id,
                amount_cents=amount_cents,
                bonus_amount=bonus_amount,
                reason=normalized_reason,
                actor_id=normalized_actor,
                operation_type=BalanceOperationType.TOP_UP,
                payment_parts=normalized_parts,
            )
            return await self.get(client_id), existing
        client = await self.get(client_id)
        try:
            updated = client.top_up(amount_cents, bonus_amount, self._clock.now())
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            operation = BalanceOperation(
                id=uuid.uuid4(),
                client_id=client_id,
                amount_cents=amount_cents,
                bonus_amount=bonus_amount,
                reason=normalized_reason,
                actor_id=normalized_actor,
                idempotency_key=normalized_key,
                created_at=self._clock.now(),
                operation_type=BalanceOperationType.TOP_UP,
                payment_parts=normalized_parts,
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            applied_client, applied_operation = await self._repository.apply_balance_operation(
                updated,
                operation,
            )
        except ValueError as error:
            error_code = ErrorCode.CONFLICT if "Idempotency" in str(error) else ErrorCode.NOT_FOUND
            raise ApplicationError(error_code, str(error)) from error
        self._validate_existing_operation(
            applied_operation,
            client_id=client_id,
            amount_cents=amount_cents,
            bonus_amount=bonus_amount,
            reason=normalized_reason,
            actor_id=normalized_actor,
            operation_type=BalanceOperationType.TOP_UP,
            payment_parts=normalized_parts,
        )
        return applied_client, applied_operation

    async def debit(
        self,
        client_id: uuid.UUID,
        amount_cents: int,
        reason: str,
        actor_id: str,
        idempotency_key: str,
    ) -> tuple[Client, BalanceOperation]:
        normalized_key = self._required_idempotency_key(idempotency_key)
        normalized_reason = reason.strip()
        normalized_actor = actor_id.strip()
        existing = await self._repository.get_operation_by_key(normalized_key)
        if existing is not None:
            self._validate_existing_operation(
                existing,
                client_id=client_id,
                amount_cents=-amount_cents,
                bonus_amount=0,
                reason=normalized_reason,
                actor_id=normalized_actor,
                operation_type=BalanceOperationType.DEBIT,
                payment_parts=(),
            )
            return await self.get(client_id), existing
        client = await self.get(client_id)
        try:
            updated = client.debit(amount_cents, self._clock.now())
        except ValueError as error:
            raise ApplicationError(ErrorCode.CONFLICT, str(error)) from error
        try:
            operation = BalanceOperation(
                id=uuid.uuid4(),
                client_id=client_id,
                amount_cents=-amount_cents,
                bonus_amount=0,
                reason=normalized_reason,
                actor_id=normalized_actor,
                idempotency_key=normalized_key,
                created_at=self._clock.now(),
                operation_type=BalanceOperationType.DEBIT,
                payment_parts=(),
            )
        except ValueError as error:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, str(error)) from error
        try:
            applied_client, applied_operation = await self._repository.apply_balance_operation(
                updated,
                operation,
            )
        except ValueError as error:
            message = str(error)
            raise ApplicationError(ErrorCode.CONFLICT, message) from error
        self._validate_existing_operation(
            applied_operation,
            client_id=client_id,
            amount_cents=-amount_cents,
            bonus_amount=0,
            reason=normalized_reason,
            actor_id=normalized_actor,
            operation_type=BalanceOperationType.DEBIT,
            payment_parts=(),
        )
        return applied_client, applied_operation

    @staticmethod
    def _required_idempotency_key(value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 128:
            raise ApplicationError(ErrorCode.INVALID_ARGUMENT, "Idempotency key is required")
        return normalized

    @staticmethod
    def _validate_existing_operation(
        operation: BalanceOperation,
        *,
        client_id: uuid.UUID,
        amount_cents: int,
        bonus_amount: int,
        reason: str,
        actor_id: str,
        operation_type: BalanceOperationType,
        payment_parts: tuple[PaymentPart, ...] = (),
    ) -> None:
        if operation.client_id != client_id:
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another client",
            )
        if (
            operation.operation_type is not operation_type
            or operation.amount_cents != amount_cents
            or operation.bonus_amount != bonus_amount
            or operation.reason != reason
            or operation.actor_id != actor_id
            or operation.payment_parts != payment_parts
        ):
            raise ApplicationError(
                ErrorCode.CONFLICT,
                "Idempotency key belongs to another balance operation",
            )
