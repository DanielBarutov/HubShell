from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import json
import time

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


@dataclasses.dataclass(frozen=True, slots=True)
class BenchmarkPeriod:
    start_at: datetime.datetime
    end_at: datetime.datetime

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Benchmark period requires aware timestamps")
        if self.start_at >= self.end_at:
            raise ValueError("Benchmark period must be half-open and increasing")
        object.__setattr__(self, "start_at", self.start_at.astimezone(datetime.UTC))
        object.__setattr__(self, "end_at", self.end_at.astimezone(datetime.UTC))


@dataclasses.dataclass(frozen=True, slots=True)
class BenchmarkResult:
    period_start: str
    period_end: str
    table_counts: dict[str, int]
    elapsed_ms: float
    explain_plans: dict[str, object]


def parse_period(value: str) -> BenchmarkPeriod:
    try:
        start, end = value.split("/", 1)
        return BenchmarkPeriod(
            datetime.datetime.fromisoformat(start), datetime.datetime.fromisoformat(end)
        )
    except ValueError as error:
        raise ValueError("Period must be START_ISO/END_ISO") from error


async def _measure_period(engine, period: BenchmarkPeriod) -> BenchmarkResult:
    table_names = (
        "balance_operations",
        "session_charges",
        "product_sales",
        "guest_session_payments",
    )
    counts: dict[str, int] = {}
    plans: dict[str, object] = {}
    started = time.perf_counter()
    async with engine.connect() as connection:
        for table_name in table_names:
            count_query = sa.text(
                f"SELECT count(*) FROM {table_name} "
                "WHERE created_at >= :start_at AND created_at < :end_at"
            )
            counts[table_name] = int(
                (
                    await connection.execute(
                        count_query,
                        {"start_at": period.start_at, "end_at": period.end_at},
                    )
                ).scalar_one()
            )
            explain = await connection.execute(
                sa.text(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                    f"SELECT count(*) FROM {table_name} "
                    "WHERE created_at >= :start_at AND created_at < :end_at"
                ),
                {"start_at": period.start_at, "end_at": period.end_at},
            )
            plan = explain.scalar_one()
            plans[table_name] = plan[0] if isinstance(plan, list) and plan else plan
    elapsed_ms = (time.perf_counter() - started) * 1000
    return BenchmarkResult(
        period_start=period.start_at.isoformat(),
        period_end=period.end_at.isoformat(),
        table_counts=counts,
        elapsed_ms=round(elapsed_ms, 3),
        explain_plans=plans,
    )


async def run_benchmark(
    dsn: str, periods: tuple[BenchmarkPeriod, ...]
) -> tuple[BenchmarkResult, ...]:
    if not periods:
        raise ValueError("At least one benchmark period is required")
    engine = create_async_engine(dsn, pool_pre_ping=True)
    try:
        return tuple([await _measure_period(engine, period) for period in periods])
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark analytics aggregates on real PostgreSQL periods"
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL async DSN; defaults to GAMECLUB_TEST_POSTGRES_DSN",
    )
    parser.add_argument(
        "--period",
        action="append",
        dest="periods",
        help="Repeatable half-open period START_ISO/END_ISO",
        required=True,
    )
    args = parser.parse_args()
    import os

    dsn = args.dsn or os.getenv("GAMECLUB_TEST_POSTGRES_DSN")
    if not dsn:
        parser.error("--dsn or GAMECLUB_TEST_POSTGRES_DSN is required")
    results = asyncio.run(run_benchmark(dsn, tuple(parse_period(value) for value in args.periods)))
    print(json.dumps([dataclasses.asdict(result) for result in results], indent=2, default=str))


if __name__ == "__main__":
    main()
