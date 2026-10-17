import { BonusAnalytics } from "./BonusAnalytics";
import { useEffect, useState } from "react";
import {
  ArrowDownLeft,
  Banknote,
  BarChart3,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Clock3,
  Computer,
  CreditCard,
  Download,
  ListFilter,
  Plus,
  RefreshCw,
  RotateCcw,
  Shield,
  ShoppingCart,
  TrendingUp,
  Users,
  Wifi,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type {
  BackendAnalyticsDrillDown,
  BackendAnalyticsFinanceResponse,
  BackendAnalyticsOverview,
  BackendAnalyticsV2Dashboard,
  BackendAuditEvent,
  BackendClientGroup,
  BackendPaymentMethod,
  BackendProduct,
  BackendProductCategory,
  BackendTariff,
  BackendWorkstationGroup,
  Reservation,
} from "../../api";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { MetricCard } from "../../shared/components/MetricCard";
import { Segmented } from "../../shared/components/Segmented";
import {
  getAnalyticsDataState,
  getAnalyticsDateInputValue,
  getAnalyticsPeriodBounds,
  isEmptyOverview,
  stateLabel,
  type AnalyticsDataState,
} from "./analytics";
import { PcGrid } from "../workstations/PcGrid";
import {
  AnalyticsComparison,
  AnalyticsReportContent,
} from "./AnalyticsReports";
import type { Client, Workstation } from "../../types";

type DashboardProps = {
  onDeposit: () => void;
  onOpenCash: () => void;
  onOpenMap: () => void;
  onOpenBookings: () => void;
  onPc: (pc: Workstation) => void;
  pcs: Workstation[];
  clients: Client[];
  reservations: Reservation[];
  auditEvents: BackendAuditEvent[];
  liveMode: boolean;
  revenueCents: number | null;
  revenueChargeCount: number;
  group: string;
  setGroup: (group: string) => void;
  zoneOptions: string[];
};
type AnalyticsTab = "overview" | "finance" | "occupancy" | "customers";
type AnalyticsFilterValues = {
  equipmentType?: "pc" | "xbox";
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
type AnalyticsPreset = "today" | "week" | "month" | "quarter" | "year" | null;

function DemoAnalytics() {
  const metricCards = [
    [
      "Выручка клуба",
      "5 131 ₽",
      "Наличные · Платежи · Бонусы",
      <Banknote size={18} />,
    ],
    ["Игровое время", "114,6 ч", "50 сессий", <Clock3 size={18} />],
    [
      "Средняя сессия",
      "116,54 мин",
      "Пиковый час: 08:00",
      <Clock3 size={18} />,
    ],
    ["Занятость мест", "2,65%", "6 мест в клубе", <Computer size={18} />],
    ["Клиенты с визитами", "5", "1 постоянный", <Users size={18} />],
  ] as const;
  const facts = [
    ["Пополнения депозита", "3", "375 ₽"],
    ["Новые клиенты", "7", ""],
    ["Вернувшиеся клиенты", "1", ""],
    ["Гости", "1", ""],
    ["Прибыль с товаров", "", "3 ₽"],
    ["Пиковый час", "", "08:00"],
  ];
  const rows = [
    ["Avalonia Linux smoke", "57", "114,6 ч", "96%"],
    ["VIP02", "1", "0,1 ч", "4%"],
    ["VIP01", "1", "0,1 ч", "4%"],
  ];
  return (
    <>
      <div
        className="relative mb-2 min-h-36 overflow-hidden rounded-2xl border border-primary/15! bg-base-100/20! p-5"
        style={{
          backgroundImage:
            "linear-gradient(90deg, rgba(4,18,20,.44), rgba(4,18,20,.06) 58%, rgba(4,18,20,.02)), url(/neon-club-room.png)",
          backgroundPosition: "center 42%",
          backgroundSize: "cover",
          backgroundRepeat: "no-repeat",
        }}
      >
        <div className="relative z-10">
          <h1 className="text-2xl font-bold tracking-tight">Отчёты</h1>
          <p className="mt-1 text-sm text-base-content/70!">
            Период: 2026-09-04 — 2026-10-03
          </p>
        </div>
        <div className="relative z-10 grid w-full max-w-xl grid-cols-3 gap-2 lg:absolute lg:right-5 lg:top-5 lg:w-[25rem]">
          <div className="join col-span-3 rounded-lg border border-primary/20! bg-base-100/55! p-1 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <button className="btn btn-ghost btn-sm join-item">Неделя</button>
            <button className="btn btn-primary btn-sm join-item">Месяц</button>
            <button className="btn btn-ghost btn-sm join-item">Квартал</button>
            <button className="btn btn-ghost btn-sm join-item">Год</button>
          </div>
          <label className="input input-sm flex items-center border-primary/20! bg-base-100/55! text-xs text-base-content/60!">
            С
            <input
              className="w-full bg-transparent text-right text-xs text-base-content!"
              value="04 сент. 2026 г."
              readOnly
            />
          </label>
          <label className="input input-sm flex items-center border-primary/20! bg-base-100/55! text-xs text-base-content/60!">
            По
            <input
              className="w-full bg-transparent text-right text-xs text-base-content!"
              value="03 окт. 2026 г."
              readOnly
            />
          </label>
          <button className="btn btn-outline btn-sm">
            <RefreshCw size={14} /> Обновить
          </button>
          <button className="btn btn-outline btn-sm">
            <Download size={14} /> Скачать CSV
          </button>
          <button className="btn btn-outline btn-sm">
            <ListFilter size={14} /> Фильтры
          </button>
        </div>
        <div className="absolute bottom-0 left-5 z-10 max-w-[44%] rounded-xl border border-primary/20! bg-base-100/45! px-4 py-3 backdrop-blur-md">
          <strong className="text-sm">Весь клуб</strong>
          <p className="mt-1 text-xs text-base-content/65!">
            Все залы, игровые места и способы оплаты.
          </p>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-primary/20! bg-base-100/55! p-1 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
        <div className="join overflow-x-auto">
          <button className="btn btn-primary btn-sm join-item">Обзор</button>
          <button className="btn btn-ghost btn-sm join-item">
            Посещаемость
          </button>
          <button className="btn btn-ghost btn-sm join-item">Занятость</button>
          <button className="btn btn-ghost btn-sm join-item">Продажи</button>
        </div>
        <button className="btn btn-ghost btn-sm">
          <BarChart3 size={14} /> Сравнить периоды
        </button>
      </div>
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {metricCards.map(([title, value, delta, icon]) => (
          <MetricCard
            title={title}
            value={value}
            delta={delta}
            icon={icon}
            accent="green"
            positive
            dense
            key={title}
          />
        ))}
      </div>
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">Операции по дням</h2>
              <p className="text-xs text-base-content/60!">
                Списание за игры и суммы продаж показаны отдельно в признанном
                доходе.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs text-base-content/60!">
              <span className="inline-flex items-center gap-1.5">
                <i className="size-2 rounded-full bg-primary" /> Списания за
                игры
              </span>
              <span className="inline-flex items-center gap-1.5">
                <i className="size-2 rounded-full bg-info" /> Сумма продаж
                товаров
              </span>
            </div>
          </div>
          <div className="mt-1 h-36 rounded-lg border border-primary/15! bg-base-200/45 p-3 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <svg
              className="h-full w-full"
              viewBox="0 0 1000 220"
              preserveAspectRatio="none"
              aria-label="Операции по дням"
            >
              <g className="stroke-base-content/15" strokeWidth="1">
                <line x1="0" y1="40" x2="1000" y2="40" />
                <line x1="0" y1="80" x2="1000" y2="80" />
                <line x1="0" y1="120" x2="1000" y2="120" />
                <line x1="0" y1="160" x2="1000" y2="160" />
                <line x1="0" y1="200" x2="1000" y2="200" />
              </g>
              <path
                d="M0 190 L45 190 L90 170 L135 120 L180 150 L225 175 L270 160 L315 170 L360 140 L405 125 L450 105 L495 165 L540 180 L585 115 L630 135 L675 65 L720 95 L765 35 L810 105 L855 145 L900 145 L945 195 L1000 190"
                className="fill-none stroke-primary stroke-2"
              />
              <path
                d="M0 190 L45 190 L90 170 L135 120 L180 150 L225 175 L270 160 L315 170 L360 140 L405 125 L450 105 L495 165 L540 180 L585 115 L630 135 L675 65 L720 95 L765 35 L810 105 L855 145 L900 145 L945 195 L1000 190 L1000 220 L0 220 Z"
                className="fill-primary/10"
              />
              <path
                d="M0 215 L100 215 L200 214 L300 216 L400 213 L500 215 L600 214 L700 215 L800 214 L900 216 L1000 213"
                className="fill-none stroke-info stroke-2"
              />
              <g className="fill-base-content/45 text-[12px]">
                <text x="8" y="215">
                  0 ₽
                </text>
                <text x="130" y="215">
                  07.09
                </text>
                <text x="330" y="215">
                  15.09
                </text>
                <text x="530" y="215">
                  23.09
                </text>
                <text x="730" y="215">
                  01.10
                </text>
                <text x="900" y="215">
                  03.10
                </text>
              </g>
            </svg>
          </div>
        </section>
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div>
            <h2 className="font-semibold">За этот период</h2>
            <p className="text-xs text-base-content/60!">
              Клиенты, товары и часы пик
            </p>
          </div>
          <dl className="grid gap-0">
            {facts.map(([label, value, amount], index) => (
              <div
                className="flex items-center gap-2 border-b border-primary/10! px-1 py-0 last:border-b-0"
                key={label}
              >
                <span className="grid size-5 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                  {index === 0 ? (
                    <Banknote size={16} />
                  ) : index === 5 ? (
                    <Clock3 size={16} />
                  ) : (
                    <Users size={16} />
                  )}
                </span>
                <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                  {label}
                </dt>
                <dd className="text-sm font-semibold">
                  {value} {amount}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      </div>
      <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <Computer size={16} />
            </span>
            <div>
              <h2 className="font-semibold">Загрузка по игровым местам</h2>
              <p className="text-xs text-base-content/60!">
                Число сессий и игровое время
              </p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="table table-xs w-full text-xs">
              <thead>
                <tr>
                  <th>Место или зал</th>
                  <th>Сессии</th>
                  <th>Игровое время</th>
                  <th>Загрузка</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([name, sessions, hours, load]) => (
                  <tr key={name}>
                    <th>{name}</th>
                    <td>{sessions}</td>
                    <td>{hours}</td>
                    <td>
                      <progress
                        className="progress progress-primary h-1.5 w-24"
                        value={Number.parseInt(load)}
                        max="100"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <ShoppingCart size={16} />
            </span>
            <div>
              <h2 className="font-semibold">Продажи по товарам</h2>
              <p className="text-xs text-base-content/60!">
                Количество, выручка и прибыль
              </p>
            </div>
          </div>
          <table className="table table-xs w-full text-xs">
            <thead>
              <tr>
                <th>Товар</th>
                <th>Продано</th>
                <th>Сумма</th>
                <th>Прибыль</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Smoke juice 192557</th>
                <td>2 шт.</td>
                <td>5 ₽</td>
                <td>3 ₽</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <CreditCard size={16} />
            </span>
            <div>
              <h2 className="font-semibold">Выручка по способам оплаты</h2>
              <p className="text-xs text-base-content/60!">
                Подтверждённые операции за период
              </p>
            </div>
          </div>
          <table className="table table-xs w-full text-xs">
            <thead>
              <tr>
                <th>Способ оплаты</th>
                <th>Операций</th>
                <th>Доля</th>
                <th>Сумма</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Наличные</th>
                <td>31</td>
                <td>96,88%</td>
                <td>4 966 ₽</td>
              </tr>
              <tr>
                <th>Перевод</th>
                <td>2</td>
                <td>3,61%</td>
                <td>185 ₽</td>
              </tr>
            </tbody>
          </table>
        </section>
        <section className="card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <Users size={16} />
            </span>
            <div>
              <h2 className="font-semibold">Активные клиенты</h2>
              <p className="text-xs text-base-content/60!">
                Игровое время и покупки за период
              </p>
            </div>
          </div>
          <table className="table table-xs w-full text-xs">
            <thead>
              <tr>
                <th>Клиент</th>
                <th>Сессии</th>
                <th>Игровое время</th>
                <th>Товары</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>DanielBarutov</th>
                <td>54</td>
                <td>114,6 ч</td>
                <td>0 ₽</td>
              </tr>
              <tr>
                <th>test</th>
                <td>1</td>
                <td>0 ч</td>
                <td>0 ₽</td>
              </tr>
              <tr>
                <th>live-v2-accepted-c0a8b4e2</th>
                <td>1</td>
                <td>0,1 ч</td>
                <td>0 ₽</td>
              </tr>
              <tr>
                <th>persist-key-a5c0a026</th>
                <td>1</td>
                <td>0,1 ч</td>
                <td>0 ₽</td>
              </tr>
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}

export function AnalyticsView({
  api,
  clients: clientList,
  onClient,
  paymentMethods = [],
  workstations = [],
  groups = [],
  tariffs = [],
  clientGroups = [],
  productCategories = [],
  products = [],
}: {
  api?: GameClubApi;
  clients: Client[];
  onClient: (client: Client) => void;
  paymentMethods?: BackendPaymentMethod[];
  workstations?: Workstation[];
  groups?: BackendWorkstationGroup[];
  tariffs?: BackendTariff[];
  clientGroups?: BackendClientGroup[];
  productCategories?: BackendProductCategory[];
  products?: BackendProduct[];
}) {
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - 29);
    return getAnalyticsDateInputValue(date);
  });
  const [endDate, setEndDate] = useState(() => getAnalyticsDateInputValue());
  const [activePreset, setActivePreset] = useState<AnalyticsPreset>("month");
  const [overview, setOverview] = useState<BackendAnalyticsOverview | null>(
    null,
  );
  const [finance, setFinance] =
    useState<BackendAnalyticsFinanceResponse | null>(null);
  const [financeError, setFinanceError] = useState(false);
  const [financeLoading, setFinanceLoading] = useState(false);
  const [dashboard, setDashboard] =
    useState<BackendAnalyticsV2Dashboard | null>(null);
  const [drillDown, setDrillDown] = useState<BackendAnalyticsDrillDown | null>(
    null,
  );
  const [drillDownLoading, setDrillDownLoading] = useState(false);
  const [analyticsFilters, setAnalyticsFilters] =
    useState<AnalyticsFilterValues>({});
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [activeAnalyticsTab, setActiveAnalyticsTab] =
    useState<AnalyticsTab>("overview");
  const [showComparison, setShowComparison] = useState(false);
  const [occupancyScope, setOccupancyScope] = useState<
    "workstations" | "zones"
  >("workstations");
  const [occupancyMeasure, setOccupancyMeasure] = useState<"time" | "revenue">(
    "time",
  );
  const [error, setError] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<AnalyticsDataState>(
    api ? "loading" : "empty",
  );
  const [exporting, setExporting] = useState(false);
  const [refreshGeneration, setRefreshGeneration] = useState(0);

  useEffect(() => {
    if (!api) {
      setRequestState("empty");
      return undefined;
    }
    let active = true;
    setRequestState("loading");
    setDashboard(null);
    setFinance(null);
    setFinanceError(false);
    const { startAt, endAt } = getAnalyticsPeriodBounds(startDate, endDate);
    const reportFilters = { startAt, endAt, ...analyticsFilters };
    void api
      .getAnalyticsOverview(startAt, endAt, 8)
      .then((result) => {
        if (active) {
          setOverview(result);
          setError(null);
          setRequestState(
            result.data_state ?? (isEmptyOverview(result) ? "empty" : "ready"),
          );
        }
      })
      .catch((requestError) => {
        if (active) {
          setOverview(null);
          setError(
            requestError instanceof ApiError
              ? requestError.message
              : "Не удалось загрузить аналитику",
          );
          setRequestState(getAnalyticsDataState({ error: requestError }));
        }
      });
    if (typeof api.getAnalyticsFinance === "function") {
      setFinanceLoading(true);
      void api
        .getAnalyticsFinance(reportFilters)
        .then((result) => {
          if (active) {
            setFinance(result);
            setFinanceLoading(false);
          }
        })
        .catch(() => {
          if (active) {
            setFinanceError(true);
            setFinanceLoading(false);
          }
        });
    } else {
      setFinanceLoading(false);
    }
    if (typeof api.getAnalyticsDashboard === "function") {
      void api
        .getAnalyticsDashboard({ ...reportFilters, comparison: showComparison })
        .then((result) => {
          if (active) setDashboard(result);
        })
        .catch(() => {
          if (active) setDashboard(null);
        });
    }
    return () => {
      active = false;
    };
  }, [
    api,
    startDate,
    endDate,
    analyticsFilters,
    showComparison,
    refreshGeneration,
  ]);

  const money = (cents: number) => (cents / 100).toLocaleString("ru-RU") + " ₽";
  const hours = (minutes: number) =>
    (minutes / 60).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " ч";
  const openClient = (id: string) => {
    const client = clientList.find((item) => item.id === id);
    if (client) onClient(client);
  };
  const setPreset = (
    period: "today" | "week" | "month" | "quarter" | "year",
  ) => {
    const endDate = getAnalyticsDateInputValue();
    const start = new Date(`${endDate}T00:00:00Z`);
    if (period === "today") start.setUTCDate(start.getUTCDate());
    if (period === "week") start.setUTCDate(start.getUTCDate() - 6);
    if (period === "month") start.setUTCDate(1);
    if (period === "quarter") {
      start.setUTCMonth(Math.floor(start.getUTCMonth() / 3) * 3, 1);
    }
    if (period === "year") start.setUTCMonth(0, 1);
    setStartDate(start.toISOString().slice(0, 10));
    setEndDate(endDate);
    setActivePreset(period);
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
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось выгрузить аналитику",
      );
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
      setDrillDown(
        await api.getAnalyticsDrillDown({
          startAt,
          endAt,
          limit: 100,
          ...analyticsFilters,
        }),
      );
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось загрузить детализацию",
      );
    } finally {
      setDrillDownLoading(false);
    }
  };
  const hasActiveFilters = Object.values(analyticsFilters).some(Boolean);
  const clearAnalyticsFilters = () => setAnalyticsFilters({});
  if (!api) return <DemoAnalytics />;
  const loading = requestState === "loading";
  const hasFinanceActivity =
    finance !== null &&
    [
      finance.flow.payment_received_cents,
      finance.flow.deposit_top_up_revenue_cents,
      finance.flow.refunds_cents,
      finance.flow.adjustments_cents,
    ].some((value) => value !== null && value !== 0);
  const reportState =
    requestState === "empty" && financeLoading
      ? "loading"
      : requestState === "empty" && hasFinanceActivity
        ? "ready"
        : requestState;
  const metricInfo = {
    revenue: {
      description: "Полученные платежи и пополнения за вычетом возвратов.",
      formula:
        "Платежи + пополнения депозита − возвраты. Списания с депозита повторно не учитываются.",
      source: "Подтверждённые финансовые операции.",
      emptyState: "Финансовые данные за этот период недоступны.",
    },
    depositTopUps: {
      description: "Пополнения признаются доходом в день поступления денег.",
      formula: "Сумма подтверждённых пополнений за период.",
      source: "Пополнения баланса клиентов.",
      emptyState: "Нет данных о пополнениях за этот период.",
    },
    margin: {
      description: "Прибыль от продажи товаров после закупки.",
      formula: "Выручка от товаров минус их себестоимость.",
      source: "Продажи товаров и закупочные цены.",
      emptyState: "Нет данных о себестоимости товаров.",
    },
    time: {
      description: "Суммарное время завершённых игровых сессий.",
      formula: "Минуты всех сессий за выбранный период.",
      source: "Завершённые игровые сессии.",
      emptyState: "За этот период завершённых сессий нет.",
    },
    occupancy: {
      description: "Какую часть доступного времени места были заняты.",
      formula: "Занятое время относительно доступного времени.",
      source: "Игровые сессии и список мест клуба.",
      emptyState: "Нет данных о доступности мест за этот период.",
    },
    sessions: {
      description: "Количество завершённых игровых сессий.",
      formula: "Сессии, завершённые за выбранный период.",
      source: "Игровые сессии клуба.",
      emptyState: "За этот период завершённых сессий нет.",
    },
    averageSession: {
      description: "Средняя длительность одной игровой сессии.",
      formula: "Игровое время, разделённое на число завершённых сессий.",
      source: "Игровые сессии клуба.",
      emptyState: "Нет завершённых сессий для расчёта.",
    },
    clients: {
      description: "Зарегистрированные клиенты, игравшие в выбранный период.",
      formula: "Число активных клиентов за период.",
      source: "Игровые сессии клиентов.",
      emptyState: "Зарегистрированных клиентов с визитом нет.",
    },
    returningClients: {
      description: "Клиенты, которые уже посещали клуб раньше.",
      formula: "Клиенты, вернувшиеся в выбранный период.",
      source: "История игровых сессий.",
      emptyState: "Вернувшихся клиентов за период нет.",
    },
    guests: {
      description: "Сессии гостей без аккаунта клиента.",
      formula: "Гостевые сессии за выбранный период.",
      source: "Игровые сессии гостей.",
      emptyState: "Гостевых сессий за период нет.",
    },
    productRevenue: {
      description: "Деньги, полученные от продажи товаров.",
      formula: "Подтверждённая выручка от товаров за период.",
      source: "Продажи товаров клуба.",
      emptyState: "Продаж товаров за этот период нет.",
    },
    productSales: {
      description: "Количество товарных продаж.",
      formula: "Завершённые продажи товаров за период.",
      source: "Продажи товаров клуба.",
      emptyState: "Продаж товаров за этот период нет.",
    },
  };
  const comparisonMetrics = Object.values(dashboard?.blocks ?? {})
    .flatMap((block) => Object.values(block.metrics))
    .filter(
      (metric) =>
        metric.comparison !== null &&
        metric.comparison.current !== null &&
        metric.comparison.previous !== null,
    )
    .slice(0, 4);
  const comparisonValue = (
    metric: (typeof comparisonMetrics)[number],
    value: number,
  ) => {
    const key = metric.key.toLowerCase();
    if (
      key.includes("revenue") ||
      key.includes("money") ||
      key.includes("payment") ||
      key.includes("deposit")
    )
      return money(value);
    if (key.includes("occupancy") || key.includes("margin"))
      return `${value.toLocaleString("ru-RU")}%`;
    if (key.includes("minute")) return `${value.toLocaleString("ru-RU")} мин`;
    return value.toLocaleString("ru-RU");
  };
  const reportLabels: Record<
    AnalyticsTab,
    { label: string; title: string; description: string }
  > = {
    overview: {
      label: "Обзор",
      title: "Обзор клуба",
      description: "Выручка, игровые часы и загрузка мест за выбранный период.",
    },
    customers: {
      label: "Посещаемость",
      title: "Посещаемость",
      description: "Клиенты, гости и игровые сессии по дням.",
    },
    occupancy: {
      label: "Занятость",
      title: "Занятость оборудования",
      description: "Игровое время и выручка по местам и залам.",
    },
    finance: {
      label: "Продажи",
      title: "Продажи",
      description: "Выручка, товарные продажи и способы оплаты.",
    },
  };
  const selectedReport = reportLabels[activeAnalyticsTab];
  return (
    <>
      <div className="relative mt-7 mb-11 flex flex-wrap items-start justify-between gap-4">
        <div className="relative z-10 flex items-start gap-3">
          <div>
            <p className="mb-1 text-sm text-primary/80!">Аналитика · Отчеты</p>
            <h1 className="text-3xl font-bold tracking-tight">Аналитика</h1>
            <p className="mt-1 text-sm text-base-content/65!">
              Наличные операции хранятся отдельно от депозитов клиентов и оплаты
              игрового времени.
            </p>
          </div>
        </div>
      </div>
      <div className="heading-actions analytics-period relative z-10 grid w-full max-w-xl grid-cols-2 gap-2 lg:absolute lg:right-[5%] lg:top-[100px] lg:w-auto">
        <div
          className="analytics-presets join col-span-2 rounded-lg border border-primary/20! bg-base-100/55! p-1 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
          role="group"
          aria-label="Быстрый выбор периода"
        >
          <button
            className={`join-item btn btn-sm ${activePreset === "today" ? "btn-primary text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
            type="button"
            onClick={() => setPreset("today")}
          >
            Сегодня
          </button>
          <button
            className={`join-item btn btn-sm ${activePreset === "week" ? "btn-primary text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
            type="button"
            onClick={() => setPreset("week")}
          >
            Неделя
          </button>
          <button
            className={`join-item btn btn-sm ${activePreset === "month" ? "btn-primary text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
            type="button"
            onClick={() => setPreset("month")}
          >
            Месяц
          </button>
          <button
            className={`join-item btn btn-sm ${activePreset === "quarter" ? "btn-primary text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
            type="button"
            onClick={() => setPreset("quarter")}
          >
            Квартал
          </button>
          <button
            className={`join-item btn btn-sm ${activePreset === "year" ? "btn-primary text-primary-content!" : "btn-ghost text-base-content/70! hover:bg-primary/15! hover:text-primary!"}`}
            type="button"
            onClick={() => setPreset("year")}
          >
            Год
          </button>
        </div>
        <label className="analytics-date-field flex min-w-0 flex-col gap-1 text-xs text-base-content/60!">
          С
          <DateTimePicker
            value={startDate}
            onChange={(value) => {
              setStartDate(value);
              setActivePreset(null);
            }}
            mode="date"
            label="Дата начала отчёта"
          />
        </label>
        <label className="analytics-date-field flex min-w-0 flex-col gap-1 text-xs text-base-content/60!">
          По
          <DateTimePicker
            value={endDate}
            onChange={(value) => {
              setEndDate(value);
              setActivePreset(null);
            }}
            mode="date"
            label="Дата окончания отчёта"
          />
        </label>
        <button
          className="secondary-button btn btn-outline btn-sm"
          type="button"
          onClick={() => setRefreshGeneration((value) => value + 1)}
          disabled={loading || financeLoading}
          aria-busy={loading || financeLoading}
        >
          <RefreshCw size={14} />{" "}
          {loading || financeLoading ? "Обновляем…" : "Обновить"}
        </button>
        <button
          className="secondary-button btn btn-outline btn-sm"
          onClick={() => void exportCsv()}
          disabled={exporting}
          aria-busy={exporting}
        >
          <Download size={14} /> {exporting ? "Готовим…" : "Скачать CSV"}
        </button>
      </div>

      {error && (
        <div
          className="mb-3 rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {error}
        </div>
      )}
      {financeError && (
        <div
          className="flex flex-col gap-1 rounded-xl border border-error/35! bg-error/10! p-4 text-sm"
          data-state="error"
          role="status"
        >
          <strong>Не удалось обновить финансовые данные</strong>
          <span>Нажмите «Обновить», чтобы повторить запрос.</span>
        </div>
      )}
      <section
        className="analytics-filter-shell mb-3 rounded-xl border border-primary/20! bg-base-100/70! p-3 text-base-content! shadow-[0_0_20px_rgba(49,217,120,0.06)] lg:max-w-[64%]"
        aria-label="Настройки отчёта"
      >
        <div className="analytics-filter-intro flex items-center justify-between gap-4">
          <div>
            <strong className="text-sm">
              {hasActiveFilters ? "Фильтры применены" : "Весь клуб"}
            </strong>
            <p className="mt-1 text-xs text-base-content/65!">
              {hasActiveFilters
                ? "Показаны данные по выбранным параметрам."
                : "Все залы, игровые места и способы оплаты."}
            </p>
          </div>
          <div className="analytics-filter-actions flex flex-wrap items-center justify-end gap-2">
            <button
              className="secondary-button analytics-filter-toggle btn btn-outline btn-sm"
              onClick={() => setShowAdvancedFilters((current) => !current)}
              aria-expanded={showAdvancedFilters}
            >
              <ListFilter size={15} /> Фильтры{" "}
              <ChevronDown
                size={14}
                className={showAdvancedFilters ? "is-open rotate-180" : ""}
              />
            </button>
            {hasActiveFilters && (
              <button
                className="text-button btn btn-ghost btn-sm text-primary!"
                onClick={clearAnalyticsFilters}
              >
                <RotateCcw size={14} /> Сбросить
              </button>
            )}
          </div>
        </div>
        {showAdvancedFilters && (
          <div
            className="analytics-filter-bar mt-4 grid grid-cols-1 gap-3 border-t border-primary/15! pt-4 sm:grid-cols-2 lg:grid-cols-3 [&>label]:flex [&>label]:flex-col [&>label]:gap-1 [&>label]:text-xs [&>label]:text-base-content/60!"
            aria-label="Дополнительные фильтры аналитики"
          >
            <label>
              Тип оборудования (финансы)
              <select className="select select-sm" value={analyticsFilters.equipmentType ?? ""} onChange={(event) => setAnalyticsFilters((current) => ({...current, equipmentType: (event.target.value || undefined) as "pc" | "xbox" | undefined}))}>
                <option value="">Все</option><option value="pc">ПК</option><option value="xbox">Xbox</option>
              </select>
            </label>
            <label>
              Зал или зона
              <select
                className="select select-sm"
                aria-label="Зал или зона"
                value={analyticsFilters.zoneKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    zoneKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все залы и зоны</option>
                {groups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Игровое место
              <select
                className="select select-sm"
                aria-label="Игровое место"
                value={analyticsFilters.workstationKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    workstationKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все игровые места</option>
                {workstations.map((workstation) => (
                  <option key={workstation.id} value={workstation.id}>
                    {workstation.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Тариф
              <select
                className="select select-sm"
                aria-label="Тариф"
                value={analyticsFilters.tariffKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    tariffKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все тарифы</option>
                {tariffs.map((tariff) => (
                  <option key={tariff.id} value={tariff.id}>
                    {tariff.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Группа клиента
              <select
                className="select select-sm"
                aria-label="Группа клиента"
                value={analyticsFilters.clientGroupKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    clientGroupKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все группы клиентов</option>
                {clientGroups.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Как оплатили
              <select
                className="select select-sm"
                aria-label="Как оплатили"
                value={analyticsFilters.paymentMethodKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    paymentMethodKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все способы оплаты</option>
                {paymentMethods
                  .filter((method) => method.active)
                  .map((method) => (
                    <option key={method.id} value={method.key}>
                      {method.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Какая операция
              <select
                className="select select-sm"
                aria-label="Какая операция"
                value={analyticsFilters.operationType ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    operationType: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все операции</option>
                <option value="session">Игровое время</option>
                <option value="product_sale">Продажа товара</option>
                <option value="top_up">Пополнение депозита</option>
                <option value="refund">Возврат</option>
              </select>
            </label>
            <label>
              Категория товара
              <select
                className="select select-sm"
                aria-label="Категория товара"
                value={analyticsFilters.categoryKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    categoryKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все категории</option>
                {productCategories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Товар
              <select
                className="select select-sm"
                aria-label="Товар"
                value={analyticsFilters.productKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    productKey: event.target.value || undefined,
                  }))
                }
              >
                <option value="">Все товары</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Оператор
              <input
                className="input input-sm"
                aria-label="Оператор"
                placeholder="кто оформил операцию"
                value={analyticsFilters.operatorKey ?? ""}
                onChange={(event) =>
                  setAnalyticsFilters((current) => ({
                    ...current,
                    operatorKey: event.target.value || undefined,
                  }))
                }
              />
            </label>
          </div>
        )}
      </section>
      <section
        className="analytics-workspace-bar mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/20! bg-base-100/55! p-1 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]"
        aria-label="Виды отчёта"
      >
        <div
          className="analytics-tabs flex min-w-0 gap-1 overflow-x-auto"
          role="tablist"
          aria-label="Виды отчёта"
        >
          {(
            ["overview", "customers", "occupancy", "finance"] as AnalyticsTab[]
          ).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={activeAnalyticsTab === key}
              className={`btn btn-sm ${activeAnalyticsTab === key ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70!"}`}
              onClick={() => setActiveAnalyticsTab(key)}
            >
              {reportLabels[key].label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className={`analytics-comparison-toggle btn btn-sm gap-2 ${showComparison ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost text-base-content/70!"}`}
          aria-pressed={showComparison}
          onClick={() => setShowComparison((current) => !current)}
        >
          <TrendingUp size={15} /> Сравнить периоды
        </button>
      </section>
      {loading && (
        <div
          className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×']"
          role="status"
        >
          Загружаем отчёт…
        </div>
      )}
      {!loading && !overview && (
        <div
          className="flex flex-col gap-1 rounded-xl border border-primary/20! bg-base-100/55! p-4 text-sm"
          data-state={requestState}
        >
          <strong>
            {requestState === "permission_denied"
              ? "Нет доступа к аналитике"
              : requestState === "empty"
                ? "За выбранный период данных нет"
                : stateLabel(requestState)}
          </strong>
          <span>
            {requestState === "error"
              ? "Повторите запрос позже."
              : "Нет подтверждённых данных для выбранного периода."}
          </span>
        </div>
      )}
      {!loading && overview && reportState === "empty" && (
        <div
          className="flex flex-col gap-1 rounded-xl border border-primary/20! bg-base-100/55! p-4 text-sm"
          data-state="empty"
        >
          <strong>За выбранный период данных нет</strong>
          <span>Попробуйте выбрать другой период.</span>
        </div>
      )}
      {!loading && overview && reportState === "partial" && (
        <div
          className="flex flex-col gap-1 rounded-xl border border-warning/35! bg-warning/10! p-4 text-sm"
          data-state="partial"
        >
          <strong>Отчёт загружен частично</strong>
          <span>
            {overview.data_message ??
              "Некоторые источники данных пока недоступны."}
          </span>
        </div>
      )}
      {activeAnalyticsTab === "finance" && api && (
        <BonusAnalytics api={api} {...getAnalyticsPeriodBounds(startDate, endDate)} refreshGeneration={refreshGeneration} />
      )}
      {!loading && overview && (
        <div
          className="analytics-tab-panel"
          role="tabpanel"
          aria-label={selectedReport.label}
          data-tab={activeAnalyticsTab}
        >
          <header className="analytics-report-title sr-only">
            <div>
              <h2>{selectedReport.title}</h2>
              <p>{selectedReport.description}</p>
            </div>
            <span>Время отчёта: Москва</span>
          </header>
          {showComparison && (
            <AnalyticsComparison
              metrics={comparisonMetrics}
              isPartial={dashboard?.comparison.is_partial ?? false}
              value={comparisonValue}
            />
          )}
          <AnalyticsReportContent
            tab={activeAnalyticsTab}
            overview={overview}
            finance={finance}
            dashboard={dashboard}
            drillDown={drillDown}
            drillDownLoading={drillDownLoading}
            requestState={reportState}
            metricInfo={metricInfo}
            stateLabel={stateLabel}
            money={money}
            hours={hours}
            onClient={openClient}
            paymentMethods={paymentMethods}
            onOpenDrillDown={() => void openDrillDown()}
            occupancyScope={occupancyScope}
            setOccupancyScope={setOccupancyScope}
            occupancyMeasure={occupancyMeasure}
            setOccupancyMeasure={setOccupancyMeasure}
          />
        </div>
      )}
    </>
  );
}

export function Dashboard({
  onDeposit,
  onOpenCash,
  onOpenMap,
  onOpenBookings,
  onPc,
  pcs,
  clients: clientList,
  reservations,
  auditEvents,
  liveMode,
  revenueCents,
  revenueChargeCount,
  group,
  setGroup,
  zoneOptions,
}: DashboardProps) {
  const busy = pcs.filter((pc) => pc.status === "busy").length;
  const free = pcs.filter((pc) => pc.status === "online").length;
  const visiblePcs = pcs.filter(
    (pc) => group === "Все зоны" || pc.group === group,
  );
  const dashboardPcs = visiblePcs.slice(0, 6);
  const demoDashboardPcs = dashboardPcs.map((pc, index) =>
    liveMode
      ? pc
      : {
          ...pc,
          status: index === 0 ? ("busy" as const) : ("offline" as const),
          client: index === 0 ? "DanielBarutov" : undefined,
          session: index === 0 ? "5 мин" : undefined,
          tariff: index === 0 ? "Поминутно" : undefined,
        },
  );
  const deposits = clientList.reduce(
    (total, client) => total + client.balance,
    0,
  );
  const waitingReservations = reservations.filter(
    (reservation) => reservation.status === "confirmed",
  ).length;
  return (
    <>
      <div
        className="relative mb-0 min-h-46 overflow-hidden mt-7"
        style={{
          backgroundPosition: "center 44%",
          backgroundSize: "cover",
          backgroundRepeat: "no-repeat",
        }}
      >
        <div className="relative z-10">
          <p className="mb-1 text-sm text-base-content/65!">
            {new Date(2026, 9, 3).toLocaleDateString("ru-RU", {
              weekday: "long",
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </p>
          <h1 className="text-3xl font-bold tracking-tight">Сегодня в клубе</h1>
          <p className="mt-1 text-sm text-base-content/70!">
            Места, брони и операции за сегодня.
          </p>
        </div>
        <div className="heading-actions relative z-10 mt-4 flex flex-wrap items-center gap-2">
          <button
            className="secondary-button btn btn-outline btn-sm"
            onClick={onOpenCash}
          >
            <Clock3 size={16} /> Открыть смену
          </button>
          <button
            className="primary-button btn btn-primary btn-sm"
            onClick={onDeposit}
          >
            <Plus size={17} /> Пополнить депозит
          </button>
        </div>
      </div>
      <div className="metric-grid grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Выручка сегодня"
          value={
            liveMode
              ? revenueCents === null
                ? "—"
                : `${(revenueCents / 100).toLocaleString("ru-RU")} ₽`
              : "0 ₽"
          }
          delta={liveMode ? `${revenueChargeCount} операций` : "0 операций"}
          positive={!liveMode && revenueCents === null}
          icon={<Banknote size={18} />}
          accent="green"
        />
        <MetricCard
          title="Активные сессии"
          value={liveMode ? `${busy} / ${pcs.length}` : "1 / 6"}
          delta={liveMode ? `${free} свободных` : "7 свободных"}
          positive
          icon={<Wifi size={18} />}
          accent="green"
        />
        <MetricCard
          title="Брони сегодня"
          value={liveMode ? String(reservations.length) : "0"}
          delta={liveMode ? `${waitingReservations} ожидают` : "0 ожидают"}
          icon={<CalendarDays size={18} />}
          accent="green"
        />
        <MetricCard
          title="На депозитах"
          value={liveMode ? `${deposits.toLocaleString("ru-RU")} ₽` : "1 300 ₽"}
          delta={liveMode ? `${clientList.length} клиентов` : "10 клиентов"}
          icon={<CreditCard size={18} />}
          accent="green"
        />
      </div>
      <div className="section-row mt-2 mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">Карта мест</h2>
          <p className="section-caption text-sm text-base-content/65!">
            Текущее состояние игровых мест
          </p>
        </div>
        <div className="section-tools flex flex-wrap items-center gap-2 m-5">
          <Segmented value={group} onChange={setGroup} options={zoneOptions} />
          <button
            className="text-button btn btn-ghost btn-sm text-primary!"
            onClick={onOpenMap}
          >
            Открыть карту <ChevronRight size={15} />
          </button>
        </div>
      </div>
      <PcGrid pcs={demoDashboardPcs} onPc={onPc} compact regularIllustrations />
      <div className="lower-grid mt-7 grid grid-cols-1 gap-5 lg:grid-cols-2">
        <ActivityCard liveMode={liveMode} events={auditEvents} />
        <UpcomingBookings
          liveMode={liveMode}
          reservations={reservations}
          pcs={pcs}
          clients={clientList}
          onOpenBookings={onOpenBookings}
        />
      </div>
    </>
  );
}

export function ActivityCard({
  liveMode,
  events,
}: {
  liveMode: boolean;
  events: BackendAuditEvent[];
}) {
  if (liveMode) {
    const eventIcon = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("client")) return <ArrowDownLeft size={16} />;
      if (path.includes("session")) return <Computer size={16} />;
      if (path.includes("reservation")) return <CalendarDays size={16} />;
      return <Shield size={16} />;
    };
    const eventTitle = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("top-up") || path.includes("topup"))
        return "Пополнение баланса";
      if (path.includes("charge")) return "Оплата игрового времени";
      if (path.includes("reservation")) return "Операция с бронью";
      if (path.includes("session")) return "Игровая сессия";
      if (path.includes("workstation")) return "Игровое место";
      if (path.includes("client")) return "Карточка клиента";
      if (path.includes("catalog")) return "Изменение каталога";
      return "Изменение данных";
    };
    const outcomeLabel = (event: BackendAuditEvent) =>
      event.outcome === "success" ? "Успешно" : `Ошибка ${event.status_code}`;
    return (
      <div className="card shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md min-h-56 gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content!">
        <div className="card-heading flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">Активность смены</h3>
            <p className="text-xs text-base-content/60!">
              Последние операции команды
            </p>
          </div>
          <Shield size={18} className="text-primary!" />
        </div>
        {events.map((event) => (
          <div
            className="activity-item flex items-center gap-3 border-t border-primary/10! py-2"
            key={event.id}
          >
            <div
              className={`activity-icon grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/15! text-primary! ${event.outcome === "success" ? "income" : "booking"}`}
            >
              {eventIcon(event)}
            </div>
            <div className="min-w-0 grow">
              <strong className="block truncate text-sm">
                {eventTitle(event)}
              </strong>
              <span className="block truncate text-xs text-base-content/60!">
                {new Date(event.created_at).toLocaleString("ru-RU")} ·{" "}
                {event.actor_id || "Система"}
              </span>
            </div>
            <b
              className={
                event.outcome === "success"
                  ? "text-primary!"
                  : "text-base-content/70!"
              }
            >
              {outcomeLabel(event)}
            </b>
          </div>
        ))}
        {!events.length && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] text-sm text-base-content/60!">
            Операций пока нет
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="card shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md min-h-0 gap-1 border border-primary/25! bg-base-100/85! p-3 text-base-content!">
      <div className="card-heading flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">Активность смены</h3>
          <p className="text-xs text-base-content/60!">
            Последние операции команды
          </p>
        </div>
        <Shield size={18} className="text-primary!" />
      </div>
      <div className="activity-item flex items-center gap-3 border-t border-primary/10! py-1.5">
        <div className="activity-icon grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/15! text-primary!">
          <Shield size={16} />
        </div>
        <div className="min-w-0 grow">
          <strong className="block truncate text-sm">Изменение данных</strong>
          <span className="block text-xs text-base-content/60!">
            03.10.2026, 23:13:33 · mac-9c6b00cdf56d
          </span>
        </div>
        <b className="text-primary!">Успешно</b>
      </div>
      <div className="activity-item flex items-center gap-3 border-t border-primary/10! py-1.5">
        <div className="activity-icon grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/15! text-primary!">
          <Shield size={16} />
        </div>
        <div className="min-w-0 grow">
          <strong className="block truncate text-sm">Изменение данных</strong>
          <span className="block text-xs text-base-content/60!">
            03.10.2026, 23:13:23 · mac-9c6b00cdf56d
          </span>
        </div>
        <b className="text-primary!">Успешно</b>
      </div>
      <div className="activity-item flex items-center gap-3 border-t border-primary/10! py-1.5">
        <div className="activity-icon grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/15! text-primary!">
          <Shield size={16} />
        </div>
        <div className="min-w-0 grow">
          <strong className="block truncate text-sm">Изменение данных</strong>
          <span className="block text-xs text-base-content/60!">
            03.10.2026, 23:13:13 · mac-9c6b00cdf56d
          </span>
        </div>
        <b className="text-primary!">Успешно</b>
      </div>
    </div>
  );
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
  const clientNames = new Map(
    clients.map((client) => [client.id, client.nickname]),
  );
  const liveItems = reservations
    .filter(
      (reservation) =>
        reservation.status !== "cancelled" &&
        Date.parse(reservation.end_at) >= Date.now(),
    )
    .sort(
      (left, right) => Date.parse(left.start_at) - Date.parse(right.start_at),
    )
    .slice(0, 3);
  return (
    <div className="card shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md min-h-0 gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content!">
      <div className="card-heading flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">Ближайшие брони</h3>
          <p className="text-xs text-base-content/60!">Сегодня</p>
        </div>
        <button
          className="text-button btn btn-ghost btn-sm text-primary!"
          onClick={onOpenBookings}
        >
          Все брони <ChevronRight size={15} />
        </button>
      </div>
      {liveMode
        ? liveItems.map((reservation) => (
            <div
              className="upcoming-item grid grid-cols-[auto_1fr_auto] items-center gap-3 border-t border-primary/10! py-2"
              key={reservation.id}
            >
              <div className="booking-time flex flex-col">
                <strong>
                  {new Date(reservation.start_at).toLocaleTimeString("ru-RU", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </strong>
                <span className="text-xs text-base-content/60!">
                  {new Date(reservation.end_at).toLocaleTimeString("ru-RU", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div className="min-w-0">
                <strong className="block truncate text-sm">
                  {reservation.guest_name ||
                    (reservation.client_id
                      ? clientNames.get(reservation.client_id) || "Клиент"
                      : "Гость")}
                </strong>
                <span className="block truncate text-xs text-base-content/60!">
                  {reservation.workstation_ids
                    .map((id) => workstationNames.get(id) || id.slice(0, 8))
                    .join(", ")}
                </span>
              </div>
              <span
                className={`badge badge-soft badge-sm ${reservation.status === "confirmed" ? "badge-warning" : "badge-success"}`}
              >
                {reservation.status}
              </span>
            </div>
          ))
        : null}
      {(!liveMode || !liveItems.length) && (
        <div className="flex min-h-32 flex-col items-center justify-center gap-3 border-t border-primary/10! text-center text-sm text-base-content/60!">
          <CalendarDays
            size={52}
            strokeWidth={1.4}
            className="text-base-content/35!"
          />
          <span>На сегодня броней не найдено</span>
        </div>
      )}
    </div>
  );
}
