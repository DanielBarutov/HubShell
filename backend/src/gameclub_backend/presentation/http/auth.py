import dataclasses
import datetime
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from gameclub_backend.modules.auth.application.ports import RefreshTokenRepository
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import InvalidTokenError, JwtTokenService
from gameclub_backend.modules.workstations.domain import WorkstationStatus


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class DeviceTokenRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    bootstrap_token: str = Field(min_length=1)


class DeviceEnrollmentRequest(BaseModel):
    mac_addresses: list[str] = Field(min_length=1, max_length=16)
    installation_id: str = Field(min_length=1, max_length=128)


class DeviceEnrollmentResponse(BaseModel):
    state: str
    device_id: str | None = None
    workstation_id: str | None = None
    name: str | None = None
    group_id: str | None = None
    theme: str | None = None
    access_token: str | None = None
    expires_in: int | None = None


class PrincipalResponse(BaseModel):
    subject_id: str
    subject_type: SubjectType
    roles: list[str]
    permissions: list[str]


bearer = HTTPBearer(auto_error=False)

DEV_OPERATOR_PERMISSIONS = frozenset(
    {
        "dashboard.read",
        "audit.read",
        "workstations.manage",
        "clients.manage",
        "catalog.manage",
        "reservations.manage",
        "sessions.manage",
        "billing.manage",
        "sales.manage",
        "analytics.read",
        "cashier.read",
        "cashier.manage",
        "cashier.correct",
        "cashier.supervise",
        "settings.manage",
    }
)


def get_token_service(request: Request) -> JwtTokenService:
    service = request.app.state.jwt_service
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is not configured",
        )
    return service


def get_refresh_repository(request: Request) -> RefreshTokenRepository:
    return request.app.state.refresh_tokens


def issue_refresh_token(
    request: Request,
) -> tuple[str, datetime.datetime]:
    settings = request.app.state.settings
    raw_token = secrets.token_urlsafe(48)
    expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
        seconds=settings.jwt_refresh_ttl_seconds
    )
    return raw_token, expires_at


def refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    try:
        return get_token_service(request).validate_access_token(credentials.credentials)
    except InvalidTokenError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


def require_permissions(*permissions: str):
    async def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not all(principal.can(permission) for permission in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return principal

    return dependency


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: Request, credentials: TokenRequest) -> TokenResponse:
    settings = request.app.state.settings
    if settings.environment != "dev":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not settings.dev_operator_username or not settings.dev_operator_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth is not configured",
        )
    if (
        credentials.username != settings.dev_operator_username
        or credentials.password != settings.dev_operator_password
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    principal = Principal(
        subject_id="dev-operator",
        subject_type=SubjectType.OPERATOR,
        roles=frozenset({"operator"}),
        permissions=DEV_OPERATOR_PERMISSIONS,
    )
    token, expires_in = get_token_service(request).issue_access_token(principal)
    refresh_token, expires_at = issue_refresh_token(request)
    await get_refresh_repository(request).save(
        refresh_token_hash(refresh_token), principal, expires_at
    )
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        refresh_token=refresh_token,
    )


@router.post("/device-token", response_model=TokenResponse)
async def issue_device_token(request: Request, credentials: DeviceTokenRequest) -> TokenResponse:
    settings = request.app.state.settings
    configured_token = settings.device_bootstrap_token
    if settings.environment != "dev" or not configured_token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    if not secrets.compare_digest(credentials.bootstrap_token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap credentials",
        )
    device_id = credentials.device_id.strip()
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Device ID is required",
        )
    principal = Principal(
        subject_id=device_id,
        subject_type=SubjectType.DEVICE,
        roles=frozenset({"device"}),
        permissions=frozenset({"workstations.connect"}),
    )
    token, expires_in = get_token_service(request).issue_access_token(principal)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/device-enrollment", response_model=DeviceEnrollmentResponse)
async def enroll_device(
    request: Request,
    credentials: DeviceEnrollmentRequest,
) -> DeviceEnrollmentResponse | JSONResponse:
    """Find the workstation assigned by MAC and issue a device-scoped token.

    This endpoint is intentionally limited to discovery. It never issues an
    operator token; all workstation commands still require the device JWT.
    """
    workstation_service = getattr(request.app.state, "workstations", None)
    token_service: JwtTokenService | None = getattr(request.app.state, "jwt_service", None)
    if workstation_service is None or token_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Device enrollment is not configured",
        )
    workstation = await workstation_service.enroll_by_mac(
        credentials.mac_addresses,
        credentials.installation_id,
    )
    if workstation is None:
        response = DeviceEnrollmentResponse(state="pending")
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=response.model_dump())
    if workstation.status is WorkstationStatus.DISABLED:
        response = DeviceEnrollmentResponse(
            state="disabled",
            device_id=workstation.device_id,
            workstation_id=str(workstation.id),
            name=workstation.name,
        )
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=response.model_dump())

    principal = Principal(
        subject_id=workstation.device_id,
        subject_type=SubjectType.DEVICE,
        roles=frozenset({"device"}),
        permissions=frozenset({"workstations.connect"}),
    )
    token, expires_in = token_service.issue_access_token(principal)
    return DeviceEnrollmentResponse(
        state="approved",
        device_id=workstation.device_id,
        workstation_id=str(workstation.id),
        name=workstation.name,
        group_id=workstation.group_id,
        theme=workstation.theme,
        access_token=token,
        expires_in=expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: Request,
    credentials: RefreshTokenRequest,
) -> TokenResponse:
    now = datetime.datetime.now(datetime.UTC)
    record = await get_refresh_repository(request).consume(
        refresh_token_hash(credentials.refresh_token), now
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )
    principal = record.principal
    # Dev operators are issued from the local configuration rather than a user
    # directory. Refresh must pick up newly added permissions, otherwise a
    # long-lived refresh token can keep returning an obsolete access scope.
    if (
        request.app.state.settings.environment == "dev"
        and principal.subject_type is SubjectType.OPERATOR
    ):
        principal = dataclasses.replace(principal, permissions=DEV_OPERATOR_PERMISSIONS)
    token, expires_in = get_token_service(request).issue_access_token(principal)
    refresh_token, expires_at = issue_refresh_token(request)
    await get_refresh_repository(request).save(
        refresh_token_hash(refresh_token), principal, expires_at
    )
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        refresh_token=refresh_token,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, credentials: RefreshTokenRequest) -> Response:
    await get_refresh_repository(request).revoke(refresh_token_hash(credentials.refresh_token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=PrincipalResponse)
async def me(principal: Principal = Depends(get_current_principal)) -> PrincipalResponse:
    return PrincipalResponse(
        subject_id=principal.subject_id,
        subject_type=principal.subject_type,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )
