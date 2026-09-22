import { ApiError } from "../../api";
import type { BackendAnalyticsOverview } from "../../api";

export const ANALYTICS_TIME_ZONE = "Europe/Moscow";

export type AnalyticsDataState =
  | "available"
  | "ready"
  | "loading"
  | "empty"
  | "partial"
  | "not_available"
  | "not_calculated"
  | "permission_denied"
  | "error";

type AnalyticsStateInput = {
  loading?: boolean;
  error?: unknown;
  overview?: BackendAnalyticsOverview | null;
  isEmpty?: boolean;
  metricAvailable?: boolean;
  metricCalculated?: boolean;
  partial?: boolean;
};

type DateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

function getParts(value: Date, timeZone: string): DateParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(value);
  const values = new Map(parts.map((part) => [part.type, Number(part.value)]));
  return {
    year: values.get("year") ?? 0,
    month: values.get("month") ?? 0,
    day: values.get("day") ?? 0,
    hour: values.get("hour") ?? 0,
    minute: values.get("minute") ?? 0,
    second: values.get("second") ?? 0,
  };
}

function getOffsetMinutes(value: Date, timeZone: string): number {
  const parts = getParts(value, timeZone);
  const asUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  );
  return (asUtc - value.getTime()) / 60_000;
}

function parseCalendarDate(value: string): { year: number; month: number; day: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    throw new Error(`Ожидалась дата в формате YYYY-MM-DD: ${value}`);
  }
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function startOfCalendarDay(calendarDate: { year: number; month: number; day: number }, timeZone: string): Date {
  const guess = new Date(Date.UTC(calendarDate.year, calendarDate.month - 1, calendarDate.day));
  const offset = getOffsetMinutes(guess, timeZone);
  return new Date(guess.getTime() - offset * 60_000);
}

export function getAnalyticsPeriodBounds(startDate: string, endDate: string): { startAt: string; endAt: string } {
  const start = parseCalendarDate(startDate);
  const end = parseCalendarDate(endDate);
  const startAt = startOfCalendarDay(start, ANALYTICS_TIME_ZONE);
  const endCalendarDate = new Date(Date.UTC(end.year, end.month - 1, end.day + 1));
  const endAt = startOfCalendarDay(
    {
      year: endCalendarDate.getUTCFullYear(),
      month: endCalendarDate.getUTCMonth() + 1,
      day: endCalendarDate.getUTCDate(),
    },
    ANALYTICS_TIME_ZONE,
  );
  if (startAt >= endAt) {
    throw new Error("Дата начала отчёта должна быть не позже даты окончания");
  }
  return { startAt: startAt.toISOString(), endAt: endAt.toISOString() };
}

export function getAnalyticsDateInputValue(value = new Date()): string {
  const parts = getParts(value, ANALYTICS_TIME_ZONE);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}`;
}

export function getComparisonPeriod(
  startAt: string,
  endAt: string,
  now = new Date(),
): { startAt: string; endAt: string; isPartial: boolean } {
  const start = Date.parse(startAt);
  const end = Date.parse(endAt);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    throw new Error("Период сравнения должен быть непустым aware-интервалом");
  }
  const duration = end - start;
  return {
    startAt: new Date(start - duration).toISOString(),
    endAt: new Date(start).toISOString(),
    isPartial: end > now.getTime(),
  };
}

export function getAnalyticsDataState(input: AnalyticsStateInput): AnalyticsDataState {
  if (input.loading) return "loading";
  if (input.error instanceof ApiError && (input.error.status === 403 || input.error.code === "permission_denied")) {
    return "permission_denied";
  }
  if (input.error) return "error";
  if (input.partial) return "partial";
  if (input.isEmpty || (input.overview && isEmptyOverview(input.overview))) return "empty";
  if (input.metricAvailable === false) return "not_available";
  if (input.metricCalculated === false) return "not_calculated";
  return "ready";
}

export function isEmptyOverview(overview: BackendAnalyticsOverview): boolean {
  return overview.session_count === 0
    && overview.product_sale_count === 0
    && overview.total_revenue_cents === 0
    && overview.played_minutes === 0;
}

export function stateLabel(state: AnalyticsDataState): string {
  const labels: Record<AnalyticsDataState, string> = {
    available: "Доступно",
    ready: "Готово",
    loading: "Загрузка…",
    empty: "Нет данных",
    partial: "Частичные данные",
    not_available: "Недоступно",
    not_calculated: "Не рассчитано",
    permission_denied: "Нет доступа",
    error: "Ошибка загрузки",
  };
  return labels[state];
}

/** Converts known catalog keys into readable names for management reports. */
export function productCategoryLabel(value: string | null | undefined): string {
  const normalized = value?.trim().toLowerCase() ?? "";
  const knownLabels: Record<string, string> = {
    drinks: "Напитки",
    food: "Еда",
    snacks: "Снеки",
    accessories: "Аксессуары",
    unknown: "Без категории",
  };
  return knownLabels[normalized] ?? (value?.trim() || "Без категории");
}
