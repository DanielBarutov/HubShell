import datetime
import uuid
from zoneinfo import ZoneInfo

import pytest

from gameclub_backend.modules.analytics.occupancy import (
    CapacityStatus,
    OccupancySession,
    WorkstationHistory,
    WorkstationStateChange,
    calculate_occupancy,
    split_session_into_hour_buckets,
)

MOSCOW = ZoneInfo("Europe/Moscow")
UTC = datetime.UTC


def at(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value).replace(tzinfo=MOSCOW)


def session(
    workstation_id: uuid.UUID,
    started_at: datetime.datetime,
    ended_at: datetime.datetime,
    *,
    session_id: str = "session-1",
    transfer_id: str | None = None,
    revenue_cents: int = 0,
) -> OccupancySession:
    return OccupancySession(
        id=session_id,
        workstation_id=workstation_id,
        started_at=started_at,
        ended_at=ended_at,
        transfer_id=transfer_id,
        revenue_cents=revenue_cents,
    )


def workstation(
    workstation_id: uuid.UUID,
    created_at: datetime.datetime,
    *,
    group_id: str = "main",
    changes: tuple[WorkstationStateChange, ...] = (),
) -> WorkstationHistory:
    return WorkstationHistory(
        workstation_id=workstation_id,
        group_id=group_id,
        created_at=created_at,
        state_changes=changes,
    )


def test_session_is_split_using_half_open_moscow_hour_buckets() -> None:
    """Проверяет разбиение сессии по часовым корзинам Москвы."""
    workstation_id = uuid.uuid4()
    started_at = at("2026-01-10T23:50:00")
    ended_at = at("2026-01-11T00:20:00")

    slices = split_session_into_hour_buckets(started_at, ended_at)

    assert [(item.local_hour, item.occupied_minutes) for item in slices] == [(23, 10), (0, 20)]
    assert sum(item.occupied_minutes for item in slices) == 30
    assert slices[0].start_at < slices[0].end_at <= slices[1].start_at

    report = calculate_occupancy(
        started_at,
        ended_at,
        sessions=(session(workstation_id, started_at, ended_at),),
        workstations=(workstation(workstation_id, started_at - datetime.timedelta(days=1)),),
    )
    assert report.occupied_minutes == 30
    assert report.hourly_buckets[0].occupied_minutes == 10
    assert report.hourly_buckets[1].occupied_minutes == 20


def test_duplicate_and_overlapping_transfer_spans_are_not_double_counted() -> None:
    """Проверяет защиту от двойного учёта переносов и повторной доставки."""
    workstation_id = uuid.uuid4()
    target_id = uuid.uuid4()
    start = at("2026-01-10T10:00:00")
    end = at("2026-01-10T11:00:00")
    target_start = at("2026-01-10T10:30:00")
    target_end = at("2026-01-10T11:30:00")

    report = calculate_occupancy(
        start,
        at("2026-01-10T12:00:00"),
        sessions=(
            session(workstation_id, start, end, session_id="source", transfer_id="transfer-1"),
            session(
                workstation_id,
                start,
                end,
                session_id="source-retry",
                transfer_id="transfer-1",
            ),
            session(
                target_id,
                target_start,
                target_end,
                session_id="target",
                transfer_id="transfer-1",
            ),
        ),
        workstations=(
            workstation(workstation_id, start - datetime.timedelta(days=1)),
            workstation(target_id, start - datetime.timedelta(days=1)),
        ),
    )

    assert report.session_count == 1
    assert report.occupied_minutes == 90
    assert report.workstations[0].occupied_minutes + report.workstations[1].occupied_minutes == 120


