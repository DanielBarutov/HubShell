import type { CSSProperties } from "react";
import type { Workstation } from "../../types";
import { getSessionTooltipDetails, SessionEndingProjection } from "./sessionTooltip";

function formatMinutes(value: number): string {
  const minutes = Math.max(0, value);
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  if (!hours) return `${remainder} мин`;
  return remainder ? `${hours} ч ${remainder} мин` : `${hours} ч`;
}

function formatTime(value: Date): string {
  return value.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function SessionHoverCard({ pc, id, style, endingProjection }: {
  pc: Workstation;
  id: string;
  style?: CSSProperties;
  endingProjection: SessionEndingProjection;
}) {
  const details = getSessionTooltipDetails(pc, endingProjection);
  if (!details) return null;

  return <aside className="fixed z-50 w-80 rounded-xl border border-primary/30! bg-base-100/95! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.35),0_0_24px_rgba(49,217,120,0.14)] backdrop-blur-xl" id={id} role="tooltip" style={style}>
    <div className="flex items-center justify-between gap-3 border-b border-primary/15! pb-3 text-xs text-base-content/60!">
      <span>Текущая сессия</span>
      {details.stale && <b className="text-warning!">Данные устарели</b>}
    </div>
    <strong className="mt-3 block text-lg font-bold">{details.clientName}</strong>
    <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {details.balanceCents != null && <><dt className="text-base-content/60!">Баланс</dt><dd className="text-right font-semibold">{(details.balanceCents / 100).toLocaleString("ru-RU")} ₽</dd></>}
      <dt className="text-base-content/60!">По балансу</dt><dd className="text-right font-semibold">≈ {formatMinutes(details.balanceMinutes)}</dd>
      <dt className="text-base-content/60!">Всего по пакетам</dt><dd className="text-right font-semibold">{formatMinutes(details.packageMinutes)}</dd>
      <dt className="text-base-content/60!">Общее время</dt><dd className="text-right font-semibold">{formatMinutes(details.totalMinutes)}</dd>
      {details.ending && <><dt className="text-base-content/60!">Окончание</dt><dd className="text-right font-semibold text-primary!">{formatTime(details.ending)}</dd></>}
    </dl>
    {details.packages.length > 0 && <div className="mt-4 border-t border-primary/15! pt-3">
      <span className="text-xs font-semibold text-base-content/60!">Пакеты</span>
      <div className="mt-2 flex flex-col gap-2">
      {details.packages.map((item, index) => <div className="rounded-lg border border-primary/15! bg-base-200/55! p-2 text-xs" key={`${item.status}-${index}`}>
        <b className="block">{item.tariffName ? `${item.tariffName} · ${formatMinutes(item.durationMinutes)}` : formatMinutes(item.durationMinutes)}</b>
        <span className="mt-1 block text-base-content/60!">{item.status === "active" ? "Активный" : item.availableNow ? "В очереди" : "В очереди · недоступен до окна"} · осталось {formatMinutes(item.remainingMinutes)}</span>
      </div>)}
      </div>
    </div>}
    {details.snapshotTime && <small className="mt-3 block text-[10px] text-base-content/45!">Снимок сервера: {formatTime(details.snapshotTime)}</small>}
  </aside>;
}
