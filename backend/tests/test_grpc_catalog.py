import datetime

import grpc
import pytest
from google.protobuf import timestamp_pb2

from gameclub.v1 import catalog_pb2, catalog_pb2_grpc
from gameclub_backend.config import Settings
from gameclub_backend.modules.auth.domain import Principal, SubjectType
from gameclub_backend.modules.auth.infrastructure.jwt import JwtTokenService
from gameclub_backend.modules.catalog.application.service import CatalogService
from gameclub_backend.modules.catalog.infrastructure.memory import InMemoryCatalogRepository
from gameclub_backend.presentation.grpc.services import CatalogGrpcService

pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_catalog_grpc_round_trips_windows_audience_and_audience_quote() -> None:
    """
    Проверяет gRPC-контракт тарифа и server-side выбор quote для аудитории покупателя.
    """
    settings = Settings(jwt_secret="test-secret-with-at-least-32-bytes-long")
    token_service = JwtTokenService(settings)
    catalog = CatalogService(InMemoryCatalogRepository())
    server = grpc.aio.server()
    catalog_pb2_grpc.add_CatalogServiceServicer_to_server(
        CatalogGrpcService(catalog, token_service),
        server,
    )
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
    client = catalog_pb2_grpc.CatalogServiceStub(channel)
    operator_token, _ = token_service.issue_access_token(
        Principal(
            subject_id="operator",
            subject_type=SubjectType.OPERATOR,
            roles=frozenset({"operator"}),
            permissions=frozenset({"catalog.manage"}),
        )
    )
    metadata = (("authorization", f"Bearer {operator_token}"),)
    moment = datetime.datetime.now(datetime.UTC).replace(second=0, microsecond=0)
    timestamp = timestamp_pb2.Timestamp()
    timestamp.FromDatetime(moment)
    current_minute = moment.hour * 60 + moment.minute
    sale_end = (current_minute + 1) % (24 * 60)

    try:
        created = await client.CreateTariff(
            catalog_pb2.CreateTariffRequest(
                name="Guest night package",
                group_id="vip",
                duration_minutes=60,
                price_cents=500,
                valid_from=timestamp,
                lifecycle=catalog_pb2.TARIFF_LIFECYCLE_PUBLISHED,
                billing_mode=catalog_pb2.BILLING_MODE_BLOCK,
                time_restricted=True,
                sale_window_start_minute=current_minute,
                sale_window_end_minute=sale_end,
                usage_window_start_minute=22 * 60,
                usage_window_end_minute=6 * 60,
                window_timezone="UTC",
                audience="guest",
            ),
            metadata=metadata,
        )
        quote = await client.Quote(
            catalog_pb2.QuoteRequest(
                duration_minutes=60,
                group_id="vip",
                moment=timestamp,
                audience="guest",
            ),
            metadata=metadata,
        )
    finally:
        await channel.close()
        await server.stop(0)

    assert created.audience == "guest"
    assert created.time_restricted is True
    assert created.sale_window_start_minute == current_minute
    assert created.sale_window_end_minute == sale_end
    assert created.usage_window_start_minute == 22 * 60
    assert created.usage_window_end_minute == 6 * 60
    assert created.window_timezone == "UTC"
    assert quote.tariff_id == created.id
    assert quote.price_cents == 500