def test_historical_capacity_excludes_disabled_and_archived_but_keeps_offline_and_stale() -> None:
    """Проверяет историческую ёмкость с правилами статусов рабочего места."""
    workstation_id = uuid.uuid4()
    start = at("2026-01-10T00:00:00")
    end = at("2026-01-11T00:00:00")
    workstation_history = workstation(
        workstation_id,
        start - datetime.timedelta(hours=12),
        changes=(
            WorkstationStateChange(at("2026-01-10T06:00:00"), CapacityStatus.OFFLINE),
            WorkstationStateChange(at("2026-01-10T10:00:00"), CapacityStatus.DISABLED),
            WorkstationStateChange(at("2026-01-10T14:00:00"), CapacityStatus.STALE),
            WorkstationStateChange(at("2026-01-10T18:00:00"), CapacityStatus.ARCHIVED),
        ),
    )

    report = calculate_occupancy(
        start,
        end,
        sessions=(),
        workstations=(workstation_history,),
    )

    assert report.available_minutes == 840
    assert report.workstations[0].available_minutes == 840


def test_report_exposes_hour_rates_peak_and_heatmap_inputs() -> None:
    """Проверяет часы, загрузку, ставки, пик и данные тепловой карты."""
    workstation_id = uuid.uuid4()
    start = at("2026-01-05T10:00:00")
    end = at("2026-01-05T12:00:00")

    report = calculate_occupancy(
        start,
        end,
        sessions=(
            session(
                workstation_id,
                at("2026-01-05T10:00:00"),
                at("2026-01-05T11:30:00"),
                revenue_cents=1_500,
            ),
        ),
        workstations=(workstation(workstation_id, start - datetime.timedelta(days=1)),),
    )

    assert report.occupied_hours == 1.5
    assert report.available_hours == 2.0
    assert report.average_session_minutes == 90.0
    assert report.occupancy_percent == 75.0
    assert report.revenue_per_occupied_hour == 1_000.0
    assert report.revenue_per_available_hour == 750.0
    assert report.peak_hour == 10
    assert report.weak_hour == 11
    assert len(report.heatmap) == 2
    assert [(item.weekday, item.hour) for item in report.heatmap] == [(0, 10), (0, 11)]
    assert [item.occupied_minutes for item in report.heatmap] == [60, 30]
    assert all(item.available_minutes == 60 for item in report.heatmap)


def test_bucket_arithmetic_remains_elapsed_time_safe_for_historical_moscow_transition() -> None:
    """Проверяет расчёт длительности при историческом переходе часового пояса."""
    started_at = datetime.datetime(2014, 10, 25, 23, 30, tzinfo=UTC)
    ended_at = datetime.datetime(2014, 10, 26, 2, 30, tzinfo=UTC)

    slices = split_session_into_hour_buckets(started_at, ended_at)

    assert sum(item.occupied_minutes for item in slices) == 180
    assert all(item.start_at.tzinfo is not None for item in slices)
    assert all(item.end_at > item.start_at for item in slices)
    assert slices[0].local_hour == 2
    assert slices[-1].local_hour == 5


def test_zone_breakdown_counts_distinct_logical_sessions() -> None:
    """Проверяет число разных логических сессий в разрезе зоны."""
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    start = at("2026-01-05T10:00:00")
    end = at("2026-01-05T12:00:00")

    report = calculate_occupancy(
        start,
        end,
        sessions=(
            session(first_id, start, at("2026-01-05T10:30:00"), session_id="first"),
            session(second_id, at("2026-01-05T11:00:00"), end, session_id="second"),
        ),
        workstations=(
            workstation(first_id, start - datetime.timedelta(days=1), group_id="vip"),
            workstation(second_id, start - datetime.timedelta(days=1), group_id="vip"),
        ),
    )

    assert report.zones[0].key == "vip"
    assert report.zones[0].session_count == 2


def test_rejects_naive_or_reversed_intervals() -> None:
    """Проверяет отказ для времени без зоны и обратного интервала."""
    with pytest.raises(ValueError, match="timezone"):
        split_session_into_hour_buckets(
            datetime.datetime(2026, 1, 1),
            datetime.datetime(2026, 1, 1, 1),
        )

    with pytest.raises(ValueError, match="before"):
        split_session_into_hour_buckets(at("2026-01-01T01:00:00"), at("2026-01-01T00:00:00"))
