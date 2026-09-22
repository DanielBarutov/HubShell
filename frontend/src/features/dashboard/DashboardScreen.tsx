import { useEffect, useState } from "react";
import { ArrowDownLeft, BarChart3, Banknote, CalendarDays, ChevronDown, ChevronRight, Clock3, Computer, CreditCard, Download, ListFilter, Plus, RotateCcw, ShieldCheck, ShoppingCart, TrendingUp, Users, Wifi } from "lucide-react";
import { bookings } from "../../data";
import { ApiError, GameClubApi } from "../../api";
import type { BackendAnalyticsDrillDown, BackendAnalyticsOverview, BackendAnalyticsV2Dashboard, BackendAuditEvent, Reservation } from "../../api";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { MetricCard } from "../../shared/components/MetricCard";
import { Segmented } from "../../shared/components/Segmented";
import { getAnalyticsDataState, getAnalyticsDateInputValue, getAnalyticsPeriodBounds, isEmptyOverview, productCategoryLabel, stateLabel, type AnalyticsDataState } from "./analytics";
import { PcGrid } from "../workstations/PcGrid";
import type { Client, Workstation } from "../../types";

type DashboardProps = { onDeposit: () => void; onOpenCash: () => void; onOpenMap: () => void; onOpenBookings: () => void; onPc: (pc: Workstation) => void; pcs: Workstation[]; clients: Client[]; reservations: Reservation[]; auditEvents: BackendAuditEvent[]; liveMode: boolean; revenueCents: number | null; revenueChargeCount: number; group: string; setGroup: (group: string) => void; zoneOptions: string[] };
type AnalyticsFilterValues = {
  zoneKey?: string;
  workstationKey?: string;
  tariffKey?: string;
  clientGroupKey?: string;
  paymentMethodKey?: string;
  operationType?: string;
  categoryKey?: string;
  productKey?: string;
  operatorKey?: string;
};

