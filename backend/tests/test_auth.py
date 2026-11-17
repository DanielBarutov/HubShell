import asyncio
import datetime

import httpx
import jwt
import pytest

from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import InvalidTokenError, JwtTokenService
from gameclub_backend.presentation.http.app import create_app
from gameclub_backend.presentation.http.auth import refresh_token_hash


def test_refresh_token_default_ttl_is_ninety_days() -> None:
    """
    Проверяет сценарий «test_refresh_token_default_ttl_is_ninety_days» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")

    assert settings.jwt_refresh_ttl_seconds == 90 * 24 * 60 * 60


async def test_dev_operator_can_issue_and_use_bearer_token() -> None:
    """
    Проверяет сценарий «test_dev_operator_can_issue_and_use_bearer_token» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        dev_operator_username="operator",
        dev_operator_password="password",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            token = token_response.json()["access_token"]
            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert token_response.status_code == 200
    assert me_response.status_code == 200
    assert me_response.json()["subject_id"] == "dev-operator"
    assert token_response.json()["refresh_token"]


async def test_operator_login_rate_limit_is_atomic_and_scoped_to_client_ip(api_context) -> None:
    url = "/api/v1/auth/token"
    wrong = {"username": "operator", "password": "wrong"}
    correct = {"username": "operator", "password": "password"}

    # The fixture already used one attempt. Extra requests cannot race past the cap.
    responses = await asyncio.gather(*(api_context.client.post(url, json=wrong) for _ in range(10)))
    assert sorted(response.status_code for response in responses) == [401] * 9 + [429]
    blocked = await api_context.client.post(
        url, json=correct, headers={"X-Forwarded-For": "198.51.100.3"}
    )
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900

    transport = httpx.ASGITransport(app=api_context.application, client=("198.51.100.3", 123))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        assert (await other.post(url, json=correct)).status_code == 200


async def test_refresh_token_rotates_and_logout_revokes_current_token() -> None:
    """
    Проверяет сценарий «test_refresh_token_rotates_and_logout_revokes_current_token» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        dev_operator_username="operator",
        dev_operator_password="password",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                json={"username": "operator", "password": "password"},
            )
            first_refresh_token = token_response.json()["refresh_token"]
            refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": first_refresh_token},
            )
            second_refresh_token = refresh_response.json()["refresh_token"]
            reused_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": first_refresh_token},
            )
            logout_response = await client.post(
                "/api/v1/auth/logout",
                json={"refresh_token": second_refresh_token},
            )
            revoked_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": second_refresh_token},
            )

    assert token_response.status_code == 200
    assert refresh_response.status_code == 200
    assert second_refresh_token != first_refresh_token
    assert reused_response.status_code == 401
    assert logout_response.status_code == 204
    assert revoked_response.status_code == 401


async def test_dev_refresh_rehydrates_permissions_for_legacy_operator_record() -> None:
    """
    Проверяет сценарий «test_dev_refresh_rehydrates_permissions_for_legacy_operator_record» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        dev_operator_username="operator",
        dev_operator_password="password",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        await application.state.refresh_tokens.save(
            refresh_token_hash("legacy-refresh-token"),
            Principal(
                subject_id="dev-operator",
                subject_type=SubjectType.OPERATOR,
                roles=frozenset({"operator"}),
                permissions=frozenset({"dashboard.read"}),
            ),
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
        )
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            refresh_response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "legacy-refresh-token"},
            )
            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {refresh_response.json()['access_token']}"},
            )

    assert refresh_response.status_code == 200
    assert "settings.manage" in me_response.json()["permissions"]


async def test_invalid_bearer_token_is_rejected() -> None:
    """
    Проверяет сценарий «test_invalid_bearer_token_is_rejected» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    application = create_app(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer invalid"},
            )

    assert response.status_code == 401


async def test_device_bootstrap_issues_connect_only_token() -> None:
    """
    Проверяет сценарий «test_device_bootstrap_issues_connect_only_token» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        device_bootstrap_token="bootstrap-secret",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/device-token",
                json={"device_id": "device-01", "bootstrap_token": "bootstrap-secret"},
            )
            token = token_response.json()["access_token"]
            me_response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert token_response.status_code == 200
    assert token_response.json()["refresh_token"] is None
    assert me_response.status_code == 200
    assert me_response.json()["subject_type"] == "device"
    assert me_response.json()["permissions"] == ["workstations.connect"]


async def test_invalid_device_bootstrap_is_rejected() -> None:
    """
    Проверяет сценарий «test_invalid_device_bootstrap_is_rejected» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        device_bootstrap_token="bootstrap-secret",
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/device-token",
                json={"device_id": "device-01", "bootstrap_token": "wrong"},
            )

    assert response.status_code == 401


async def test_device_bootstrap_is_disabled_without_configured_token() -> None:
    """
    Проверяет сценарий «test_device_bootstrap_is_disabled_without_configured_token» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    application = create_app(Settings(jwt_secret="test-secret-with-at-least-32-bytes-long"))
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/device-token",
                json={"device_id": "device-01", "bootstrap_token": "bootstrap-secret"},
            )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "another-issuer"),
        ("aud", "another-audience"),
        ("subject_type", "unknown"),
    ],
)
def test_jwt_rejects_invalid_trust_claims(claim: str, value: str) -> None:
    """
    Проверяет сценарий «test_jwt_rejects_invalid_trust_claims» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(
        jwt_secret="test-secret-with-at-least-32-bytes-long",
        jwt_issuer="gameclub-backend",
        jwt_audience="gameclub-clients",
    )
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "sub": "operator-01",
        "subject_type": "operator",
        "roles": ["operator"],
        "permissions": ["dashboard.read"],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + datetime.timedelta(minutes=5),
        "jti": "test-jti",
    }
    payload[claim] = value
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        JwtTokenService(settings).validate_access_token(token)


def test_jwt_rejects_expired_access_token() -> None:
    """
    Проверяет сценарий «test_jwt_rejects_expired_access_token» и подтверждает ожидаемый
    публичный результат согласно соответствующему бизнес-правилу.
    """
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    now = datetime.datetime.now(datetime.UTC)
    token = jwt.encode(
        {
            "sub": "operator-01",
            "subject_type": "operator",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "iat": now - datetime.timedelta(minutes=10),
            "exp": now - datetime.timedelta(minutes=5),
            "jti": "expired-jti",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )

    with pytest.raises(InvalidTokenError):
        JwtTokenService(settings).validate_access_token(token)
