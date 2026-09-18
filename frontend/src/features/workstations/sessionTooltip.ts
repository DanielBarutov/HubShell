import type { Workstation } from "../../types";

export type SessionTooltipDetails = {
  clientName: string;
  balanceCents: number | null;
  balanceMinutes: number;
  packages: Array<{
    id: string;
    tariffName: string | null;
    durationMinutes: number;
    remainingMinutes: number;
    status: "active" | "queued";
    availableNow: boolean;
  }>;
  packageMinutes: number;
  totalMinutes: number;
  ending: Date | null;
  snapshotTime: Date | null;
  stale: boolean;
};

function minuteInTimezone(value: Date, timezone: string): number | null {
  try {
    const parts = new Intl.DateTimeFormat("en-GB", {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(value);
    const hour = Number(parts.find((part) => part.type === "hour")?.value);
    const minute = Number(parts.find((part) => part.type === "minute")?.value);
    return Number.isFinite(hour) && Number.isFinite(minute) ? hour * 60 + minute : null;
  } catch {
    return null;
  }
}

function isPackageAvailableNow(
  item: NonNullable<Workstation["sessionSnapshot"]>["entitlements"][number],
  snapshotTime: Date | null,
): boolean {
  if (!item.time_restricted || !snapshotTime) return true;
  const start = item.usage_window_start_minute;
  const end = item.usage_window_end_minute;
  const minute = minuteInTimezone(snapshotTime, item.window_timezone ?? "UTC");
  if (start == null || end == null || minute == null) return false;
  return start < end ? minute >= start && minute < end : minute >= start || minute < end;
}

function minutesUntilUsageWindowCloses(
  item: NonNullable<Workstation["sessionSnapshot"]>["entitlements"][number],
  snapshotTime: Date | null,
): number | null {
  if (!item.time_restricted || !snapshotTime) return null;
  const start = item.usage_window_start_minute;
  const end = item.usage_window_end_minute;
  const minute = minuteInTimezone(snapshotTime, item.window_timezone ?? "UTC");
  if (start == null || end == null || minute == null) return null;
  if (start < end) return minute >= start && minute < end ? end - minute : null;
  if (minute >= start) return 24 * 60 - minute + end;
  return minute < end ? end - minute : null;
}

export function getSessionTooltipDetails(pc: Workstation): SessionTooltipDetails | null {
  const snapshot = pc.sessionSnapshot;
  const stale = pc.status === "stale";
  if (!snapshot || pc.status !== "busy") return null;

  const snapshotTime = new Date(snapshot.server_time);
  const validSnapshotTime = Number.isNaN(snapshotTime.valueOf()) ? null : snapshotTime;
  const packages = snapshot.entitlements
    .filter((item) => item.status === "active" || item.status === "queued")
    .map((item) => ({
      id: item.id,
      tariffName: item.tariff_name ?? null,
      durationMinutes: item.duration_minutes,
      remainingMinutes: item.remaining_minutes,
      status: item.status as "active" | "queued",
      availableNow: isPackageAvailableNow(item, validSnapshotTime),
    }));
  const activeTariffMinutes = packages.length
    ? 0
    : Math.max(0, snapshot.active_tariff?.remaining_minutes ?? 0);
  const uncappedPackageMinutes = packages.reduce(
    (total, item) => total + (item.availableNow ? item.remainingMinutes : 0),
    0,
  )
    + activeTariffMinutes;
  const activePackage = packages.find((item) => item.status === "active");
  const activeSnapshotPackage = activePackage
    ? snapshot.entitlements.find((item) => item.id === activePackage.id)
    : undefined;
  const activeWindowMinutes = activeSnapshotPackage
    ? minutesUntilUsageWindowCloses(activeSnapshotPackage, validSnapshotTime)
    : null;
  const sessionCutoffMinutes = activePackage
    && activeWindowMinutes != null
    && activePackage.remainingMinutes > activeWindowMinutes
    ? activeWindowMinutes
    : null;
  const packageMinutes = sessionCutoffMinutes == null
    ? uncappedPackageMinutes
    : Math.min(uncappedPackageMinutes, sessionCutoffMinutes);
  const balanceMinutes = Math.max(0, snapshot.balance_remaining_minutes ?? 0);
  const loginGrantMinutes = Math.max(0, snapshot.login_grant_remaining_minutes ?? 0);
  const uncappedTotalMinutes = packageMinutes + balanceMinutes + loginGrantMinutes;
  const totalMinutes = sessionCutoffMinutes == null
    ? uncappedTotalMinutes
    : Math.min(uncappedTotalMinutes, sessionCutoffMinutes);
  return {
    clientName: pc.client ?? "Гость",
    balanceCents: snapshot.balance_cents ?? null,
    balanceMinutes,
    packages,
    packageMinutes,
    totalMinutes,
    ending: validSnapshotTime && totalMinutes > 0
      ? new Date(validSnapshotTime.valueOf() + totalMinutes * 60_000)
      : null,
    snapshotTime: validSnapshotTime,
    stale,
  };
}

export function sessionTooltip(pc: Workstation): string | undefined {
  const details = getSessionTooltipDetails(pc);
  if (!details) return pc.status === "stale" ? "Связь нестабильна" : undefined;
  const lines = [`Пользователь: ${details.clientName}`];
  if (details.balanceCents != null) lines.push(`Баланс: ${(details.balanceCents / 100).toLocaleString("ru-RU")} ₽`);
  lines.push(`По балансу: ${details.balanceMinutes} мин`);
  for (const item of details.packages) {
    lines.push(`${item.status === "active" ? "Активный" : "В очереди"} · ${item.remainingMinutes} из ${item.durationMinutes} мин`);
  }
  lines.push(`Всего по пакетам: ${details.packageMinutes} мин`);
  lines.push(`Общее доступное время: ${details.totalMinutes} мин`);
  if (details.ending) {
    lines.push(`Окончание: ${details.ending.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`);
  }
  if (details.snapshotTime) {
    lines.push(`Снимок: ${details.snapshotTime.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`);
  }
  return lines.join("\n");
}
