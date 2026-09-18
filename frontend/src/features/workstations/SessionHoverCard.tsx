import type { CSSProperties } from "react";
import type { Workstation } from "../../types";
import { getSessionTooltipDetails } from "./sessionTooltip";

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

export function SessionHoverCard({ pc, id, style }: { pc: Workstation; id: string; style?: CSSProperties }) {
  const details = getSessionTooltipDetails(pc);
  if (!details) return null;

  return <aside className="session-hover-card" id={id} role="tooltip" style={style}>
    <div className="session-hover-card-head">
      <span>Текущая сессия</span>
      {details.stale && <b>Данные устарели</b>}
    </div>
    <strong className="session-hover-client">{details.clientName}</strong>
    <dl className="session-hover-summary">
      {details.balanceCents != null && <><dt>Баланс</dt><dd>{(details.balanceCents / 100).toLocaleString("ru-RU")} ₽</dd></>}
      <dt>По балансу</dt><dd>≈ {formatMinutes(details.balanceMinutes)}</dd>
      <dt>Всего по пакетам</dt><dd>{formatMinutes(details.packageMinutes)}</dd>
      <dt>Общее время</dt><dd>{formatMinutes(details.totalMinutes)}</dd>
      {details.ending && <><dt>Окончание</dt><dd>{formatTime(details.ending)}</dd></>}
    </dl>
    {details.packages.length > 0 && <div className="session-hover-packages">
      <span>Пакеты</span>
      {details.packages.map((item, index) => <div className="session-hover-package" key={`${item.status}-${index}`}>
        <b>{item.tariffName ? `${item.tariffName} · ${formatMinutes(item.durationMinutes)}` : formatMinutes(item.durationMinutes)}</b>
        <span>{item.status === "active" ? "Активный" : item.availableNow ? "В очереди" : "В очереди · недоступен до окна"} · осталось {formatMinutes(item.remainingMinutes)}</span>
      </div>)}
    </div>}
    {details.snapshotTime && <small>Снимок сервера: {formatTime(details.snapshotTime)}</small>}
  </aside>;
}
