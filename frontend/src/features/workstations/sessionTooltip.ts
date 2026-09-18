import type { Workstation } from "../../types";

export type SessionTooltipDetails = {
  clientName: string;
  balanceCents: number | null;
  balanceMinutes: number;
  packages: Array<{
    tariffName: string | null;
    durationMinutes: number;
    remainingMinutes: number;
    status: "active" | "queued";
  }>;
  packageMinutes: number;
  totalMinutes: number;
  ending: Date | null;
  snapshotTime: Date | null;
  stale: boolean;
};

export function getSessionTooltipDetails(pc: Workstation): SessionTooltipDetails | null {
  const snapshot = pc.sessionSnapshot;
  const stale = pc.status === "stale";
  if (!snapshot || pc.status !== "busy") return null;

  const packages = snapshot.entitlements
    .filter((item) => item.status === "active" || item.status === "queued")
    .map((item) => ({
      tariffName: item.tariff_name ?? null,
      durationMinutes: item.duration_minutes,
      remainingMinutes: item.remaining_minutes,
      status: item.status as "active" | "queued",
    }));
  const activeTariffMinutes = packages.length
    ? 0
    : Math.max(0, snapshot.active_tariff?.remaining_minutes ?? 0);
  const packageMinutes = packages.reduce((total, item) => total + item.remainingMinutes, 0)
    + activeTariffMinutes;
  const balanceMinutes = Math.max(0, snapshot.balance_remaining_minutes ?? 0);
  const loginGrantMinutes = Math.max(0, snapshot.login_grant_remaining_minutes ?? 0);
  const totalMinutes = packageMinutes + balanceMinutes + loginGrantMinutes;
  const snapshotTime = new Date(snapshot.server_time);
  const validSnapshotTime = Number.isNaN(snapshotTime.valueOf()) ? null : snapshotTime;

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
