import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type BackendAnalyticsOverview, type GameClubApi } from "../../api";
import { AnalyticsView } from "./DashboardScreen";

const emptyOverview: BackendAnalyticsOverview = {
  start_at: "2026-09-20T21:00:00.000Z",
  end_at: "2026-09-21T21:00:00.000Z",
  session_revenue_cents: 0,
  product_revenue_cents: 0,
  total_revenue_cents: 0,
  session_count: 0,
  product_sale_count: 0,
  product_units: 0,
  played_minutes: 0,
  average_session_minutes: 0,
  guest_session_count: 0,
  client_count: 0,
  top_products: [],
  top_clients: [],
  product_cost_cents: 0,
  gross_profit_cents: 0,
  discount_cents: 0,
  active_client_count: 0,
  new_client_count: 0,
  returning_client_count: 0,
  unique_visitor_count: 0,
  workstation_count: 0,
  occupancy_percent: 0,
  peak_usage_hour: null,
  daily_activity: [],
  hourly_activity: [],
  zones: [],
  workstations: [],
  tariffs: [],
  payment_methods: [],
  product_categories: [],
};

function makeApi(overrides: Partial<GameClubApi> = {}): GameClubApi {
  return {
    getAnalyticsOverview: vi.fn().mockResolvedValue(emptyOverview),
    downloadAnalyticsCsv: vi.fn().mockResolvedValue(new Blob(["overview"])),
    ...overrides,
  } as unknown as GameClubApi;
}

describe("AnalyticsView", () => {
  it("показывает понятную бизнес-сводку и прячет технические фильтры до запроса", async () => {
    render(<AnalyticsView api={makeApi()} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByText("Главное за период")).toBeVisible();
    expect(screen.getByText("Сколько заработали, сколько клиентов и насколько занят клуб")).toBeVisible();
    expect(screen.getByRole("button", { name: "Дополнительные фильтры" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Дополнительные фильтры" }));
    expect(screen.getByLabelText("Зал или зона")).toBeVisible();
  });

  it("loads the additive v2 dashboard and exposes comparison and product states", async () => {
    const dashboard = {
      api_version: "v2" as const,
      timezone: "Europe/Moscow" as const,
      period: {} as never,
      filters: {} as never,
      comparison: { start_at: "2026-09-17T21:00:00.000Z", end_at: "2026-09-20T21:00:00.000Z", is_partial: true },
      blocks: {
        products: { key: "products", state: "partial" as const, rows: [], metrics: {} },
      },
    };
    const api = makeApi({
      getAnalyticsDashboard: vi.fn().mockResolvedValue(dashboard),
    });

    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByText("Сравнение: неполный период")).toBeVisible();
    expect(screen.getByText("Товары: Частичные данные")).toBeVisible();
  });

  it("opens operator drill-down without changing the v1 CSV flow", async () => {
    const api = makeApi({
      getAnalyticsDashboard: vi.fn().mockResolvedValue({
        api_version: "v2",
        timezone: "Europe/Moscow",
        period: {} as never,
        filters: {} as never,
        comparison: { start_at: "", end_at: "", is_partial: false },
        blocks: { products: { key: "products", state: "available", rows: [], metrics: {} } },
      }),
      getAnalyticsDrillDown: vi.fn().mockResolvedValue({
        state: "available",
        items: [{ source_id: "sale-1", kind: "sale", occurred_at: "2026-09-20T10:00:00Z", amount_cents: 500, quantity: 2, product_id: null, product_name: "Cola", operator_key: "operator-1", reason: null, source_reference: "ref-1", client_id: null }],
      }),
    });

    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Открыть детализацию" }));

    expect(await screen.findByText(/Cola ·/)).toBeVisible();
    expect(screen.queryByText("sale-1")).not.toBeInTheDocument();
    expect(api.getAnalyticsDrillDown).toHaveBeenCalled();
  });

  it("passes selected product and payment filters only to the additive dashboard", async () => {
    const api = makeApi({
      getAnalyticsDashboard: vi.fn().mockResolvedValue({
        api_version: "v2",
        timezone: "Europe/Moscow",
        period: {} as never,
        filters: {} as never,
        comparison: { start_at: "", end_at: "", is_partial: false },
        blocks: { products: { key: "products", state: "empty", rows: [], metrics: {} } },
      }),
    });

    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Дополнительные фильтры" }));
    fireEvent.change(screen.getByLabelText("Категория товара"), { target: { value: "drinks" } });
    fireEvent.change(screen.getByLabelText("Как оплатили"), { target: { value: "cash" } });

    await waitFor(() => expect(api.getAnalyticsDashboard).toHaveBeenLastCalledWith(expect.objectContaining({ categoryKey: "drinks", paymentMethodKey: "cash" })));
  });

  it("switches readable analytics tabs and lets the operator turn period comparison on and off", async () => {
    const api = makeApi({
      getAnalyticsDashboard: vi.fn().mockResolvedValue({
        api_version: "v2",
        timezone: "Europe/Moscow",
        period: {} as never,
        filters: {} as never,
        comparison: { start_at: "2026-09-17T21:00:00.000Z", end_at: "2026-09-20T21:00:00.000Z", is_partial: false },
        blocks: {
          finance: {
            key: "finance",
            state: "available",
            rows: [],
            metrics: {
              revenue: {
                key: "revenue",
                value: 24000,
                state: "available",
                coverage: 1,
                metric_info: { key: "revenue", label: "Выручка", description: "", formula: "", source: "" },
                comparison: { current: 24000, previous: 20000, delta: 4000, change_percent: 20, change_percentage_points: null, state: "available" },
              },
            },
          },
          products: { key: "products", state: "available", rows: [], metrics: {} },
        },
      }),
    });

    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByRole("tab", { name: "Обзор" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Деньги" }));
    expect(screen.getByRole("tab", { name: "Деньги" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Деньги" })).toBeVisible();
    expect(screen.queryByRole("tabpanel", { name: "Загрузка" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Сравнение с прошлым периодом" }));
    await waitFor(() => expect(api.getAnalyticsDashboard).toHaveBeenLastCalledWith(expect.objectContaining({ comparison: false })));
  });

  it("requests the selected calendar day using Europe/Moscow boundaries and preserves v1 CSV download", async () => {
    const api = makeApi();
    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    await waitFor(() => expect(api.getAnalyticsOverview).toHaveBeenCalled());
    const overviewCall = vi.mocked(api.getAnalyticsOverview).mock.calls[0];
    expect(overviewCall?.[0]).toMatch(/T21:00:00\.000Z$/);
    expect(overviewCall?.[1]).toMatch(/T21:00:00\.000Z$/);

    fireEvent.click(screen.getByRole("button", { name: "Скачать CSV" }));
    await waitFor(() => expect(api.downloadAnalyticsCsv).toHaveBeenCalledWith(
      overviewCall?.[0],
      overviewCall?.[1],
      50,
    ));
  });

  it("shows an explicit empty state without replacing zeroes with a fake metric", async () => {
    render(<AnalyticsView api={makeApi()} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByText("За выбранный период данных нет")).toBeVisible();
    expect(screen.getAllByText("Нет данных").length).toBeGreaterThan(0);
  });

  it("shows permission_denied instead of a generic empty dashboard", async () => {
    const api = makeApi({
      getAnalyticsOverview: vi.fn().mockRejectedValue(new ApiError(403, "Недостаточно прав", "permission_denied")),
    });
    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Недостаточно прав");
    expect(screen.getByText("Нет доступа к аналитике")).toBeVisible();
  });
});
