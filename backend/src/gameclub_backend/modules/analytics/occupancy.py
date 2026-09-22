from __future__ import annotations

import dataclasses
import datetime
import enum
import typing
import uuid
from collections import defaultdict
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")
UTC = datetime.UTC


class CapacityStatus(enum.StrEnum):
    ACTIVE = "active"
    OFFLINE = "offline"
    STALE = "stale"
    DISABLED = "disabled"
    ARCHIVED = "archived"

    @property
    def contributes_capacity(self) -> bool:
        return self not in {self.DISABLED, self.ARCHIVED}


@dataclasses.dataclass(frozen=True)
class WorkstationStateChange:
    at: datetime.datetime
    status: CapacityStatus

    def __post_init__(self) -> None:
        _require_aware(self.at)


@dataclasses.dataclass(frozen=True)
class WorkstationHistory:
    workstation_id: uuid.UUID
    group_id: str
    created_at: datetime.datetime
    state_changes: tuple[WorkstationStateChange, ...] = ()
    initial_status: CapacityStatus = CapacityStatus.ACTIVE

    def __post_init__(self) -> None:
        _require_aware(self.created_at)


@dataclasses.dataclass(frozen=True)
class OccupancySession:
    id: str
    workstation_id: uuid.UUID
    started_at: datetime.datetime
    ended_at: datetime.datetime
    transfer_id: str | None = None
    revenue_cents: int = 0

    def __post_init__(self) -> None:
        _require_aware(self.started_at)
        _require_aware(self.ended_at)
        if self.started_at >= self.ended_at:
            raise ValueError("Session must start before it ends")
        if self.revenue_cents < 0:
            raise ValueError("Session revenue cannot be negative")


@dataclasses.dataclass(frozen=True)
class SessionBucketSlice:
    key: str
    start_at: datetime.datetime
    end_at: datetime.datetime
    local_date: datetime.date
    local_hour: int
    weekday: int
    occupied_minutes: float


@dataclasses.dataclass(frozen=True)
class OccupancyBucket:
    key: str
    start_at: datetime.datetime
    end_at: datetime.datetime
    local_date: datetime.date
    local_hour: int
    weekday: int
    occupied_minutes: float
    available_minutes: float

    @property
    def occupancy_percent(self) -> float:
        return _percent(self.occupied_minutes, self.available_minutes)


@dataclasses.dataclass(frozen=True)
class HeatmapCell:
    weekday: int
    hour: int
    occupied_minutes: float
    available_minutes: float

    @property
    def occupancy_percent(self) -> float:
        return _percent(self.occupied_minutes, self.available_minutes)


@dataclasses.dataclass(frozen=True)
class OccupancyBreakdown:
    key: str
    label: str
    occupied_minutes: float
    available_minutes: float
    session_count: int
    revenue_cents: int

    @property
    def occupied_hours(self) -> float:
        return round(self.occupied_minutes / 60, 2)

    @property
    def available_hours(self) -> float:
        return round(self.available_minutes / 60, 2)

    @property
    def average_session_minutes(self) -> float:
        return round(self.occupied_minutes / self.session_count, 2) if self.session_count else 0.0

    @property
    def occupancy_percent(self) -> float:
        return _percent(self.occupied_minutes, self.available_minutes)

    @property
    def revenue_per_occupied_hour(self) -> float:
        return _hour_rate(self.revenue_cents, self.occupied_minutes)

    @property
    def revenue_per_available_hour(self) -> float:
        return _hour_rate(self.revenue_cents, self.available_minutes)


@dataclasses.dataclass(frozen=True)
class OccupancyReport:
    start_at: datetime.datetime
    end_at: datetime.datetime
    occupied_minutes: float
    available_minutes: float
    session_count: int
    revenue_cents: int
    hourly_buckets: tuple[OccupancyBucket, ...]
    heatmap: tuple[HeatmapCell, ...]
    workstations: tuple[OccupancyBreakdown, ...]
    zones: tuple[OccupancyBreakdown, ...]
    peak_hour: int | None
    weak_hour: int | None

    @property
    def occupied_hours(self) -> float:
        return round(self.occupied_minutes / 60, 2)

    @property
    def available_hours(self) -> float:
        return round(self.available_minutes / 60, 2)

    @property
    def average_session_minutes(self) -> float:
        return round(self.occupied_minutes / self.session_count, 2) if self.session_count else 0.0

    @property
    def occupancy_percent(self) -> float:
        return _percent(self.occupied_minutes, self.available_minutes)

    @property
    def revenue_per_occupied_hour(self) -> float:
        return _hour_rate(self.revenue_cents, self.occupied_minutes)

    @property
    def revenue_per_available_hour(self) -> float:
        return _hour_rate(self.revenue_cents, self.available_minutes)


def split_session_into_hour_buckets(
    started_at: datetime.datetime,
    ended_at: datetime.datetime,
    timezone: ZoneInfo = MOSCOW,
) -> tuple[SessionBucketSlice, ...]:
    """Split an aware half-open interval into Moscow-local hour slices."""
    _require_aware(started_at)
    _require_aware(ended_at)
    if started_at >= ended_at:
        raise ValueError("Session must start before it ends")

    start_utc = started_at.astimezone(UTC)
    end_utc = ended_at.astimezone(UTC)
    cursor = start_utc
    local = cursor.astimezone(timezone)
    boundary = local.replace(minute=0, second=0, microsecond=0).astimezone(UTC)
    while boundary > cursor:
        boundary -= datetime.timedelta(hours=1)

    result: list[SessionBucketSlice] = []
    while cursor < end_utc:
        next_boundary = boundary + datetime.timedelta(hours=1)
        slice_end = min(next_boundary, end_utc)
        local_start = cursor.astimezone(timezone)
        result.append(
            SessionBucketSlice(
                key=local_start.strftime("%Y-%m-%dT%H:00%z"),
                start_at=cursor,
                end_at=slice_end,
                local_date=local_start.date(),
                local_hour=local_start.hour,
                weekday=local_start.weekday(),
                occupied_minutes=round((slice_end - cursor).total_seconds() / 60, 6),
            )
        )
        cursor = slice_end
        boundary = next_boundary
    return tuple(result)


def calculate_occupancy(
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    *,
    sessions: typing.Iterable[OccupancySession],
    workstations: typing.Iterable[WorkstationHistory],
    timezone: ZoneInfo = MOSCOW,
) -> OccupancyReport:
    """Calculate occupancy from immutable session and workstation history facts."""
    _require_aware(start_at)
    _require_aware(end_at)
    if start_at >= end_at:
        raise ValueError("Report period must start before it ends")
    report_start = start_at.astimezone(UTC)
    report_end = end_at.astimezone(UTC)

    workstation_list = tuple(workstations)
    histories = {item.workstation_id: item for item in workstation_list}
    available_intervals = {
        item.workstation_id: _available_intervals(item, report_start, report_end)
        for item in workstation_list
    }

    groups: dict[str, list[tuple[OccupancySession, datetime.datetime, datetime.datetime]]] = (
        defaultdict(list)
    )
    seen_spans: set[tuple[str, uuid.UUID, datetime.datetime, datetime.datetime]] = set()
    for item in sessions:
        _require_aware(item.started_at)
        _require_aware(item.ended_at)
        clipped_start = max(item.started_at.astimezone(UTC), report_start)
        clipped_end = min(item.ended_at.astimezone(UTC), report_end)
        if clipped_start >= clipped_end or item.workstation_id not in histories:
            continue
        logical_key = f"transfer:{item.transfer_id}" if item.transfer_id else f"session:{item.id}"
        span_key = (logical_key, item.workstation_id, clipped_start, clipped_end)
        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)
        groups[logical_key].append((item, clipped_start, clipped_end))

    hour_slices = split_session_into_hour_buckets(report_start, report_end, timezone)
    workstation_occupied: dict[uuid.UUID, list[tuple[datetime.datetime, datetime.datetime]]] = {}
    workstation_groups: dict[uuid.UUID, set[str]] = defaultdict(set)
    workstation_revenue: dict[uuid.UUID, int] = defaultdict(int)
    for workstation_id in histories:
        intervals: list[tuple[datetime.datetime, datetime.datetime]] = []
        for logical_key, items in groups.items():
            station_intervals = [
                (clipped_start, clipped_end)
                for item, clipped_start, clipped_end in items
                if item.workstation_id == workstation_id
            ]
            if station_intervals:
                workstation_groups[workstation_id].add(logical_key)
                workstation_revenue[workstation_id] += sum(
                    item.revenue_cents
                    for item, _, _ in items
                    if item.workstation_id == workstation_id
                )
                intervals.extend(station_intervals)
        workstation_occupied[workstation_id] = _merge_intervals(intervals)

    occupied_by_bucket = []
    available_by_bucket = []
    for hour_slice in hour_slices:
        station_minutes = sum(
            _overlap_minutes(interval, (hour_slice.start_at, hour_slice.end_at))
            for intervals in workstation_occupied.values()
            for interval in intervals
        )
        duplicate_transfer_minutes = 0.0
        for items in groups.values():
            per_station = defaultdict(list)
            for item, clipped_start, clipped_end in items:
                bucket_start = max(clipped_start, hour_slice.start_at)
                bucket_end = min(clipped_end, hour_slice.end_at)
                if bucket_start < bucket_end:
                    per_station[item.workstation_id].append((bucket_start, bucket_end))
            station_total = sum(
                _intervals_minutes(_merge_intervals(intervals))
                for intervals in per_station.values()
            )
            all_intervals = _merge_intervals(
                [interval for intervals in per_station.values() for interval in intervals]
            )
            group_total = _intervals_minutes(all_intervals)
            duplicate_transfer_minutes += max(0.0, station_total - group_total)
        occupied_by_bucket.append(round(max(0.0, station_minutes - duplicate_transfer_minutes), 6))
        available_by_bucket.append(
            round(
                sum(
                    _overlap_minutes(interval, (hour_slice.start_at, hour_slice.end_at))
                    for intervals in available_intervals.values()
                    for interval in intervals
                ),
                6,
            )
        )

    hourly_buckets = tuple(
        OccupancyBucket(
            key=hour_slice.key,
            start_at=hour_slice.start_at,
            end_at=hour_slice.end_at,
            local_date=hour_slice.local_date,
            local_hour=hour_slice.local_hour,
            weekday=hour_slice.weekday,
            occupied_minutes=occupied_by_bucket[index],
            available_minutes=available_by_bucket[index],
        )
        for index, hour_slice in enumerate(hour_slices)
    )
    heatmap = _build_heatmap(hourly_buckets)
    workstation_breakdowns = tuple(
        _breakdown_for_workstation(
            history,
            workstation_occupied[history.workstation_id],
            available_intervals[history.workstation_id],
            workstation_groups[history.workstation_id],
            workstation_revenue[history.workstation_id],
        )
        for history in sorted(workstation_list, key=lambda item: str(item.workstation_id))
    )
    zones = _build_zones(workstation_breakdowns, workstation_list, workstation_groups)
    revenue_cents = sum(
        sum(item.revenue_cents for item, _, _ in items) for items in groups.values()
    )
    occupied_minutes = round(sum(occupied_by_bucket), 6)
    available_minutes = round(sum(available_by_bucket), 6)
    usable_buckets = [item for item in hourly_buckets if item.available_minutes > 0]
    peak_hour = (
        max(usable_buckets, key=lambda item: (item.occupancy_percent, -item.local_hour)).local_hour
        if usable_buckets
        else None
    )
    weak_hour = (
        min(usable_buckets, key=lambda item: (item.occupancy_percent, item.local_hour)).local_hour
        if usable_buckets
        else None
    )
    return OccupancyReport(
        start_at=report_start,
        end_at=report_end,
        occupied_minutes=occupied_minutes,
        available_minutes=available_minutes,
        session_count=len(groups),
        revenue_cents=revenue_cents,
        hourly_buckets=hourly_buckets,
        heatmap=heatmap,
        workstations=workstation_breakdowns,
        zones=zones,
        peak_hour=peak_hour,
        weak_hour=weak_hour,
    )


