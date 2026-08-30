import os

import pytest

from gameclub_backend.config import Settings
from gameclub_backend.infrastructure.resources import create_resources


async def test_resources_close_is_idempotent_without_dependencies() -> None:
    resources = create_resources(Settings())

    await resources.close()
    await resources.close()


@pytest.mark.skipif(
    not os.getenv("GAMECLUB_TEST_POSTGRES_DSN"),
    reason="Set GAMECLUB_TEST_POSTGRES_DSN to run infrastructure integration tests",
)
async def test_configured_resources_pass_health_and_close_gracefully() -> None:
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
