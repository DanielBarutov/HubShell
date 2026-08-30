import typing
import uuid

from fastapi import APIRouter, Depends, Header, Query, status
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.domain import Principal
from gameclub_backend.modules.clients.application.guests import GuestService
from gameclub_backend.modules.clients.application.service import ClientService
from gameclub_backend.modules.clients.domain import BalanceOperation, Client, Guest
from gameclub_backend.presentation.http.auth import require_permissions

Operator = typing.Annotated[Principal, Depends(require_permissions("clients.manage"))]


class CreateClientRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    discount_category: str | None = Field(default=None, max_length=64)


class UpdateClientRequest(CreateClientRequest):
    pass


class ResetPasswordResponse(BaseModel):
    temporary_password: str


class TopUpRequest(BaseModel):
    amount_cents: int = Field(default=0, ge=0)
    bonus_amount: int = Field(default=0, ge=0)
    reason: str = Field(min_length=1, max_length=255)


class ClientResponse(BaseModel):
    id: uuid.UUID
    nickname: str
    phone: str | None
    discount_category: str | None
    balance_cents: int
    balance_bonus: int
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, client: Client) -> "ClientResponse":
        return cls(
            id=client.id,
            nickname=client.nickname,
            phone=client.phone,
            discount_category=client.discount_category,
            balance_cents=client.balance_cents,
            balance_bonus=client.balance_bonus,
            created_at=client.created_at.isoformat(),
            updated_at=client.updated_at.isoformat(),
        )


class CreateGuestRequest(BaseModel):
    nickname: str = Field(min_length=3, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    discount_category: str | None = Field(default=None, max_length=64)


class GuestResponse(BaseModel):
    id: uuid.UUID
    nickname: str
    phone: str | None
    discount_category: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, guest: Guest) -> "GuestResponse":
        return cls(
            id=guest.id,
            nickname=guest.nickname,
            phone=guest.phone,
            discount_category=guest.discount_category,
            created_at=guest.created_at.isoformat(),
            updated_at=guest.updated_at.isoformat(),
        )


class TopUpResponse(BaseModel):
    client: ClientResponse
    operation_id: uuid.UUID
    idempotency_key: str


class BalanceOperationResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    operation_type: str
    amount_cents: int
    bonus_amount: int
    reason: str
    actor_id: str
    idempotency_key: str
    created_at: str

    @classmethod
    def from_domain(cls, operation: BalanceOperation) -> "BalanceOperationResponse":
        return cls(
            id=operation.id,
            client_id=operation.client_id,
            operation_type=operation.operation_type.value,
            amount_cents=operation.amount_cents,
            bonus_amount=operation.bonus_amount,
            reason=operation.reason,
            actor_id=operation.actor_id,
            idempotency_key=operation.idempotency_key,
            created_at=operation.created_at.isoformat(),
        )


def create_router(service: ClientService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

    @router.get("", response_model=list[ClientResponse])
    async def list_clients(principal: Operator) -> list[ClientResponse]:
        del principal
        return [ClientResponse.from_domain(client) for client in await service.list_clients()]

    @router.post("", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
    async def create_client(
        body: CreateClientRequest,
        principal: Operator,
    ) -> ClientResponse:
        del principal
        return ClientResponse.from_domain(await service.create(**body.model_dump()))

    @router.put("/{client_id}", response_model=ClientResponse)
    async def update_client(
        client_id: uuid.UUID,
        body: UpdateClientRequest,
        principal: Operator,
    ) -> ClientResponse:
        del principal
        return ClientResponse.from_domain(
            await service.update(client_id=client_id, **body.model_dump())
        )

    @router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_client(client_id: uuid.UUID, principal: Operator) -> None:
        del principal
        await service.delete(client_id)

    @router.post("/{client_id}/reset-password", response_model=ResetPasswordResponse)
    async def reset_client_password(
        client_id: uuid.UUID,
        principal: Operator,
    ) -> ResetPasswordResponse:
        del principal
        return ResetPasswordResponse(
            temporary_password=await service.reset_password(client_id),
        )

    @router.get("/search", response_model=list[ClientResponse])
    async def search_clients(
        principal: Operator,
        q: str,
        field: str = "nickname",
    ) -> list[ClientResponse]:
        del principal
        clients = await service.search(q, field)
        return [ClientResponse.from_domain(client) for client in clients]

    @router.get("/{client_id}", response_model=ClientResponse)
    async def get_client(
        client_id: uuid.UUID,
        principal: Operator,
    ) -> ClientResponse:
        del principal
        return ClientResponse.from_domain(await service.get(client_id))

    @router.get("/{client_id}/balance-operations", response_model=list[BalanceOperationResponse])
    async def list_balance_operations(
        client_id: uuid.UUID,
        principal: Operator,
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[BalanceOperationResponse]:
        del principal
        operations = await service.list_operations(client_id, limit)
        return [BalanceOperationResponse.from_domain(operation) for operation in operations]

    @router.post("/{client_id}/top-up", response_model=TopUpResponse)
    async def top_up(
        client_id: uuid.UUID,
        body: TopUpRequest,
        principal: Operator,
        idempotency_key: str = Header(min_length=1, alias="Idempotency-Key"),
    ) -> TopUpResponse:
        client, operation = await service.top_up(
            client_id=client_id,
            actor_id=principal.subject_id,
            idempotency_key=idempotency_key,
            **body.model_dump(),
        )
        return TopUpResponse(
            client=ClientResponse.from_domain(client),
            operation_id=operation.id,
            idempotency_key=operation.idempotency_key,
        )

    return router


def create_guest_router(service: GuestService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/guests", tags=["guests"])

    @router.get("", response_model=list[GuestResponse])
    async def list_guests(principal: Operator) -> list[GuestResponse]:
        del principal
        return [GuestResponse.from_domain(guest) for guest in await service.list_guests()]

    @router.post("", response_model=GuestResponse, status_code=status.HTTP_201_CREATED)
    async def create_guest(
        body: CreateGuestRequest,
        principal: Operator,
    ) -> GuestResponse:
        del principal
        return GuestResponse.from_domain(await service.create(**body.model_dump()))

    @router.get("/search", response_model=list[GuestResponse])
    async def search_guests(
        principal: Operator,
        q: str,
        field: str = "nickname",
    ) -> list[GuestResponse]:
        del principal
        guests = await service.search(q, field)
        return [GuestResponse.from_domain(guest) for guest in guests]

    @router.get("/{guest_id}", response_model=GuestResponse)
    async def get_guest(guest_id: uuid.UUID, principal: Operator) -> GuestResponse:
        del principal
        return GuestResponse.from_domain(await service.get(guest_id))

    return router
