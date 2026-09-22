import datetime
import os

import pytest

from gameclub_backend.modules.analytics.benchmark import parse_period, run_benchmark

UTC = datetime.UTC


def test_parse_period_uses_half_open_aware_interval() -> None:
    """Проверяет разбор часового пояса и полуоткрытого периода."""
    period = parse_period("2026-09-20T00:00:00+00:00/2026-09-21T00:00:00+00:00")
    assert period.start_at == datetime.datetime(2026, 9, 20, tzinfo=UTC)
    assert period.end_at == datetime.datetime(2026, 9, 21, tzinfo=UTC)


@pytest.mark.integration
@pytest.mark.postgres
async def test_benchmark_runs_against_real_period_when_dsn_is_configured() -> None:
    """Проверяет измерение настоящего периода в PostgreSQL при наличии DSN."""
    dsn = os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set GAMECLUB_TEST_POSTGRES_DSN to run real PostgreSQL benchmark")
    results = await run_benchmark(
        dsn,
        tuple(
            parse_period(period)
            for period in (
                "2026-09-20T00:00:00+00:00/2026-09-21T00:00:00+00:00",
                "2026-09-18T00:00:00+00:00/2026-09-21T00:00:00+00:00",
            )
        ),
    )
    assert len(results) == 2
    assert results[0].period_start == "2026-09-20T00:00:00+00:00"
    assert results[0].table_counts["product_sales"] >= 1
    assert all(result.elapsed_ms >= 0 for result in results)
    assert all(len(result.explain_plans) == 4 for result in results)
