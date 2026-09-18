import datetime
import uuid

import pytest

from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.domain import BillingMode, TariffAudience, TariffSaleChannel
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository


@pytest.mark.asyncio
async def test_operator_only_tariff_is_hidden_from_self_service_catalog() -> None:
    """Проверяет, что channel policy отделена от audience и enforced backend-ом."""
    repository = InMemoryCatalogRepository()
    service = CatalogService(repository)
    now = datetime.datetime(2026, 9, 17, 12, 0, tzinfo=datetime.UTC)
    operator_only = await service.create_tariff(
        name="Только оператор",
        group_id="main",
        duration_minutes=60,
        price_cents=1_000,
        valid_from=now - datetime.timedelta(hours=1),
        valid_to=None,
        billing_mode=BillingMode.BLOCK,
        audience=TariffAudience.GUEST,
        sale_channel=TariffSaleChannel.OPERATOR,
    )
    self_service = await service.create_tariff(
        name="Самостоятельный",
        group_id="main",
        duration_minutes=60,
        price_cents=1_000,
        valid_from=now - datetime.timedelta(hours=1),
        valid_to=None,
        billing_mode=BillingMode.BLOCK,
        audience=TariffAudience.REGISTERED,
        sale_channel=TariffSaleChannel.SELF_SERVICE,
    )

    visible = await service.list_available_tariffs("main", TariffAudience.REGISTERED, now)
    all_operator_tariffs = await service.list_tariffs_for_group("main")

    assert operator_only not in visible
    assert self_service in visible
    assert operator_only in all_operator_tariffs
    assert uuid.UUID(str(operator_only.id)) == operator_only.id
