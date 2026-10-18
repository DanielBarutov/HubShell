import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type BackendAnalyticsFinanceResponse, type BackendAnalyticsOverview, type GameClubApi } from "../../api";
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

const emptyFinance: BackendAnalyticsFinanceResponse = {
  api_version: "v2",
  period: {} as never,
  comparison: {
    current_start_at: "2026-09-20T21:00:00.000Z",
    current_end_at: "2026-09-21T21:00:00.000Z",
    previous_start_at: "2026-09-19T21:00:00.000Z",
    previous_end_at: "2026-09-20T21:00:00.000Z",
    current_state: "available",
  },
  flow: {
    payment_received_cents: 0,
    direct_payment_cents: 0,
    deposit_top_up_revenue_cents: 0,
    wallet_debit_cents: 0,
    recognized_revenue_cents: 0,
    refunds_cents: 0,
    adjustments_cents: null,
    net_cash_received_cents: 0,
  },
  metrics: {
    recognized_revenue_cents: {
      value_cents: 0,
      state: "available",
      metric_info: { key: "recognized_revenue_cents", label: "Выручка клуба", description: "", formula: "", source: "" },
      comparison: null,
    },
    deposit_top_up_revenue_cents: {
      value_cents: 0,
      state: "available",
      metric_info: { key: "deposit_top_up_revenue_cents", label: "Пополнения депозита", description: "", formula: "", source: "" },
      comparison: null,
    },
  },
  sources: {
    financial_facts: { state: "available" },
    wallet_facts: { state: "available" },
    refunds: { state: "available" },
    history: { state: "available" },
  },
  payment_methods: [],
  daily: [],
};

function makeApi(overrides: Partial<GameClubApi> = {}): GameClubApi {
  return {
    getAnalyticsOverview: vi.fn().mockResolvedValue(emptyOverview),
    getAnalyticsFinance: vi.fn().mockResolvedValue(emptyFinance),
    downloadAnalyticsCsv: vi.fn().mockResolvedValue(new Blob(["overview"])),
    ...overrides,
  } as unknown as GameClubApi;
}

describe("AnalyticsView", () => {
  it("показывает меню отчётов, период и дополнительные фильтры", async () => {
    render(<AnalyticsView api={makeApi()} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findByRole("heading", { name: "Обзор клуба" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Посещаемость" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Занятость" })).toBeVisible();
    expect(screen.getByRole("tab", { name: "Продажи" })).toBeVisible();
    expect(screen.getByRole("group", { name: "Быстрый выбор периода" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Фильтры" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
    expect(screen.getByLabelText("Зал или зона")).toBeVisible();
  });

  it("показывает таблицу занятости по местам или залам и переключает показатель", async () => {
    const api = makeApi({
      getAnalyticsOverview: vi.fn().mockResolvedValue({
        ...emptyOverview,
        session_count: 3,
        workstation_count: 1,
        workstations: [{
          key: "pc-1",
          label: "PC-01",
          session_revenue_cents: 1000,
          product_revenue_cents: 0,
          revenue_cents: 1000,
          product_cost_cents: 0,
          gross_profit_cents: 1000,
          session_count: 3,
          product_sale_count: 0,
          product_units: 0,
          played_minutes: 180,
          share_bps: 10000,
          discount_cents: 0,
        }],
        zones: [{
          key: "vip",
          label: "VIP-зал",
          session_revenue_cents: 1000,
          product_revenue_cents: 0,
          revenue_cents: 1000,
          product_cost_cents: 0,
          gross_profit_cents: 1000,
          session_count: 3,
          product_sale_count: 0,
          product_units: 0,
          played_minutes: 180,
          share_bps: 10000,
          discount_cents: 0,
        }],
      }),
    });
    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    fireEvent.click(await screen.findByRole("tab", { name: "Занятость" }));
    expect(await screen.findByRole("rowheader", { name: "PC-01" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "По залам" }));
    expect(screen.getByRole("rowheader", { name: "VIP-зал" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Сумма операций" }));
    expect(screen.getByRole("columnheader", { name: "Сумма операций" })).toBeVisible();
  });

  it("учитывает подтверждённое пополнение в выручке и обновляет отчёт по запросу", async () => {
    const finance = {
      ...emptyFinance,
      flow: {
        ...emptyFinance.flow,
        deposit_top_up_revenue_cents: 25_000,
        recognized_revenue_cents: 25_000,
        net_cash_received_cents: 25_000,
      },
      daily: [{ key: "2026-09-21", label: "21.09.2026", recognized_revenue_cents: 25_000 }],
      metrics: {
        ...emptyFinance.metrics,
        recognized_revenue_cents: {
          ...emptyFinance.metrics.recognized_revenue_cents!,
          value_cents: 25_000,
        },
        deposit_top_up_revenue_cents: {
          ...emptyFinance.metrics.deposit_top_up_revenue_cents!,
          value_cents: 25_000,
        },
      },
    } satisfies BackendAnalyticsFinanceResponse;
    const getAnalyticsFinance = vi.fn().mockResolvedValue(finance);
    const api = makeApi({ getAnalyticsFinance });
    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} />);

    expect(await screen.findAllByText("250 ₽")).toHaveLength(3);
    expect(screen.getByText("Признанный доход")).toBeVisible();
    expect(screen.queryByText("За выбранный период данных нет")).not.toBeInTheDocument();
    expect(getAnalyticsFinance).toHaveBeenCalledWith(expect.objectContaining({
      startAt: expect.any(String),
      endAt: expect.any(String),
    }));
    fireEvent.click(screen.getByRole("button", { name: "Обновить" }));
    await waitFor(() => expect(getAnalyticsFinance).toHaveBeenCalledTimes(2));
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

    expect(await screen.findByRole("tab", { name: "Обзор" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Текущий период ещё не завершён")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сравнить периоды" }));
    expect(await screen.findByText("Текущий период ещё не завершён")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Продажи" }));
    expect(screen.getByText(/Состояние данных: Частичные данные/)).toBeVisible();
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
    fireEvent.click(await screen.findByRole("tab", { name: "Продажи" }));
    fireEvent.click(await screen.findByRole("button", { name: "Показать операции" }));

    expect(await screen.findByText("Cola")).toBeVisible();
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

    render(<AnalyticsView api={api} clients={[]} onClient={vi.fn()} productCategories={[{ id: "drinks", name: "Напитки", kind: "drink", active: true }]} paymentMethods={[{ id: "cash-id", key: "cash", name: "Наличные", active: true, sort_order: 1, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" }]} />);
    fireEvent.click(screen.getByRole("button", { name: "Фильтры" }));
    expect(screen.getByLabelText("Зал или зона").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Игровое место").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Тариф").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Группа клиента").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Категория товара").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Товар").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Оператор").tagName).toBe("INPUT");
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
    fireEvent.click(screen.getByRole("tab", { name: "Продажи" }));
    expect(screen.getByRole("tab", { name: "Продажи" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Продажи" })).toBeVisible();
    expect(screen.queryByRole("tabpanel", { name: "Загрузка" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Сравнить периоды" }));
    await waitFor(() => expect(api.getAnalyticsDashboard).toHaveBeenLastCalledWith(expect.objectContaining({ comparison: true })));
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
