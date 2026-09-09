import { useEffect, useState } from "react";
import { ArrowDownLeft, BarChart3, Banknote, CalendarDays, ChevronRight, Clock3, Computer, CreditCard, Download, Plus, ShieldCheck, ShoppingCart, TrendingUp, Users, Wifi } from "lucide-react";
import { bookings } from "../../data";
import { ApiError, GameClubApi } from "../../api";
import type { BackendAnalyticsOverview, BackendAuditEvent, Reservation } from "../../api";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { MetricCard } from "../../shared/components/MetricCard";
import { Segmented } from "../../shared/components/Segmented";
import { localDateInputValue } from "../../shared/formatters";
import { PcGrid } from "../workstations/PcGrid";
import type { Client, Workstation } from "../../types";

type DashboardProps = { onDeposit: () => void; onOpenCash: () => void; onOpenMap: () => void; onOpenBookings: () => void; onPc: (pc: Workstation) => void; pcs: Workstation[]; clients: Client[]; reservations: Reservation[]; auditEvents: BackendAuditEvent[]; liveMode: boolean; revenueCents: number | null; revenueChargeCount: number; group: string; setGroup: (group: string) => void; zoneOptions: string[] };

export function AnalyticsView({ api, clients: clientList, onClient }: { api?: GameClubApi; clients: Client[]; onClient: (client: Client) => void }) {
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 29);
    return localDateInputValue(date);
  });
  const [endDate, setEndDate] = useState(() => localDateInputValue(new Date()));
  const [overview, setOverview] = useState<BackendAnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(api));
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!api) {
      setLoading(false);
      return undefined;
    }
    let active = true;
    setLoading(true);
    const start = new Date(startDate + "T00:00:00Z").toISOString();
    const end = new Date(endDate + "T00:00:00Z");
    end.setUTCDate(end.getUTCDate() + 1);
    void api.getAnalyticsOverview(start, end.toISOString(), 8).then((result) => {
      if (active) {
        setOverview(result);
        setError(null);
        setLoading(false);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить аналитику");
        setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [api, startDate, endDate]);

  const money = (cents: number) => (cents / 100).toLocaleString("ru-RU") + " ₽";
  const hours = (minutes: number) => (minutes / 60).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " ч";
  const openClient = (id: string) => {
    const client = clientList.find((item) => item.id === id);
    if (client) onClient(client);
  };
  const setPreset = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - days + 1);
    setStartDate(localDateInputValue(start));
    setEndDate(localDateInputValue(end));
  };
  const exportCsv = async () => {
    if (!api) return;
    setExporting(true);
    try {
      const start = new Date(startDate + "T00:00:00Z").toISOString();
      const end = new Date(endDate + "T00:00:00Z");
      end.setUTCDate(end.getUTCDate() + 1);
      const blob = await api.downloadAnalyticsCsv(start, end.toISOString(), 50);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `analytics-${startDate}-${endDate}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось выгрузить аналитику");
    } finally {
      setExporting(false);
    }
  };
  if (!api) return <div className="catalog-empty-state"><p className="eyebrow">Отчёты · read-only</p><h1>Аналитика</h1><p className="subheading">Live-режим покажет выручку, загрузку, товары и статистику клиентов.</p></div>;
  const maxDailyRevenue = Math.max(1, ...(overview?.daily_activity ?? []).map((item) => item.total_revenue_cents));
  const maxHourlyMinutes = Math.max(1, ...(overview?.hourly_activity ?? []).map((item) => item.played_minutes));
  const breakdown = (items: BackendAnalyticsOverview["zones"], empty: string, mode: "sessions" | "products" = "sessions") => items.length ? <div className="analytics-breakdown-list">{items.slice(0, 8).map((item) => <div className="analytics-breakdown-row" key={item.key}><div className="analytics-breakdown-title"><strong>{item.label}</strong><span>{mode === "products" ? `${item.product_sale_count} продаж · ${item.product_units} шт. · маржа ${money(item.gross_profit_cents)}` : `${item.session_count} сессий · ${hours(item.played_minutes)}`}</span></div><div className="analytics-breakdown-bar"><i style={{ width: `${Math.max(2, item.share_bps / 100)}%` }} /></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">{empty}</div>;
  return <>
    <div className="page-heading analytics-heading"><div><p className="eyebrow">Отчёты · Клуб, продажи и клиенты</p><h1>Аналитика</h1><p className="subheading">Единый отчёт по выручке, загрузке оборудования, товарам и поведению клиентов.</p></div><div className="heading-actions analytics-period"><div className="analytics-presets"><button onClick={() => setPreset(7)}>7 дн.</button><button onClick={() => setPreset(30)}>30 дн.</button><button onClick={() => setPreset(90)}>90 дн.</button></div><div className="analytics-date-field"><span>С</span><DateTimePicker value={startDate} onChange={setStartDate} mode="date" label="Дата начала отчёта" /></div><div className="analytics-date-field"><span>По</span><DateTimePicker value={endDate} onChange={setEndDate} mode="date" label="Дата окончания отчёта" /></div><button className="secondary-button" onClick={() => void exportCsv()} disabled={exporting} aria-busy={exporting}><Download size={14} /> {exporting ? "Готовим…" : "CSV"}</button></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {loading && <div className="timeline-empty">Собираем показатели…</div>}
    {!loading && overview && <>
      <div className="metric-grid analytics-metrics analytics-metrics-wide">
        <MetricCard title="Общая выручка" value={money(overview.total_revenue_cents)} delta={overview.session_count + overview.product_sale_count + " операций"} positive icon={<BarChart3 size={18} />} accent="violet" />
        <MetricCard title="Валовая прибыль" value={money(overview.gross_profit_cents)} delta={`скидки ${money(overview.discount_cents)}`} positive icon={<TrendingUp size={18} />} accent="green" />
        <MetricCard title="Игровое время" value={hours(overview.played_minutes)} delta={`${overview.session_count} сессий`} icon={<Clock3 size={18} />} accent="blue" />
        <MetricCard title="Загрузка мест" value={`${overview.occupancy_percent.toLocaleString("ru-RU")}%`} delta={`${overview.workstation_count} ПК`} icon={<Computer size={18} />} accent="orange" />
        <MetricCard title="Активные клиенты" value={String(overview.active_client_count)} delta={`${overview.new_client_count} новых`} icon={<Users size={18} />} accent="blue" />
        <MetricCard title="Посетители" value={String(overview.unique_visitor_count)} delta={`${overview.guest_session_count} гостевых`} icon={<Users size={18} />} accent="violet" />
        <MetricCard title="Продажи товаров" value={money(overview.product_revenue_cents)} delta={`${overview.product_units} единиц`} icon={<ShoppingCart size={18} />} accent="green" />
        <MetricCard title="Средняя сессия" value={`${overview.average_session_minutes.toLocaleString("ru-RU")} мин`} delta={`пик ${overview.peak_usage_hour ?? "—"}`} icon={<Wifi size={18} />} accent="orange" />
      </div>
      <div className="analytics-report-grid">
        <section className="white-card analytics-card analytics-chart-card"><div className="section-row"><div><h2>Динамика выручки</h2><p className="section-caption">Сессии и товары по дням выбранного периода</p></div><span className="active-chip">{startDate} — {endDate}</span></div><div className="analytics-chart-legend"><span><i className="session" /> Игровое время</span><span><i className="products" /> Товары</span></div><div className="analytics-chart">{overview.daily_activity.map((item) => <div className="analytics-chart-column" key={item.key}><div className="analytics-chart-bars"><i className="session" style={{ height: `${Math.max(item.session_revenue_cents ? 5 : 0, item.session_revenue_cents / maxDailyRevenue * 100)}%` }} /><i className="products" style={{ height: `${Math.max(item.product_revenue_cents ? 5 : 0, item.product_revenue_cents / maxDailyRevenue * 100)}%` }} /></div><span>{item.label}</span></div>)}</div></section>
        <section className="white-card analytics-card analytics-insights"><div className="section-row"><div><h2>Сводка периода</h2><p className="section-caption">Ключевые операционные сигналы</p></div></div><div className="analytics-insight-list"><div><span>Новые клиенты</span><strong>{overview.new_client_count}</strong></div><div><span>Вернувшиеся клиенты</span><strong>{overview.returning_client_count}</strong></div><div><span>Товарная себестоимость</span><strong>{money(overview.product_cost_cents)}</strong></div><div><span>Пиковый час</span><strong>{overview.peak_usage_hour ?? "Нет данных"}</strong></div><div><span>Продажи / сессии</span><strong>{overview.product_sale_count} / {overview.session_count}</strong></div></div></section>
      </div>
      <div className="analytics-report-grid">
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Загрузка по часам</h2><p className="section-caption">Когда клуб наиболее загружен</p></div></div><div className="analytics-hourly-chart">{overview.hourly_activity.map((item) => <div className="analytics-hour-column" key={item.key} title={`${item.label}: ${hours(item.played_minutes)}`}><i style={{ height: `${Math.max(item.played_minutes ? 5 : 2, item.played_minutes / maxHourlyMinutes * 100)}%` }} /><span>{Number(item.key) % 3 === 0 ? item.label : ""}</span></div>)}</div></section>
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Способы оплаты</h2><p className="section-caption">Распределение подтверждённой выручки</p></div></div>{overview.payment_methods.length ? <div className="analytics-payment-list">{overview.payment_methods.map((item) => <div className="analytics-payment-row" key={item.key}><div><strong>{item.label}</strong><span>{item.operation_count} операций · {item.share_bps / 100}%</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Оплат за период нет</div>}</section>
      </div>
      <div className="analytics-breakdown-grid"><section className="white-card analytics-card"><div className="section-row"><div><h2>Зоны клуба</h2><p className="section-caption">Загрузка и выручка по залам</p></div></div>{breakdown(overview.zones, "Сессий по зонам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Игровые места</h2><p className="section-caption">Какие ПК используются чаще</p></div></div>{breakdown(overview.workstations, "Данных по местам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Тарифы</h2><p className="section-caption">Продажи игрового времени</p></div></div>{breakdown(overview.tariffs, "Тарифы за период не продавались")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Категории товаров</h2><p className="section-caption">Выручка, себестоимость и маржа</p></div></div>{breakdown(overview.product_categories, "Продаж по категориям нет", "products")}</section></div>
      <div className="analytics-grid"><section className="white-card analytics-card"><div className="section-row"><div><h2>Популярные товары</h2><p className="section-caption">Количество, выручка и маржа по snapshots</p></div><span className="active-chip">{overview.product_sale_count} продаж</span></div>{overview.top_products.length ? <div className="analytics-list">{overview.top_products.map((item) => <div className="analytics-list-row" key={item.product_id + item.product_name}><div><strong>{item.product_name}</strong><span>{item.units} шт. · маржа {money(item.gross_profit_cents)}</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Продаж за период нет</div>}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Лучшие клиенты</h2><p className="section-caption">Игровое время, товары и общие траты</p></div><span className="active-chip">{overview.active_client_count} активных</span></div>{overview.top_clients.length ? <div className="analytics-list">{overview.top_clients.map((item) => <button className="analytics-list-row analytics-client-row" key={item.client_id} onClick={() => openClient(item.client_id)}><div><strong>{item.nickname}</strong><span>{hours(item.played_minutes)} · {item.session_count} сессий · товары {money(item.product_spend_cents)}</span></div><b>{money(item.total_spend_cents)}</b></button>)}</div> : <div className="timeline-empty">Активности клиентов за период нет</div>}</section></div>
    </>}
  </>;
}

export function Dashboard({ onDeposit, onOpenCash, onOpenMap, onOpenBookings, onPc, pcs, clients: clientList, reservations, auditEvents, liveMode, revenueCents, revenueChargeCount, group, setGroup, zoneOptions }: DashboardProps) {
  const busy = pcs.filter((pc) => pc.status === "busy").length;
  const free = pcs.filter((pc) => pc.status === "online").length;
  const visiblePcs = pcs.filter((pc) => group === "Все зоны" || pc.group === group);
  const deposits = clientList.reduce((total, client) => total + client.balance, 0);
  const waitingReservations = reservations.filter((reservation) => reservation.status === "confirmed").length;
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">{new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p><h1>Добрый день, Алексей</h1><p className="subheading">Вот что происходит в клубе прямо сейчас.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onOpenCash}><Clock3 size={16} /> Открыть смену</button><button className="primary-button" onClick={onDeposit}><Plus size={17} /> Пополнить депозит</button></div></div>
      <div className="metric-grid">
        <MetricCard title={liveMode ? "Выручка сегодня" : "Выручка за смену"} value={liveMode ? (revenueCents === null ? "—" : `${(revenueCents / 100).toLocaleString("ru-RU")} ₽`) : "48 620 ₽"} delta={liveMode ? `${revenueChargeCount} списаний` : "+12,8%"} positive={!liveMode && revenueCents === null} icon={<Banknote size={18} />} accent="violet" />
        <MetricCard title="Активные сессии" value={`${busy} / ${pcs.length}`} delta={`${free} свободных`} positive icon={<Wifi size={18} />} accent="blue" />
        <MetricCard title="Брони сегодня" value={liveMode ? String(reservations.length) : "18"} delta={liveMode ? `${waitingReservations} ожидают` : "4 ожидают"} icon={<CalendarDays size={18} />} accent="orange" />
        <MetricCard title="На депозитах" value={liveMode ? `${deposits.toLocaleString("ru-RU")} ₽` : "126 840 ₽"} delta={liveMode ? `${clientList.length} клиентов` : "32 клиента"} icon={<CreditCard size={18} />} accent="green" />
      </div>
      <div className="section-row"><div><h2>Карта мест</h2><p className="section-caption">Состояние игровых мест в реальном времени</p></div><div className="section-tools"><Segmented value={group} onChange={setGroup} options={zoneOptions} /><button className="text-button" onClick={onOpenMap}>Открыть карту <ChevronRight size={15} /></button></div></div>
      <PcGrid pcs={visiblePcs} onPc={onPc} compact />
      <div className="lower-grid"><ActivityCard liveMode={liveMode} events={auditEvents} /><UpcomingBookings liveMode={liveMode} reservations={reservations} pcs={pcs} clients={clientList} onOpenBookings={onOpenBookings} /></div>
    </>
  );
}

export function ActivityCard({ liveMode, events }: { liveMode: boolean; events: BackendAuditEvent[] }) {
  if (liveMode) {
    const eventIcon = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("client")) return <ArrowDownLeft size={16} />;
      if (path.includes("session")) return <Computer size={16} />;
      if (path.includes("reservation")) return <CalendarDays size={16} />;
      return <ShieldCheck size={16} />;
    };
    const eventTitle = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("top-up") || path.includes("topup")) return "Пополнение баланса";
      if (path.includes("charge")) return "Списание за сессию";
      if (path.includes("reservation")) return "Операция с бронью";
      if (path.includes("session")) return "Операция сессии";
      if (path.includes("workstation")) return "Операция с игровым ПК";
      if (path.includes("client")) return "Операция с клиентом";
      if (path.includes("catalog")) return "Изменение каталога";
      return event.action;
    };
    const outcomeLabel = (event: BackendAuditEvent) => event.outcome === "success" ? "Успешно" : `Ошибка ${event.status_code}`;
    return <div className="white-card activity-card"><div className="card-heading"><div><h3>Активность смены</h3><p>Последние операции команды</p></div><ShieldCheck size={18} className="muted" /></div>{events.map((event) => <div className="activity-item" key={event.id}><div className={`activity-icon ${event.outcome === "success" ? "income" : "booking"}`}>{eventIcon(event)}</div><div><strong>{eventTitle(event)}</strong><span>{new Date(event.created_at).toLocaleString("ru-RU")} · {event.actor_id || "Система"}</span></div><b className={event.outcome === "success" ? "income-text" : ""}>{outcomeLabel(event)}</b></div>)}{!events.length && <div className="timeline-empty">Операций пока нет</div>}</div>;
  }
  return <div className="white-card activity-card"><div className="card-heading"><div><h3>Активность смены</h3><p>Последние операции оператора</p></div><ShieldCheck size={18} className="muted" /></div><div className="activity-item"><div className="activity-icon income"><ArrowDownLeft size={16} /></div><div><strong>Пополнение · NightFox</strong><span>Сегодня, 12:36</span></div><b className="income-text">+1 000 ₽</b></div><div className="activity-item"><div className="activity-icon session"><Computer size={16} /></div><div><strong>Запущена сессия · VIP-01</strong><span>Сегодня, 12:18</span></div><b>m0onlight</b></div><div className="activity-item"><div className="activity-icon booking"><CalendarDays size={16} /></div><div><strong>Создана бронь · A-04</strong><span>Сегодня, 12:04</span></div><b>night_walker</b></div></div>;
}

export function UpcomingBookings({
  liveMode,
  reservations,
  pcs,
  clients,
  onOpenBookings,
}: {
  liveMode: boolean;
  reservations: Reservation[];
  pcs: Workstation[];
  clients: Client[];
  onOpenBookings: () => void;
}) {
  const workstationNames = new Map(pcs.map((pc) => [pc.id, pc.name]));
  const clientNames = new Map(clients.map((client) => [client.id, client.nickname]));
  const liveItems = reservations
    .filter((reservation) => reservation.status !== "cancelled" && Date.parse(reservation.end_at) >= Date.now())
    .sort((left, right) => Date.parse(left.start_at) - Date.parse(right.start_at))
    .slice(0, 3);
  return <div className="white-card upcoming-card"><div className="card-heading"><div><h3>Ближайшие брони</h3><p>Сегодня</p></div><button className="text-button" onClick={onOpenBookings}>Все брони <ChevronRight size={15} /></button></div>{liveMode ? liveItems.map((reservation) => <div className="upcoming-item" key={reservation.id}><div className="booking-time"><strong>{new Date(reservation.start_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</strong><span>{new Date(reservation.end_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span></div><div className="booking-line" /><div><strong>{reservation.guest_name || (reservation.client_id ? clientNames.get(reservation.client_id) || "Клиент" : "Гость")}</strong><span>{reservation.workstation_ids.map((id) => workstationNames.get(id) || id.slice(0, 8)).join(", ")}</span></div><span className={`booking-status ${reservation.status === "confirmed" ? "pending" : ""}`}>{reservation.status}</span></div>) : bookings.slice(0, 3).map((booking) => <div className="upcoming-item" key={booking.id}><div className="booking-time"><strong>{booking.start}</strong><span>{booking.end}</span></div><div className="booking-line" /><div><strong>{booking.client}</strong><span>{booking.workstation}</span></div><span className={`booking-status ${booking.status === "Ожидает" ? "pending" : ""}`}>{booking.status}</span></div>)}{liveMode && !liveItems.length && <div className="timeline-empty">На сегодня броней не найдено</div>}</div>;
}
