import os

import pytest

from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.resources import create_resources


async def test_resources_close_is_idempotent_without_dependencies() -> None:
    """
    Проверяет сценарий «test_resources_close_is_idempotent_without_dependencies» и подтверждает
    ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    resources = create_resources(Settings())

    await resources.close()
    await resources.close()


@pytest.mark.skipif(
    not os.getenv("GAMECLUB_TEST_POSTGRES_DSN"),
    reason="Set GAMECLUB_TEST_POSTGRES_DSN to run infrastructure integration tests",
)
@pytest.mark.integration
@pytest.mark.postgres
@pytest.mark.redis
@pytest.mark.slow
async def test_configured_resources_pass_health_and_close_gracefully() -> None:
    """
    Проверяет сценарий «test_configured_resources_pass_health_and_close_gracefully» и
    подтверждает ожидаемый публичный результат согласно соответствующему бизнес-правилу.
    """
    resources = create_resources(
        Settings(
            postgres_dsn=os.environ["GAMECLUB_TEST_POSTGRES_DSN"],
            redis_url=os.getenv("GAMECLUB_TEST_REDIS_URL"),
        )
    )
    try:
        for check in resources.checks.values():
            assert await check.check()
    finally:
        await resources.close()

    await resources.close()