export function AnalyticsView({ api, clients: clientList, onClient }: { api?: GameClubApi; clients: Client[]; onClient: (client: Client) => void }) {
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - 29);
    return getAnalyticsDateInputValue(date);
  });
  const [endDate, setEndDate] = useState(() => getAnalyticsDateInputValue());
  const [overview, setOverview] = useState<BackendAnalyticsOverview | null>(null);
  const [dashboard, setDashboard] = useState<BackendAnalyticsV2Dashboard | null>(null);
  const [drillDown, setDrillDown] = useState<BackendAnalyticsDrillDown | null>(null);
  const [drillDownLoading, setDrillDownLoading] = useState(false);
  const [analyticsFilters, setAnalyticsFilters] = useState<AnalyticsFilterValues>({});
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [activeAnalyticsTab, setActiveAnalyticsTab] = useState<"overview" | "finance" | "occupancy" | "customers">("overview");
  const [showComparison, setShowComparison] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<AnalyticsDataState>(api ? "loading" : "empty");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!api) {
      setRequestState("empty");
      return undefined;
    }
    let active = true;
    setRequestState("loading");
    setDashboard(null);
    const { startAt, endAt } = getAnalyticsPeriodBounds(startDate, endDate);
    void api.getAnalyticsOverview(startAt, endAt, 8).then((result) => {
      if (active) {
        setOverview(result);
        setError(null);
        setRequestState(result.data_state ?? (isEmptyOverview(result) ? "empty" : "ready"));
      }
    }).catch((requestError) => {
      if (active) {
        setOverview(null);
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить аналитику");
        setRequestState(getAnalyticsDataState({ error: requestError }));
      }
    });
    if (typeof api.getAnalyticsDashboard === "function") {
      void api.getAnalyticsDashboard({ startAt, endAt, ...analyticsFilters, comparison: showComparison }).then((result) => {
        if (active) setDashboard(result);
      }).catch(() => {
        if (active) setDashboard(null);
      });
    }
    return () => {
      active = false;
    };
  }, [api, startDate, endDate, analyticsFilters, showComparison]);

  const money = (cents: number) => (cents / 100).toLocaleString("ru-RU") + " ₽";
  const hours = (minutes: number) => (minutes / 60).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " ч";
  const openClient = (id: string) => {
    const client = clientList.find((item) => item.id === id);
    if (client) onClient(client);
  };
  const setPreset = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setUTCDate(start.getUTCDate() - days + 1);
    setStartDate(getAnalyticsDateInputValue(start));
    setEndDate(getAnalyticsDateInputValue(end));
  };
  const exportCsv = async () => {
    if (!api) return;
    setExporting(true);
    try {
      const { startAt, endAt } = getAnalyticsPeriodBounds(startDate, endDate);
      const blob = await api.downloadAnalyticsCsv(startAt, endAt, 50);
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
      setRequestState(getAnalyticsDataState({ error: requestError }));
    } finally {
      setExporting(false);
    }
  };
  const openDrillDown = async () => {
    if (!api?.getAnalyticsDrillDown) return;
    setDrillDownLoading(true);
    try {
      const { startAt, endAt } = getAnalyticsPeriodBounds(startDate, endDate);
      setDrillDown(await api.getAnalyticsDrillDown({ startAt, endAt, limit: 100, ...analyticsFilters }));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить детализацию");
    } finally {
      setDrillDownLoading(false);
    }
  };
  const hasActiveFilters = Object.values(analyticsFilters).some(Boolean);
  const clearAnalyticsFilters = () => setAnalyticsFilters({});
  if (!api) return <div className="catalog-empty-state"><p className="eyebrow">Отчёты · read-only</p><h1>Аналитика</h1><p className="subheading">Live-режим покажет выручку, загрузку, товары и статистику клиентов.</p></div>;
  const loading = requestState === "loading";
  const maxDailyRevenue = Math.max(1, ...(overview?.daily_activity ?? []).map((item) => item.total_revenue_cents));
  const maxHourlyMinutes = Math.max(1, ...(overview?.hourly_activity ?? []).map((item) => item.played_minutes));
  const metricValue = (value: string, state: AnalyticsDataState | "ready" = "ready") => state === "ready" ? value : stateLabel(state);
  const metricInfo = {
    revenue: { description: "Подтверждённая выручка за выбранный период.", formula: "Доступные подтверждённые факты, без повторного учёта депозита.", source: "Текущий analytics.v1 overview.", emptyState: "Без источника Payment/Refund точная чистая выручка не рассчитывается." },
    margin: { description: "Валовая прибыль по доступной товарной себестоимости.", formula: "Товарная выручка − snapshot себестоимости.", source: "Завершённые ProductSale.", emptyState: "Операционные расходы и неполные финансовые факты не подставляются." },
    time: { description: "Игровое время завершённых сессий.", formula: "Сумма подтверждённых минут сессий.", source: "Завершённые Session.", emptyState: "При отсутствии завершённых сессий показатель не рассчитан." },
    occupancy: { description: "Доля занятых минут от доступной ёмкости.", formula: "Занятые минуты / доступные минуты × 100%.", source: "Текущий analytics.v1 overview.", emptyState: "Историческая ёмкость мест ещё не доступна; ноль не означает 0%." },
  };
  const comparisonMetrics = Object.values(dashboard?.blocks ?? {})
    .flatMap((block) => Object.values(block.metrics))
    .filter((metric) => metric.comparison?.current !== null && metric.comparison?.previous !== null)
    .slice(0, 4);
  const comparisonValue = (metric: typeof comparisonMetrics[number], value: number) => {
    const key = metric.key.toLowerCase();
    if (key.includes("revenue") || key.includes("money") || key.includes("payment") || key.includes("deposit")) return money(value);
    if (key.includes("occupancy") || key.includes("margin")) return `${value.toLocaleString("ru-RU")}%`;
    if (key.includes("minute")) return `${value.toLocaleString("ru-RU")} мин`;
    return value.toLocaleString("ru-RU");
  };
  const breakdown = (items: BackendAnalyticsOverview["zones"], empty: string, mode: "sessions" | "products" = "sessions") => items.length ? <div className="analytics-breakdown-list">{items.slice(0, 8).map((item) => <div className="analytics-breakdown-row" key={item.key}><div className="analytics-breakdown-title"><strong>{mode === "products" ? productCategoryLabel(item.label) : item.label}</strong><span>{mode === "products" ? `${item.product_sale_count} продаж · ${item.product_units} шт. · маржа ${money(item.gross_profit_cents)}` : `${item.session_count} сессий · ${hours(item.played_minutes)}`}</span></div><div className="analytics-breakdown-bar"><i style={{ width: `${Math.max(2, item.share_bps / 100)}%` }} /></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">{empty}</div>;
  return <>
    <div className="page-heading analytics-heading"><div><p className="eyebrow">Отчёты · Деньги, клиенты и загрузка</p><h1>Аналитика клуба</h1><p className="subheading">Понятная сводка для решения трёх вопросов: сколько заработали, сколько людей пришло и насколько занят клуб.</p></div><div className="heading-actions analytics-period"><div className="analytics-presets"><button onClick={() => setPreset(7)}>7 дней</button><button onClick={() => setPreset(30)}>30 дней</button><button onClick={() => setPreset(90)}>90 дней</button></div><div className="analytics-date-field"><span>С</span><DateTimePicker value={startDate} onChange={setStartDate} mode="date" label="Дата начала отчёта" /></div><div className="analytics-date-field"><span>По</span><DateTimePicker value={endDate} onChange={setEndDate} mode="date" label="Дата окончания отчёта" /></div><button className="secondary-button" onClick={() => void exportCsv()} disabled={exporting} aria-busy={exporting}><Download size={14} /> {exporting ? "Готовим…" : "Скачать CSV"}</button></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    <section className="analytics-filter-shell" aria-label="Настройки отчёта">
      <div className="analytics-filter-intro"><div><span className="eyebrow">Срез отчёта</span><strong>{hasActiveFilters ? "Показан выбранный срез" : "Сейчас показан весь клуб"}</strong><p>Период: {startDate} — {endDate}. При необходимости сузьте отчёт до зала, оплаты или товара.</p></div><div className="analytics-filter-actions"><button className="secondary-button analytics-filter-toggle" onClick={() => setShowAdvancedFilters((current) => !current)} aria-expanded={showAdvancedFilters}><ListFilter size={15} /> Дополнительные фильтры <ChevronDown size={14} className={showAdvancedFilters ? "is-open" : ""} /></button>{hasActiveFilters && <button className="text-button" onClick={clearAnalyticsFilters}><RotateCcw size={14} /> Сбросить</button>}</div></div>
      {showAdvancedFilters && <div className="analytics-filter-bar" aria-label="Дополнительные фильтры аналитики">
        <label>Зал или зона<input aria-label="Зал или зона" placeholder="например, VIP" value={analyticsFilters.zoneKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, zoneKey: event.target.value || undefined }))} /></label>
        <label>Игровое место<input aria-label="Игровое место" placeholder="например, VIP-01" value={analyticsFilters.workstationKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, workstationKey: event.target.value || undefined }))} /></label>
        <label>Тариф<input aria-label="Тариф" placeholder="например, Ночной" value={analyticsFilters.tariffKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, tariffKey: event.target.value || undefined }))} /></label>
        <label>Группа клиента<input aria-label="Группа клиента" placeholder="например, Постоянные" value={analyticsFilters.clientGroupKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, clientGroupKey: event.target.value || undefined }))} /></label>
        <label>Как оплатили<select aria-label="Как оплатили" value={analyticsFilters.paymentMethodKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, paymentMethodKey: event.target.value || undefined }))}><option value="">Все способы оплаты</option><option value="balance">Депозит</option><option value="cash">Наличные</option><option value="transfer">Перевод</option><option value="mixed">Смешанная оплата</option></select></label>
        <label>Какая операция<select aria-label="Какая операция" value={analyticsFilters.operationType ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, operationType: event.target.value || undefined }))}><option value="">Все операции</option><option value="session">Игровое время</option><option value="product_sale">Продажа товара</option><option value="top_up">Пополнение депозита</option><option value="refund">Возврат</option></select></label>
        <label>Категория товара<input aria-label="Категория товара" placeholder="например, Напитки" value={analyticsFilters.categoryKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, categoryKey: event.target.value || undefined }))} /></label>
        <label>Товар<input aria-label="Товар" placeholder="например, Cola" value={analyticsFilters.productKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, productKey: event.target.value || undefined }))} /></label>
        <label>Оператор<input aria-label="Оператор" placeholder="кто оформил операцию" value={analyticsFilters.operatorKey ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({ ...current, operatorKey: event.target.value || undefined }))} /></label>
      </div>}
    </section>
    <section className="analytics-workspace-bar" aria-label="Разделы аналитики">
      <div className="analytics-tabs" role="tablist" aria-label="Разделы аналитики">
        {[
          ["overview", "Обзор"],
          ["finance", "Деньги"],
          ["occupancy", "Загрузка"],
          ["customers", "Клиенты и товары"],
        ].map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeAnalyticsTab === key} className={activeAnalyticsTab === key ? "selected" : ""} onClick={() => setActiveAnalyticsTab(key as typeof activeAnalyticsTab)}>{label}</button>)}
      </div>
      <button type="button" className={`analytics-comparison-toggle${showComparison ? " selected" : ""}`} aria-pressed={showComparison} onClick={() => setShowComparison((current) => !current)}>
        <TrendingUp size={15} /> Сравнение с прошлым периодом
      </button>
    </section>
    {dashboard?.comparison.is_partial && showComparison && <div className="analytics-state-card" data-state="partial"><strong>Сравнение: неполный период</strong><span>Текущий период ещё не завершён; сравнение с равным предыдущим периодом помечено.</span></div>}
    {dashboard?.blocks.products && <div className="analytics-v2-summary" data-state={dashboard.blocks.products.state}><span>Товары: {stateLabel(dashboard.blocks.products.state)}</span><span>{dashboard.blocks.products.rows.length} товарных позиций</span><button className="text-button" onClick={() => void openDrillDown()} disabled={drillDownLoading}>{drillDownLoading ? "Загружаем…" : "Открыть детализацию"}</button></div>}
    {drillDown && <div className="analytics-drill-down" data-state={drillDown.state}>{drillDown.items.map((item) => <div key={item.source_id}><span>{item.product_name ?? (item.kind === "sale" ? "Продажа" : item.kind === "return" ? "Возврат" : "Корректировка")} · {new Date(item.occurred_at).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span><b>{money(item.amount_cents)}</b></div>)}{drillDown.items.length === 0 && <span>Операций для детализации нет</span>}</div>}
    {loading && <div className="timeline-empty">Собираем показатели…</div>}
    {!loading && !overview && <div className="analytics-state-card" data-state={requestState}><strong>{requestState === "permission_denied" ? "Нет доступа к аналитике" : requestState === "empty" ? "За выбранный период данных нет" : stateLabel(requestState)}</strong><span>{requestState === "error" ? "Повторите запрос позже." : "Показатель не заменяется нулём без подтверждённого факта."}</span></div>}
    {!loading && overview && requestState === "empty" && <div className="analytics-state-card" data-state="empty"><strong>За выбранный период данных нет</strong><span>Доступные показатели не заменяются фиктивными нулями.</span></div>}
    {!loading && overview && requestState === "partial" && <div className="analytics-state-card" data-state="partial"><strong>Частичные данные</strong><span>{overview.data_message ?? "Часть источников текущего v1-контракта недоступна; показатели не дополняются предположениями."}</span></div>}
    {!loading && overview && <div className="analytics-tab-panel" role="tabpanel" aria-label={activeAnalyticsTab === "overview" ? "Обзор" : activeAnalyticsTab === "finance" ? "Деньги" : activeAnalyticsTab === "occupancy" ? "Загрузка" : "Клиенты и товары"} data-tab={activeAnalyticsTab}>
      <div className="analytics-section-heading"><div><p className="eyebrow">Главный экран руководителя</p><h2>Главное за период</h2><p>Сколько заработали, сколько клиентов и насколько занят клуб</p></div><span className="analytics-timezone-note">Время отчёта: Москва</span></div>
      {showComparison && comparisonMetrics.length > 0 && <section className="analytics-comparison-card" aria-label="Графическое сравнение периодов"><div className="analytics-comparison-heading"><div><span className="eyebrow">СРАВНЕНИЕ ПЕРИОДОВ</span><h2>Что изменилось относительно прошлого периода</h2></div><span>Равный предыдущий период</span></div><div className="analytics-comparison-grid">{comparisonMetrics.map((metric) => { const comparison = metric.comparison!; const max = Math.max(1, comparison.current ?? 0, comparison.previous ?? 0); const positive = (comparison.delta ?? 0) >= 0; return <div className="analytics-comparison-metric" key={metric.key}><div><strong>{metric.metric_info.label}</strong><b className={positive ? "positive" : "negative"}>{positive ? "+" : ""}{comparison.change_percent?.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) ?? "—"}%</b></div><div className="analytics-compare-bars"><span style={{ width: `${Math.max(4, ((comparison.current ?? 0) / max) * 100)}%` }} /><i style={{ width: `${Math.max(4, ((comparison.previous ?? 0) / max) * 100)}%` }} /></div><small><em>Сейчас</em>{comparisonValue(metric, comparison.current ?? 0)} <em>Раньше</em>{comparisonValue(metric, comparison.previous ?? 0)}</small></div>; })}</div></section>}
      <div className="metric-grid analytics-metrics analytics-metrics-wide analytics-tab-overview-finance">
        <MetricCard title="Выручка клуба" value={metricValue(money(overview.total_revenue_cents), requestState)} delta={overview.session_count + overview.product_sale_count + " операций"} positive icon={<BarChart3 size={18} />} accent="violet" info={metricInfo.revenue} state={requestState} stateLabel={stateLabel(requestState)} />
        <MetricCard title="Прибыль с товаров" value={metricValue(money(overview.gross_profit_cents), requestState)} delta={`после себестоимости · скидки ${money(overview.discount_cents)}`} positive icon={<TrendingUp size={18} />} accent="green" info={metricInfo.margin} state={requestState} stateLabel={stateLabel(requestState)} />
        <MetricCard title="Игровые часы" value={metricValue(hours(overview.played_minutes), overview.session_count ? requestState : "not_calculated")} delta={`${overview.session_count} завершённых игр`} icon={<Clock3 size={18} />} accent="blue" info={metricInfo.time} state={overview.session_count ? requestState : "not_calculated"} stateLabel={stateLabel(overview.session_count ? requestState : "not_calculated")} />
        <MetricCard title="Занятость компьютеров" value={metricValue(`${overview.occupancy_percent.toLocaleString("ru-RU")}%`, overview.workstation_count ? requestState : "not_available")} delta={`${overview.workstation_count} мест в клубе`} icon={<Computer size={18} />} accent="orange" info={metricInfo.occupancy} state={overview.workstation_count ? requestState : "not_available"} stateLabel={stateLabel(overview.workstation_count ? requestState : "not_available")} />
        <MetricCard title="Клиенты с визитом" value={metricValue(String(overview.active_client_count), requestState)} delta={`${overview.new_client_count} новых`} icon={<Users size={18} />} accent="blue" state={requestState} stateLabel={stateLabel(requestState)} />
        <MetricCard title="Гости без аккаунта" value={metricValue(String(overview.guest_session_count), requestState)} delta={`${overview.unique_visitor_count} всего посетителей`} icon={<Users size={18} />} accent="violet" state={requestState} stateLabel={stateLabel(requestState)} />
        <MetricCard title="Продажи товаров" value={metricValue(money(overview.product_revenue_cents), requestState)} delta={`${overview.product_units} единиц продано`} icon={<ShoppingCart size={18} />} accent="green" state={requestState} stateLabel={stateLabel(requestState)} />
        <MetricCard title="Средняя игра" value={metricValue(`${overview.average_session_minutes.toLocaleString("ru-RU")} мин`, overview.session_count ? requestState : "not_calculated")} delta={`пиковое время ${overview.peak_usage_hour ?? "—"}`} icon={<Wifi size={18} />} accent="orange" state={overview.session_count ? requestState : "not_calculated"} stateLabel={stateLabel(overview.session_count ? requestState : "not_calculated")} />
      </div>
      <div className="analytics-report-grid analytics-tab-overview-finance">
        <section className="white-card analytics-card analytics-chart-card"><div className="section-row"><div><h2>Динамика выручки</h2><p className="section-caption">Сессии и товары по дням выбранного периода</p></div><span className="active-chip">{startDate} — {endDate}</span></div><div className="analytics-chart-legend"><span><i className="session" /> Игровое время</span><span><i className="products" /> Товары</span></div><div className="analytics-chart">{overview.daily_activity.map((item) => <div className="analytics-chart-column" key={item.key}><div className="analytics-chart-bars"><i className="session" style={{ height: `${Math.max(item.session_revenue_cents ? 5 : 0, item.session_revenue_cents / maxDailyRevenue * 100)}%` }} /><i className="products" style={{ height: `${Math.max(item.product_revenue_cents ? 5 : 0, item.product_revenue_cents / maxDailyRevenue * 100)}%` }} /></div><span>{item.label}</span></div>)}</div></section>
        <section className="white-card analytics-card analytics-insights"><div className="section-row"><div><h2>Сводка периода</h2><p className="section-caption">Ключевые операционные сигналы</p></div></div><div className="analytics-insight-list"><div><span>Новые клиенты</span><strong>{overview.new_client_count}</strong></div><div><span>Вернувшиеся клиенты</span><strong>{overview.returning_client_count}</strong></div><div><span>Товарная себестоимость</span><strong>{money(overview.product_cost_cents)}</strong></div><div><span>Пиковый час</span><strong>{overview.peak_usage_hour ?? "Нет данных"}</strong></div><div><span>Продажи / сессии</span><strong>{overview.product_sale_count} / {overview.session_count}</strong></div></div></section>
      </div>
      <div className="analytics-report-grid analytics-tab-overview-occupancy">
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Загрузка по часам</h2><p className="section-caption">Когда клуб наиболее загружен</p></div></div><div className="analytics-hourly-chart">{overview.hourly_activity.map((item) => <div className="analytics-hour-column" key={item.key} title={`${item.label}: ${hours(item.played_minutes)}`}><i style={{ height: `${Math.max(item.played_minutes ? 5 : 2, item.played_minutes / maxHourlyMinutes * 100)}%` }} /><span>{Number(item.key) % 3 === 0 ? item.label : ""}</span></div>)}</div></section>
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Способы оплаты</h2><p className="section-caption">Распределение подтверждённой выручки</p></div></div>{overview.payment_methods.length ? <div className="analytics-payment-list">{overview.payment_methods.map((item) => <div className="analytics-payment-row" key={item.key}><div><strong>{item.label}</strong><span>{item.operation_count} операций · {item.share_bps / 100}%</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Оплат за период нет</div>}</section>
      </div>
      <div className="analytics-breakdown-grid analytics-tab-overview-occupancy"><section className="white-card analytics-card"><div className="section-row"><div><h2>Зоны клуба</h2><p className="section-caption">Загрузка и выручка по залам</p></div></div>{breakdown(overview.zones, "Сессий по зонам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Игровые места</h2><p className="section-caption">Какие ПК используются чаще</p></div></div>{breakdown(overview.workstations, "Данных по местам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Тарифы</h2><p className="section-caption">Продажи игрового времени</p></div></div>{breakdown(overview.tariffs, "Тарифы за период не продавались")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Категории товаров</h2><p className="section-caption">Выручка, себестоимость и маржа</p></div></div>{breakdown(overview.product_categories, "Продаж по категориям нет", "products")}</section></div>
      <div className="analytics-grid analytics-tab-overview-customers"><section className="white-card analytics-card"><div className="section-row"><div><h2>Популярные товары</h2><p className="section-caption">Количество, выручка и маржа по snapshots</p></div><span className="active-chip">{overview.product_sale_count} продаж</span></div>{overview.top_products.length ? <div className="analytics-list">{overview.top_products.map((item) => <div className="analytics-list-row" key={item.product_id + item.product_name}><div><strong>{item.product_name}</strong><span>{item.units} шт. · маржа {money(item.gross_profit_cents)}</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Продаж за период нет</div>}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Лучшие клиенты</h2><p className="section-caption">Игровое время, товары и общие траты</p></div><span className="active-chip">{overview.active_client_count} активных</span></div>{overview.top_clients.length ? <div className="analytics-list">{overview.top_clients.map((item) => <button className="analytics-list-row analytics-client-row" key={item.client_id} onClick={() => openClient(item.client_id)}><div><strong>{item.nickname}</strong><span>{hours(item.played_minutes)} · {item.session_count} сессий · товары {money(item.product_spend_cents)}</span></div><b>{money(item.total_spend_cents)}</b></button>)}</div> : <div className="timeline-empty">Активности клиентов за период нет</div>}</section></div>
    </div>}
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