def _available_intervals(
    history: WorkstationHistory,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
) -> tuple[tuple[datetime.datetime, datetime.datetime], ...]:
    created_at = history.created_at.astimezone(UTC)
    if created_at >= end_at:
        return ()
    cursor = max(created_at, start_at)
    current_status = history.initial_status
    intervals: list[tuple[datetime.datetime, datetime.datetime]] = []
    for change in sorted(history.state_changes, key=lambda item: item.at):
        change_at = change.at.astimezone(UTC)
        if change_at <= start_at:
            current_status = change.status
            continue
        if change_at >= end_at:
            break
        if current_status.contributes_capacity and cursor < change_at:
            intervals.append((cursor, change_at))
        current_status = change.status
        cursor = change_at
    if current_status.contributes_capacity and cursor < end_at:
        intervals.append((cursor, end_at))
    return tuple(intervals)


def _breakdown_for_workstation(
    history: WorkstationHistory,
    occupied: list[tuple[datetime.datetime, datetime.datetime]],
    available: tuple[tuple[datetime.datetime, datetime.datetime], ...],
    groups: set[str],
    revenue_cents: int,
) -> OccupancyBreakdown:
    return OccupancyBreakdown(
        key=str(history.workstation_id),
        label=str(history.workstation_id),
        occupied_minutes=round(_intervals_minutes(occupied), 6),
        available_minutes=round(_intervals_minutes(available), 6),
        session_count=len(groups),
        revenue_cents=revenue_cents,
    )


def _build_zones(
    workstations: tuple[OccupancyBreakdown, ...],
    histories: tuple[WorkstationHistory, ...],
    session_groups: dict[uuid.UUID, set[str]],
) -> tuple[OccupancyBreakdown, ...]:
    labels = {str(item.workstation_id): item.group_id for item in histories}
    workstation_ids = {str(item.workstation_id): item.workstation_id for item in histories}
    grouped: dict[str, list[OccupancyBreakdown]] = defaultdict(list)
    for item in workstations:
        grouped[labels[item.key]].append(item)
    return tuple(
        OccupancyBreakdown(
            key=key,
            label=key,
            occupied_minutes=round(sum(item.occupied_minutes for item in values), 6),
            available_minutes=round(sum(item.available_minutes for item in values), 6),
            session_count=len(
                {
                    session
                    for item in values
                    for session in session_groups[workstation_ids[item.key]]
                }
            ),
            revenue_cents=sum(item.revenue_cents for item in values),
        )
        for key, values in sorted(grouped.items())
    )


def _build_heatmap(buckets: tuple[OccupancyBucket, ...]) -> tuple[HeatmapCell, ...]:
    grouped: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for bucket in buckets:
        values = grouped[(bucket.weekday, bucket.local_hour)]
        values[0] += bucket.occupied_minutes
        values[1] += bucket.available_minutes
    return tuple(
        HeatmapCell(
            weekday=weekday,
            hour=hour,
            occupied_minutes=round(values[0], 6),
            available_minutes=round(values[1], 6),
        )
        for (weekday, hour), values in sorted(grouped.items())
    )


def _merge_intervals(
    intervals: typing.Iterable[tuple[datetime.datetime, datetime.datetime]],
) -> list[tuple[datetime.datetime, datetime.datetime]]:
    ordered = sorted((start, end) for start, end in intervals if start < end)
    if not ordered:
        return []
    result = [ordered[0]]
    for start, end in ordered[1:]:
        current_start, current_end = result[-1]
        if start <= current_end:
            result[-1] = (current_start, max(current_end, end))
        else:
            result.append((start, end))
    return result


def _overlap_minutes(
    left: tuple[datetime.datetime, datetime.datetime],
    right: tuple[datetime.datetime, datetime.datetime],
) -> float:
    start = max(left[0], right[0])
    end = min(left[1], right[1])
    return max(0.0, (end - start).total_seconds() / 60)


def _intervals_minutes(
    intervals: typing.Iterable[tuple[datetime.datetime, datetime.datetime]],
) -> float:
    return sum((end - start).total_seconds() / 60 for start, end in intervals)


def _percent(numerator: float, denominator: float) -> float:
    return round(numerator / denominator * 100, 2) if denominator else 0.0


def _hour_rate(revenue_cents: int, minutes: float) -> float:
    return round(revenue_cents / (minutes / 60), 2) if minutes else 0.0


def _require_aware(value: datetime.datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include timezone")
