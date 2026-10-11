import { Children, type ReactNode } from "react";
import {
  Banknote,
  BarChart3,
  CalendarDays,
  Clock3,
  Computer,
  ShoppingCart,
  Timer,
  TrendingUp,
  UserPlus,
  UserRoundCheck,
  Users,
  WalletCards,
} from "lucide-react";
import type {
  BackendAnalyticsBreakdown,
  BackendAnalyticsBucket,
  BackendAnalyticsDrillDown,
  BackendAnalyticsFinanceResponse,
  BackendAnalyticsOverview,
  BackendAnalyticsV2Dashboard,
  BackendAnalyticsV2Metric,
  BackendPaymentMethod,
  BackendTopClient,
  BackendTopProduct,
} from "../../api";
import { MetricCard } from "../../shared/components/MetricCard";
import type { MetricInfoData } from "../../shared/components/MetricInfo";
import { productCategoryLabel, type AnalyticsDataState } from "./analytics";

export type AnalyticsSeries = {
  key: string;
  label: string;
  tone: "sessions" | "products" | "visitors";
  value: (bucket: BackendAnalyticsBucket) => number;
};

export function AnalyticsBucketChart({
  title,
  caption,
  buckets,
  series,
  formatAxisValue,
  formatValue,
  variant = "bars",
}: {
  title: string;
  caption: string;
  buckets: BackendAnalyticsBucket[];
  series: AnalyticsSeries[];
  formatAxisValue: (value: number) => string;
  formatValue: (value: number) => string;
  variant?: "bars" | "area";
}) {
  const maximum = Math.max(
    0,
    ...buckets.flatMap((bucket) => series.map((item) => item.value(bucket))),
  );
  const axisMaximum = maximum > 0 ? maximum : 1;
  const ticks = [1, 0.75, 0.5, 0.25, 0].map(
    (fraction) => axisMaximum * fraction,
  );
  const labelEvery = Math.max(1, Math.ceil(buckets.length / 8));
  const chartWidth = 1000;
  const chartHeight = 176;
  const chartInset = { left: 10, right: 10, top: 10, bottom: 24 };
  const graphWidth = chartWidth - chartInset.left - chartInset.right;
  const graphHeight = chartHeight - chartInset.top - chartInset.bottom;
  const pointX = (index: number) =>
    buckets.length < 2
      ? chartInset.left + graphWidth / 2
      : chartInset.left + (index * graphWidth) / (buckets.length - 1);
  const pointY = (value: number) =>
    chartInset.top + graphHeight * (1 - value / axisMaximum);
  const pathFor = (value: (bucket: BackendAnalyticsBucket) => number) =>
    buckets
      .map(
        (bucket, index) =>
          `${index === 0 ? "M" : "L"} ${pointX(index)} ${pointY(value(bucket))}`,
      )
      .join(" ");
  const areaPath =
    series.length && buckets.length
      ? `${pathFor(series[0].value)} L ${pointX(buckets.length - 1)} ${chartInset.top + graphHeight} L ${pointX(0)} ${chartInset.top + graphHeight} Z`
      : "";
  const seriesColor = (tone: AnalyticsSeries["tone"]) =>
    tone === "products"
      ? "var(--color-info)"
      : tone === "visitors"
        ? "var(--color-secondary)"
        : "var(--color-primary)";

  return (
    <section className="analytics-chart-card card gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{title}</h3>
          <p className="text-xs text-base-content/60!">{caption}</p>
        </div>
      </header>
      {buckets.length ? (
        <>
          <div
            className="analytics-chart-legend flex flex-wrap gap-3 text-xs text-base-content/60!"
            aria-label="Обозначения графика"
          >
            {series.map((item) => (
              <span className="inline-flex items-center gap-1.5" key={item.key}>
                <i
                  className="inline-block size-2 rounded-full"
                  style={{ backgroundColor: seriesColor(item.tone) }}
                />
                {item.label}
              </span>
            ))}
          </div>
          <div
            className="analytics-chart-frame flex h-40 gap-2"
            role="img"
            aria-label={title}
          >
            <div
              className="analytics-chart-axis-y flex w-12 shrink-0 flex-col justify-between py-2 text-[10px] text-base-content/50!"
              aria-hidden="true"
            >
              {ticks.map((tick, index) => (
                <span key={index}>{formatAxisValue(tick)}</span>
              ))}
            </div>
            <div
              className={`analytics-chart-plot relative h-40 min-w-0 flex-1 overflow-hidden rounded-lg border border-primary/15! bg-base-200/55! shadow-[inset_0_0_18px_rgba(49,217,120,0.04)] ${variant === "area" ? "is-area" : ""}`}
            >
              {maximum === 0 && (
                <div className="absolute inset-0 z-20 grid place-items-center p-6 text-center">
                  <div className="max-w-xs rounded-2xl border border-primary/20 bg-base-100/85 px-5 py-4 shadow-xl backdrop-blur-sm">
                    <p className="text-sm font-semibold text-base-content">
                      Нет операций за период
                    </p>
                    <p className="mt-1 text-xs text-base-content/60">
                      График появится, когда в выбранном диапазоне будут данные.
                    </p>
                  </div>
                </div>
              )}
              {variant === "area" ? (
                <svg
                  className="analytics-area-svg h-full w-full"
                  viewBox={`0 0 ${chartWidth} ${chartHeight}`}
                  preserveAspectRatio="none"
                  aria-hidden="true"
                >
                  {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
                    const y = chartInset.top + graphHeight * fraction;
                    return (
                      <line
                        className="stroke-1"
                        key={fraction}
                        x1={chartInset.left}
                        x2={chartWidth - chartInset.right}
                        y1={y}
                        y2={y}
                        stroke="rgba(224,238,233,.16)"
                      />
                    );
                  })}
                  <path d={areaPath} fill="rgba(168,255,77,.10)" />
                  {series.map((item) => (
                    <g key={item.key}>
                      <path
                        className="fill-none stroke-2"
                        d={pathFor(item.value)}
                        style={{ stroke: seriesColor(item.tone) }}
                      />
                      {buckets.map((bucket, index) => (
                        <circle
                          className="stroke-2"
                          key={bucket.key}
                          cx={pointX(index)}
                          cy={pointY(item.value(bucket))}
                          r="3"
                          style={{
                            fill: seriesColor(item.tone),
                            stroke: "var(--color-base-100)",
                          }}
                        >
                          <title>
                            {bucket.label}: {item.label} —{" "}
                            {formatValue(item.value(bucket))}
                          </title>
                        </circle>
                      ))}
                    </g>
                  ))}
                  {buckets.map((bucket, index) =>
                    index % labelEvery === 0 || index === buckets.length - 1 ? (
                      <text
                        className="text-[10px]"
                        key={bucket.key}
                        x={pointX(index)}
                        y={chartHeight - 3}
                        textAnchor={
                          index === 0
                            ? "start"
                            : index === buckets.length - 1
                              ? "end"
                              : "middle"
                        }
                        fill="rgba(224,238,233,.65)"
                      >
                        {bucket.label}
                      </text>
                    ) : null,
                  )}
                </svg>
              ) : (
                <>
                  <div
                    className="analytics-chart-grid pointer-events-none absolute inset-0 flex flex-col justify-between p-3"
                    aria-hidden="true"
                  >
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                  <div className="analytics-chart-columns relative z-10 flex h-full items-stretch gap-1 px-3 pt-3">
                    {buckets.map((bucket, index) => (
                      <div
                        className="analytics-chart-column flex min-w-0 flex-1 flex-col justify-end gap-1"
                        key={bucket.key}
                        title={`${bucket.label}: ${series.map((item) => `${item.label} — ${formatValue(item.value(bucket))}`).join(", ")}`}
                      >
                        <div className="analytics-chart-bars flex min-h-0 flex-1 items-end justify-center gap-0.5">
                          {series.map((item) => (
                            <i
                              className="block w-2 rounded-t-sm"
                              key={item.key}
                              style={{
                                height: `${item.value(bucket) > 0 ? Math.max(2, (item.value(bucket) / axisMaximum) * 100) : 0}%`,
                                backgroundColor: seriesColor(item.tone),
                              }}
                            />
                          ))}
                        </div>
                        <span>
                          {index % labelEvery === 0 ||
                          index === buckets.length - 1
                            ? bucket.label
                            : ""}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          За выбранный период нет данных для графика.
        </div>
      )}
    </section>
  );
}

export function ReportMetricGrid({ children }: { children: ReactNode }) {
  return (
    <div
      className="analytics-report-kpis mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5 [&>.card]:h-32 [&>.card]:min-h-0! [&>.card]:gap-1 [&>.card]:p-2.5"
      data-count={Children.count(children)}
    >
      {children}
    </div>
  );
}

export function AnalyticsBreakdownTable({
  title,
  caption,
  rows,
  mode,
  usageMeasure = "time",
}: {
  title: string;
  caption: string;
  rows: BackendAnalyticsBreakdown[];
  mode: "usage" | "sales";
  usageMeasure?: "time" | "revenue";
}) {
  const usageColumns = mode === "usage";
  const sortedRows = usageColumns
    ? [...rows].sort((left, right) =>
        usageMeasure === "time"
          ? right.played_minutes - left.played_minutes
          : right.revenue_cents - left.revenue_cents,
      )
    : rows;
  const maxValue = Math.max(
    1,
    ...sortedRows.map((row) =>
      usageMeasure === "time" ? row.played_minutes : row.revenue_cents,
    ),
  );

  return (
    <section className="card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
      {title && (
        <header className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
              <BarChart3 size={16} />
            </span>
            <div>
              <h3 className="font-semibold">{title}</h3>
              <p className="text-xs text-base-content/60!">{caption}</p>
            </div>
          </div>
        </header>
      )}
      {sortedRows.length ? (
        <div className="analytics-table-scroll overflow-x-auto">
          <table className="analytics-data-table table table-sm w-full text-sm">
            <thead>
              <tr>
                <th scope="col">
                  {usageColumns ? "Место или зал" : "Категория"}
                </th>
                {usageColumns ? (
                  <>
                    <th scope="col">Сессии</th>
                    <th scope="col">
                      {usageMeasure === "time"
                        ? "Игровое время"
                        : "Сумма операций"}
                    </th>
                  </>
                ) : (
                  <>
                    <th scope="col">Продано</th>
                    <th scope="col">Сумма продаж</th>
                    <th scope="col">Себестоимость</th>
                    <th scope="col">Прибыль</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.key}>
                  <th scope="row">
                    {usageColumns ? row.label : productCategoryLabel(row.label)}
                  </th>
                  {usageColumns ? (
                    <>
                      <td>{row.session_count.toLocaleString("ru-RU")}</td>
                      <td>
                        <div className="min-w-28">
                          <span>
                            {usageMeasure === "time"
                              ? `${(row.played_minutes / 60).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ч`
                              : `${(row.revenue_cents / 100).toLocaleString("ru-RU")} ₽`}
                          </span>
                          <progress
                            className="progress progress-primary mt-1 h-1.5 w-full"
                            value={
                              usageMeasure === "time"
                                ? row.played_minutes
                                : row.revenue_cents
                            }
                            max={maxValue}
                          />
                        </div>
                      </td>
                    </>
                  ) : (
                    <>
                      <td>{row.product_units.toLocaleString("ru-RU")} шт.</td>
                      <td>
                        {(row.product_revenue_cents / 100).toLocaleString(
                          "ru-RU",
                        )}{" "}
                        ₽
                      </td>
                      <td>
                        {(row.product_cost_cents / 100).toLocaleString("ru-RU")}{" "}
                        ₽
                      </td>
                      <td>
                        {(row.gross_profit_cents / 100).toLocaleString("ru-RU")}{" "}
                        ₽
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          За выбранный период записей нет.
        </div>
      )}
    </section>
  );
}

export function TopProductsTable({
  products,
}: {
  products: BackendTopProduct[];
}) {
  return (
    <section className="card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
            <ShoppingCart size={16} />
          </span>
          <div>
            <h3>Продажи по товарам</h3>
            <p>Количество, выручка и прибыль</p>
          </div>
        </div>
      </header>
      {products.length ? (
        <div className="analytics-table-scroll overflow-x-auto">
          <table className="analytics-data-table table table-sm w-full text-sm">
            <thead>
              <tr>
                <th scope="col">Товар</th>
                <th scope="col">Продано</th>
                <th scope="col">Сумма продаж</th>
                <th scope="col">Прибыль</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.product_id}>
                  <th scope="row">{product.product_name}</th>
                  <td>{product.units.toLocaleString("ru-RU")} шт.</td>
                  <td>
                    {(product.revenue_cents / 100).toLocaleString("ru-RU")} ₽
                  </td>
                  <td>
                    {(product.gross_profit_cents / 100).toLocaleString("ru-RU")}{" "}
                    ₽
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          Продаж товаров за выбранный период нет.
        </div>
      )}
    </section>
  );
}

export function TopClientsTable({
  clients,
  onClient,
}: {
  clients: BackendTopClient[];
  onClient: (id: string) => void;
}) {
  return (
    <section className="card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
            <Users size={16} />
          </span>
          <div>
            <h3>Активные клиенты</h3>
            <p>Игровое время и покупки за период</p>
          </div>
        </div>
      </header>
      {clients.length ? (
        <div className="analytics-table-scroll overflow-x-auto">
          <table className="analytics-data-table table table-sm w-full text-sm">
            <thead>
              <tr>
                <th scope="col">Клиент</th>
                <th scope="col">Сессии</th>
                <th scope="col">Игровое время</th>
                <th scope="col">Товары</th>
                <th scope="col">Всего потрачено</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((client) => (
                <tr key={client.client_id}>
                  <th scope="row">
                    <button
                      className="analytics-table-link btn btn-ghost"
                      onClick={() => onClient(client.client_id)}
                    >
                      {client.nickname}
                    </button>
                  </th>
                  <td>{client.session_count.toLocaleString("ru-RU")}</td>
                  <td>
                    {(client.played_minutes / 60).toLocaleString("ru-RU", {
                      maximumFractionDigits: 1,
                    })}{" "}
                    ч
                  </td>
                  <td>
                    {(client.product_spend_cents / 100).toLocaleString("ru-RU")}{" "}
                    ₽
                  </td>
                  <td>
                    {(client.total_spend_cents / 100).toLocaleString("ru-RU")} ₽
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          Активности клиентов за выбранный период нет.
        </div>
      )}
    </section>
  );
}

export function PaymentMethodsTable({
  finance,
  methods,
}: {
  finance: BackendAnalyticsFinanceResponse | null;
  methods: BackendPaymentMethod[];
}) {
  const labels = new Map(methods.map((method) => [method.key, method.name]));
  return (
    <section className="card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
            <WalletCards size={16} />
          </span>
          <div>
            <h3>Выручка по способам оплаты</h3>
            <p>Подтверждённые операции за период</p>
          </div>
        </div>
      </header>
      {finance?.payment_methods.length ? (
        <div className="analytics-table-scroll overflow-x-auto">
          <table className="analytics-data-table table table-sm w-full text-sm">
            <thead>
              <tr>
                <th scope="col">Способ оплаты</th>
                <th scope="col">Операций</th>
                <th scope="col">Доля</th>
                <th scope="col">Сумма</th>
              </tr>
            </thead>
            <tbody>
              {finance.payment_methods.map((item) => (
                <tr key={item.key}>
                  <th scope="row">{labels.get(item.key) ?? item.key}</th>
                  <td>{item.operation_count.toLocaleString("ru-RU")}</td>
                  <td>
                    <div className="min-w-24">
                      <span>
                        {(item.share_bps / 100).toLocaleString("ru-RU")}%
                      </span>
                      <progress
                        className="progress progress-primary mt-1 h-1.5 w-full"
                        value={item.share_bps}
                        max={10000}
                      />
                    </div>
                  </td>
                  <td>{(item.amount_cents / 100).toLocaleString("ru-RU")} ₽</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          {finance
            ? "Оплат за выбранный период нет."
            : "Данные по способам оплаты недоступны."}
        </div>
      )}
    </section>
  );
}

export function AnalyticsComparison({
  metrics,
  isPartial,
  value,
}: {
  metrics: BackendAnalyticsV2Metric[];
  isPartial: boolean;
  value: (metric: BackendAnalyticsV2Metric, value: number) => string;
}) {
  return (
    <section
      className="card mb-4 gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.1)] backdrop-blur-md"
      aria-label="Сравнение периодов"
    >
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3>Сравнение с прошлым периодом</h3>
          <p>Предыдущий отрезок такой же длины</p>
        </div>
        {isPartial && (
          <span className="badge badge-warning badge-soft badge-sm">
            Текущий период ещё не завершён
          </span>
        )}
      </header>
      {metrics.length ? (
        <div className="analytics-comparison-grid grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((metric) => {
            const comparison = metric.comparison!;
            const max = Math.max(
              1,
              comparison.current ?? 0,
              comparison.previous ?? 0,
            );
            const positive = (comparison.delta ?? 0) >= 0;
            return (
              <div
                className="analytics-comparison-metric rounded-lg border border-primary/15! bg-base-100/70! p-3"
                key={metric.key}
              >
                <div>
                  <strong>{metric.metric_info.label}</strong>
                  <b className={positive ? "positive" : "negative"}>
                    {positive ? "+" : ""}
                    {comparison.change_percent?.toLocaleString("ru-RU", {
                      maximumFractionDigits: 1,
                    }) ?? "—"}
                    %
                  </b>
                </div>
                <div className="analytics-compare-bars grid gap-1.5 py-2">
                  <span
                    style={{
                      width: `${Math.max(4, ((comparison.current ?? 0) / max) * 100)}%`,
                    }}
                  />
                  <i
                    style={{
                      width: `${Math.max(4, ((comparison.previous ?? 0) / max) * 100)}%`,
                    }}
                  />
                </div>
                <small>
                  <em>Сейчас</em>
                  {value(metric, comparison.current ?? 0)} <em>Раньше</em>
                  {value(metric, comparison.previous ?? 0)}
                </small>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
          Для этого периода нет показателей для сравнения.
        </div>
      )}
    </section>
  );
}

export function AnalyticsReportContent({
  tab,
  overview,
  finance,
  paymentMethods,
  dashboard,
  drillDown,
  drillDownLoading,
  requestState,
  metricInfo,
  stateLabel,
  money,
  hours,
  onClient,
  onOpenDrillDown,
  occupancyScope,
  setOccupancyScope,
  occupancyMeasure,
  setOccupancyMeasure,
}: {
  tab: "overview" | "finance" | "occupancy" | "customers";
  overview: BackendAnalyticsOverview;
  finance: BackendAnalyticsFinanceResponse | null;
  paymentMethods: BackendPaymentMethod[];
  dashboard: BackendAnalyticsV2Dashboard | null;
  drillDown: BackendAnalyticsDrillDown | null;
  drillDownLoading: boolean;
  requestState: AnalyticsDataState;
  metricInfo: {
    revenue: MetricInfoData;
    margin: MetricInfoData;
    time: MetricInfoData;
    occupancy: MetricInfoData;
    depositTopUps: MetricInfoData;
    sessions: MetricInfoData;
    averageSession: MetricInfoData;
    clients: MetricInfoData;
    returningClients: MetricInfoData;
    guests: MetricInfoData;
    productRevenue: MetricInfoData;
    productSales: MetricInfoData;
  };
  stateLabel: (state: AnalyticsDataState) => string;
  money: (cents: number) => string;
  hours: (minutes: number) => string;
  onClient: (id: string) => void;
  onOpenDrillDown: () => void;
  occupancyScope: "workstations" | "zones";
  setOccupancyScope: (scope: "workstations" | "zones") => void;
  occupancyMeasure: "time" | "revenue";
  setOccupancyMeasure: (measure: "time" | "revenue") => void;
}) {
  const display = (value: string, state = requestState) =>
    state === "ready" || state === "available" ? value : stateLabel(state);
  const recognizedRevenue = finance?.metrics.recognized_revenue_cents;
  const recognizedRevenueValue = recognizedRevenue?.value_cents ?? null;
  const recognizedRevenueDisplay =
    recognizedRevenueValue === null
      ? stateLabel(recognizedRevenue?.state ?? "not_available")
      : money(recognizedRevenueValue);
  const depositTopUpsValue = finance?.flow.deposit_top_up_revenue_cents ?? null;
  const depositTopUpsDisplay =
    depositTopUpsValue === null ? "Нет данных" : money(depositTopUpsValue);
  const moneyAxis = (cents: number) =>
    `${new Intl.NumberFormat("ru-RU", { notation: "compact", maximumFractionDigits: 1 }).format(cents / 100)} ₽`;
  const numberAxis = (value: number) =>
    new Intl.NumberFormat("ru-RU", {
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  const revenueSeries: AnalyticsSeries[] = [
    {
      key: "recognized-revenue",
      label: "Признанный доход",
      tone: "sessions",
      value: (bucket) => bucket.total_revenue_cents,
    },
  ];
  const revenueBuckets = finance?.daily.map((bucket) => ({
    key: bucket.key,
    label: bucket.label,
    session_revenue_cents: 0,
    product_revenue_cents: 0,
    total_revenue_cents: bucket.recognized_revenue_cents,
    session_count: 0,
    product_sale_count: 0,
    product_units: 0,
    played_minutes: 0,
    guest_session_count: 0,
  })) ?? overview.daily_activity;
  const productSeries: AnalyticsSeries[] = [
    {
      key: "products",
      label: "Сумма продаж товаров",
      tone: "products",
      value: (bucket) => bucket.product_revenue_cents,
    },
  ];
  const visitSeries: AnalyticsSeries[] = [
    {
      key: "sessions",
      label: "Все сессии",
      tone: "sessions",
      value: (bucket) => bucket.session_count,
    },
    {
      key: "visitors",
      label: "Гостевые сессии",
      tone: "visitors",
      value: (bucket) => bucket.guest_session_count,
    },
  ];
  const hourlySeries: AnalyticsSeries[] = [
    {
      key: "sessions",
      label: "Игровое время",
      tone: "sessions",
      value: (bucket) => bucket.played_minutes,
    },
  ];
  const operations = drillDown?.items ?? [];
  const productBlock = dashboard?.blocks.products;

  if (tab === "finance") {
    return (
      <>
        <ReportMetricGrid>
          <MetricCard
            title="Выручка клуба"
            value={recognizedRevenueDisplay}
            delta="Платежи + пополнения − возвраты"
            icon={<Banknote size={18} />}
            accent="green"
            info={metricInfo.revenue}
            state={recognizedRevenue?.state ?? "not_available"}
            stateLabel={stateLabel(recognizedRevenue?.state ?? "not_available")}
          />
          <MetricCard
            title="Пополнения депозита"
            value={depositTopUpsDisplay}
            delta="Признаны доходом один раз"
            icon={<WalletCards size={18} />}
            accent="green"
            info={metricInfo.depositTopUps}
            state={
              finance?.metrics.deposit_top_up_revenue_cents?.state ??
              "not_available"
            }
            stateLabel={stateLabel(
              finance?.metrics.deposit_top_up_revenue_cents?.state ??
                "not_available",
            )}
          />
          <MetricCard
            title="Сумма продаж товаров"
            value={display(money(overview.product_revenue_cents))}
            delta={`${overview.product_units.toLocaleString("ru-RU")} продано`}
            icon={<ShoppingCart size={18} />}
            accent="green"
            info={metricInfo.productRevenue}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Валовая прибыль"
            value={display(money(overview.gross_profit_cents))}
            delta={`Себестоимость ${money(overview.product_cost_cents)}`}
            icon={<TrendingUp size={18} />}
            accent="green"
            info={metricInfo.margin}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Продажи товаров"
            value={display(overview.product_sale_count.toLocaleString("ru-RU"))}
            delta="За выбранный период"
            icon={<CalendarDays size={18} />}
            accent="green"
            info={metricInfo.productSales}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
        </ReportMetricGrid>
        <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
          <AnalyticsBucketChart
            title="Сумма продаж товаров по дням"
            caption="Продажи товаров за выбранный период, независимо от способа оплаты"
            buckets={overview.daily_activity}
            series={productSeries}
            formatAxisValue={(value) => moneyAxis(value)}
            formatValue={(value) => money(value)}
          />
          <PaymentMethodsTable finance={finance} methods={paymentMethods} />
        </div>
        <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
          <TopProductsTable products={overview.top_products} />
          <AnalyticsBreakdownTable
            title="Продажи по категориям"
            caption="Количество, сумма продаж, себестоимость и прибыль"
            rows={overview.product_categories}
            mode="sales"
          />
        </div>
        {productBlock && (
        <section className="analytics-sales-detail card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
            <header className="flex items-start justify-between gap-3">
              <div>
                <h3>Операции по товарам</h3>
                <p>
                  Состояние данных: {stateLabel(productBlock.state)} ·{" "}
                  {productBlock.rows.length} позиций
                </p>
              </div>
              <button
                className="secondary-button btn btn-outline"
                onClick={onOpenDrillDown}
                disabled={drillDownLoading}
                aria-busy={drillDownLoading}
              >
                {drillDownLoading ? "Загружаем…" : "Показать операции"}
              </button>
            </header>
            {productBlock.state === "partial" && (
              <p className="analytics-data-note rounded-lg bg-warning/10! p-3 text-sm text-warning-content!">
                Часть товарных данных ещё не подтверждена.
              </p>
            )}
            {productBlock.rows.length > 0 && (
              <div className="analytics-table-scroll overflow-x-auto">
                <table className="analytics-data-table table table-sm w-full text-sm">
                  <thead>
                    <tr>
                      <th scope="col">Позиция</th>
                      <th scope="col">Продано</th>
                      <th scope="col">Сумма продаж</th>
                      <th scope="col">Себестоимость</th>
                      <th scope="col">Прибыль</th>
                    </tr>
                  </thead>
                  <tbody>
                    {productBlock.rows.map((row) => (
                      <tr key={row.key}>
                        <th scope="row">{row.label}</th>
                        <td>{row.units.toLocaleString("ru-RU")}</td>
                        <td>{money(row.revenue_cents)}</td>
                        <td>{money(row.cost_cents)}</td>
                        <td>{money(row.gross_profit_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {drillDown &&
              (operations.length ? (
                <div className="analytics-table-scroll overflow-x-auto">
                  <table className="analytics-data-table analytics-operations-table table table-sm w-full text-sm">
                    <thead>
                      <tr>
                        <th scope="col">Дата и время</th>
                        <th scope="col">Операция</th>
                        <th scope="col">Товар или причина</th>
                        <th scope="col">Количество</th>
                        <th scope="col">Сумма</th>
                      </tr>
                    </thead>
                    <tbody>
                      {operations.map((item) => (
                        <tr key={item.source_id}>
                          <td>
                            {new Date(item.occurred_at).toLocaleString(
                              "ru-RU",
                              {
                                day: "2-digit",
                                month: "short",
                                hour: "2-digit",
                                minute: "2-digit",
                              },
                            )}
                          </td>
                          <td>
                            {item.kind === "sale"
                              ? "Продажа"
                              : item.kind === "return"
                                ? "Возврат"
                                : "Корректировка"}
                          </td>
                          <td>{item.product_name ?? item.reason ?? "—"}</td>
                          <td>{item.quantity.toLocaleString("ru-RU")}</td>
                          <td>{money(item.amount_cents)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="analytics-report-empty rounded-lg border border-dashed border-primary/25! bg-base-200/35 p-5 text-center text-sm text-base-content/60!">
                  Операций за выбранный период нет.
                </div>
              ))}
          </section>
        )}
      </>
    );
  }

  if (tab === "occupancy") {
    const rows =
      occupancyScope === "workstations"
        ? overview.workstations
        : overview.zones;
    return (
      <>
        <ReportMetricGrid>
          <MetricCard
            title="Занятость мест"
            value={display(
              `${overview.occupancy_percent.toLocaleString("ru-RU")}%`,
              overview.workstation_count ? requestState : "not_available",
            )}
            delta={`${overview.workstation_count} мест в клубе`}
            icon={<Computer size={18} />}
            accent="green"
            info={metricInfo.occupancy}
            state={overview.workstation_count ? requestState : "not_available"}
            stateLabel={stateLabel(
              overview.workstation_count ? requestState : "not_available",
            )}
          />
          <MetricCard
            title="Игровое время"
            value={display(
              hours(overview.played_minutes),
              overview.session_count ? requestState : "not_calculated",
            )}
            delta="За выбранный период"
            icon={<Clock3 size={18} />}
            accent="green"
            info={metricInfo.time}
            state={overview.session_count ? requestState : "not_calculated"}
            stateLabel={stateLabel(
              overview.session_count ? requestState : "not_calculated",
            )}
          />
          <MetricCard
            title="Сессии"
            value={display(overview.session_count.toLocaleString("ru-RU"))}
            delta="Завершённые игры"
            icon={<CalendarDays size={18} />}
            accent="green"
            info={metricInfo.sessions}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Средняя сессия"
            value={display(
              `${overview.average_session_minutes.toLocaleString("ru-RU")} мин`,
              overview.session_count ? requestState : "not_calculated",
            )}
            delta={`Пиковый час ${overview.peak_usage_hour ?? "—"}`}
            icon={<Timer size={18} />}
            accent="green"
            info={metricInfo.averageSession}
            state={overview.session_count ? requestState : "not_calculated"}
            stateLabel={stateLabel(
              overview.session_count ? requestState : "not_calculated",
            )}
          />
        </ReportMetricGrid>
        <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
          <AnalyticsBucketChart
            title="Загрузка по часам"
            caption="Игровое время в течение дня"
            buckets={overview.hourly_activity}
            series={hourlySeries}
            formatAxisValue={(value) => hours(value)}
            formatValue={(value) => hours(value)}
          />
          <div className="analytics-occupancy-side flex flex-col gap-4">
          <section className="analytics-occupancy-controls card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
            <header className="flex items-start justify-between gap-3">
                <div>
                  <h3>
                    {occupancyScope === "workstations"
                      ? "Игровые места"
                      : "Залы и зоны"}
                  </h3>
                  <p>Выберите разрез и показатель</p>
                </div>
              </header>
              <div className="analytics-report-controls flex flex-wrap gap-2">
                <div
                  className="analytics-view-toggle join border border-primary/20! bg-base-100/55! p-1"
                  role="group"
                  aria-label="Разбивка по местам или зонам"
                >
                  <button
                    className="btn btn-ghost btn-sm"
                    type="button"
                    aria-pressed={occupancyScope === "workstations"}
                    onClick={() => setOccupancyScope("workstations")}
                  >
                    По местам
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    type="button"
                    aria-pressed={occupancyScope === "zones"}
                    onClick={() => setOccupancyScope("zones")}
                  >
                    По залам
                  </button>
                </div>
                <div
                  className="analytics-view-toggle join border border-primary/20! bg-base-100/55! p-1"
                  role="group"
                  aria-label="Показатель загрузки"
                >
                  <button
                    className="btn btn-ghost btn-sm"
                    type="button"
                    aria-pressed={occupancyMeasure === "time"}
                    onClick={() => setOccupancyMeasure("time")}
                  >
                    Игровое время
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    type="button"
                    aria-pressed={occupancyMeasure === "revenue"}
                    onClick={() => setOccupancyMeasure("revenue")}
                  >
                    Сумма операций
                  </button>
                </div>
              </div>
            </section>
            <AnalyticsBreakdownTable
              title=""
              caption=""
              rows={rows}
              mode="usage"
              usageMeasure={occupancyMeasure}
            />
          </div>
        </div>
      </>
    );
  }

  if (tab === "customers") {
    return (
      <>
        <ReportMetricGrid>
          <MetricCard
            title="Клиенты с визитом"
            value={display(
              overview.active_client_count.toLocaleString("ru-RU"),
            )}
            delta={`${overview.new_client_count} новых`}
            icon={<Users size={18} />}
            accent="green"
            info={metricInfo.clients}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Вернувшиеся клиенты"
            value={display(
              overview.returning_client_count.toLocaleString("ru-RU"),
            )}
            delta="За выбранный период"
            icon={<Users size={18} />}
            accent="green"
            info={metricInfo.returningClients}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Гостевые сессии"
            value={display(
              overview.guest_session_count.toLocaleString("ru-RU"),
            )}
            delta={`${overview.unique_visitor_count} посетителей`}
            icon={<Users size={18} />}
            accent="green"
            info={metricInfo.guests}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
          <MetricCard
            title="Сессии"
            value={display(overview.session_count.toLocaleString("ru-RU"))}
            delta="За выбранный период"
            icon={<CalendarDays size={18} />}
            accent="green"
            info={metricInfo.sessions}
            state={requestState}
            stateLabel={stateLabel(requestState)}
          />
        </ReportMetricGrid>
        <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
          <AnalyticsBucketChart
            title="Сессии по дням"
            caption="Все сессии и гостевые сессии по выбранному периоду"
            buckets={overview.daily_activity}
            series={visitSeries}
            formatAxisValue={(value) => numberAxis(value)}
            formatValue={(value) => value.toLocaleString("ru-RU")}
            variant="area"
          />
          <section className="analytics-visitor-summary card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
            <header className="flex items-start justify-between gap-3">
              <div>
                <h3>Посещения</h3>
                <p>Клиенты и гости отдельно</p>
              </div>
            </header>
            <dl>
              <div>
                <dt>Новые клиенты</dt>
                <dd>{overview.new_client_count.toLocaleString("ru-RU")}</dd>
              </div>
              <div>
                <dt>Вернувшиеся клиенты</dt>
                <dd>
                  {overview.returning_client_count.toLocaleString("ru-RU")}
                </dd>
              </div>
              <div>
                <dt>Гостевые сессии</dt>
                <dd>{overview.guest_session_count.toLocaleString("ru-RU")}</dd>
              </div>
              <div>
                <dt>Пиковый час</dt>
                <dd>{overview.peak_usage_hour ?? "Нет данных"}</dd>
              </div>
            </dl>
          </section>
        </div>
        <TopClientsTable clients={overview.top_clients} onClient={onClient} />
      </>
    );
  }

  return (
    <>
      <ReportMetricGrid>
        <MetricCard
          title="Выручка клуба"
          value={recognizedRevenueDisplay}
          delta="Платежи + пополнения − возвраты"
          icon={<Banknote size={18} />}
          accent="green"
          info={metricInfo.revenue}
          state={recognizedRevenue?.state ?? "not_available"}
          stateLabel={stateLabel(recognizedRevenue?.state ?? "not_available")}
        />
        <MetricCard
          title="Игровое время"
          value={display(
            hours(overview.played_minutes),
            overview.session_count ? requestState : "not_calculated",
          )}
          delta={`${overview.session_count} сессий`}
          icon={<Clock3 size={18} />}
          accent="green"
          info={metricInfo.time}
          state={overview.session_count ? requestState : "not_calculated"}
          stateLabel={stateLabel(
            overview.session_count ? requestState : "not_calculated",
          )}
        />
        <MetricCard
          title="Средняя сессия"
          value={display(
            `${overview.average_session_minutes.toLocaleString("ru-RU")} мин`,
            overview.session_count ? requestState : "not_calculated",
          )}
          delta={`Пиковый час ${overview.peak_usage_hour ?? "—"}`}
          icon={<Timer size={18} />}
          accent="green"
          info={metricInfo.averageSession}
          state={overview.session_count ? requestState : "not_calculated"}
          stateLabel={stateLabel(
            overview.session_count ? requestState : "not_calculated",
          )}
        />
        <MetricCard
          title="Занятость мест"
          value={display(
            `${overview.occupancy_percent.toLocaleString("ru-RU")}%`,
            overview.workstation_count ? requestState : "not_available",
          )}
          delta={`${overview.workstation_count} мест в клубе`}
          icon={<Computer size={18} />}
          accent="green"
          info={metricInfo.occupancy}
          state={overview.workstation_count ? requestState : "not_available"}
          stateLabel={stateLabel(
            overview.workstation_count ? requestState : "not_available",
          )}
        />
        <MetricCard
          title="Клиенты с визитом"
          value={display(overview.active_client_count.toLocaleString("ru-RU"))}
          delta={`${overview.guest_session_count} гостевых сессий`}
          icon={<Users size={18} />}
          accent="green"
          info={metricInfo.clients}
          state={requestState}
          stateLabel={stateLabel(requestState)}
        />
      </ReportMetricGrid>
      <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <AnalyticsBucketChart
          title="Операции по дням"
          caption="Все подтверждённые платежи и пополнения без повторного учёта списаний депозита."
          buckets={revenueBuckets}
          series={revenueSeries}
          formatAxisValue={moneyAxis}
          formatValue={money}
          variant="area"
        />
        <section className="analytics-overview-facts card gap-1 border border-primary/25! bg-base-100/85! p-2 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md [&_dl>div]:min-h-0 [&_dl>div]:gap-1 [&_dl>div]:rounded-lg [&_dl>div]:px-1 [&_dl>div]:py-0! [&_dl>div>dt]:text-[10px] [&_dl>div>dd]:text-[11px] [&_dl>div>span]:size-6 [&_dl>div>span]:rounded-md [&_dl>div_svg]:size-3.5">
          <header className="flex items-start justify-between gap-2">
            <div>
              <h3 className="text-sm">За этот период</h3>
              <p className="text-[11px]">Клиенты, товары и часы пик</p>
            </div>
          </header>
        <dl className="grid gap-0.5">
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <WalletCards size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Пополнения депозита
              </dt>
              <dd className="text-sm font-semibold">{depositTopUpsDisplay}</dd>
            </div>
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <UserPlus size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Новые клиенты
              </dt>
              <dd className="text-sm font-semibold">
                {overview.new_client_count.toLocaleString("ru-RU")}
              </dd>
            </div>
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <UserRoundCheck size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Вернувшиеся клиенты
              </dt>
              <dd className="text-sm font-semibold">
                {overview.returning_client_count.toLocaleString("ru-RU")}
              </dd>
            </div>
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <Users size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Гости
              </dt>
              <dd className="text-sm font-semibold">
                {overview.guest_session_count.toLocaleString("ru-RU")} сессий
              </dd>
            </div>
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <TrendingUp size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Прибыль с товаров
              </dt>
              <dd className="text-sm font-semibold">
                {money(overview.gross_profit_cents)}
              </dd>
            </div>
          <div className="flex items-center gap-2 rounded-xl border border-primary/15! bg-base-200/45 p-1">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/12 text-primary">
                <Clock3 size={16} />
              </span>
              <dt className="min-w-0 flex-1 text-xs text-base-content/65">
                Пиковый час
              </dt>
              <dd className="text-sm font-semibold">
                {overview.peak_usage_hour ?? "Нет данных"}
              </dd>
            </div>
          </dl>
        </section>
      </div>
      <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <AnalyticsBreakdownTable
          title="Загрузка по игровым местам"
          caption="Число сессий и игровое время"
          rows={overview.workstations}
          mode="usage"
        />
        <TopProductsTable products={overview.top_products} />
      </div>
      <div className="analytics-report-grid mb-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(280px,0.75fr)]">
        <PaymentMethodsTable finance={finance} methods={paymentMethods} />
        <TopClientsTable clients={overview.top_clients} onClient={onClient} />
      </div>
    </>
  );
}
