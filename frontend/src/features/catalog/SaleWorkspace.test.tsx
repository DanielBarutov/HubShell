import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SaleWorkspace } from "./SaleWorkspace";
import type { BackendProduct, BackendProductCategory, BackendTariff, GameClubApi } from "../../api";
import type { Workstation } from "../../types";

const pc: Workstation = {
  id: "pc-main-01",
  name: "Main-01",
  group: "Основной зал",
  groupId: "main",
  status: "online",
};

const tariffs: BackendTariff[] = [
  { id: "global-hour", name: "Общий час", group_id: null, duration_minutes: 60, price_cents: 500, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "global-hour", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "main-hour", name: "Час в основном зале", group_id: "main", duration_minutes: 60, price_cents: 400, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "main-hour", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "vip-hour", name: "VIP час", group_id: "vip", duration_minutes: 60, price_cents: 800, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "vip-hour", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
];

const products: BackendProduct[] = [
  { id: "water", name: "Вода", category: "drinks", price_cents: 100, active: true, cost_price_cents: 40, stock_quantity: 3 },
];

const categories: BackendProductCategory[] = [{ id: "drinks", name: "Напитки", kind: "drink", active: true }];
const api = {} as GameClubApi;

function renderSale() {
  return render(
    <SaleWorkspace
      api={api}
      pc={pc}
      initialClient={null}
      initialProduct={null}
      clients={[]}
      cashShifts={[]}
      tariffs={tariffs}
      products={products}
      categories={categories}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  );
}

describe("Окно продажи", () => {
  it("блокирует гостя на занятом ПК с зарегистрированным клиентом", async () => {
    const activePc: Workstation = { ...pc, status: "busy", clientId: "client-1", client: "NightFox" };
    const client = { id: "client-1", nickname: "NightFox", phone: "+79990000000", balance: 1250, bonus: 0, category: "Обычная" };
    const listAvailableTariffs = vi.fn().mockResolvedValue(tariffs);
    const activeApi = { listAvailableTariffs, searchClients: vi.fn().mockResolvedValue([]) } as unknown as GameClubApi;

    render(
      <SaleWorkspace
        api={activeApi}
        pc={activePc}
        initialClient={client}
        initialProduct={null}
        clients={[client]}
        cashShifts={[]}
        tariffs={tariffs}
        products={products}
        categories={categories}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: /NightFox/ })).toBeEnabled());
    expect(listAvailableTariffs).toHaveBeenCalledWith("main", "registered");
    expect(screen.getByRole("button", { name: /Гость/ })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Клиент для продажи" })).toBeDisabled();
    expect(screen.getByText("На занятом месте продажа времени доступна только текущему зарегистрированному клиенту.")).toBeVisible();
  });

  it("показывает только глобальный и зональный тарифы и требует позицию до подтверждения", () => {
    renderSale();

    expect(screen.getByRole("dialog")).toHaveAccessibleName("Продажа для Main-01");
    expect(screen.getByRole("button", { name: /Общий час/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Час в основном зале/ })).toBeVisible();
    expect(screen.queryByRole("button", { name: /VIP час/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Оформить продажу/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /Час в основном зале/ }));

    expect(screen.getAllByText("Час в основном зале")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Оформить продажу/ })).toBeEnabled();
  });

  it("переключает покупателя на гостя без регистрации и сохраняет modal accessibility", () => {
    renderSale();

    fireEvent.click(screen.getByRole("button", { name: /Зарегистрированный клиент/ }));
    expect(screen.getByRole("textbox", { name: "Клиент для продажи" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Гость/ }));

    expect(screen.queryByRole("textbox", { name: "Клиент для продажи" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-modal", "true");
  });

  it("запускает гостевую сессию только после подтверждённой оплаты", async () => {
    const confirmGuestSessionPayment = vi.fn().mockResolvedValue({ id: "payment-1", status: "confirmed" });
    const startSession = vi.fn().mockResolvedValue({ id: "session-1" });
    const api = { confirmGuestSessionPayment, startSession } as unknown as GameClubApi;
    const onSaved = vi.fn();
    vi.stubGlobal("crypto", { randomUUID: () => "sale-key-test" });

    render(
      <SaleWorkspace
        api={api}
        pc={pc}
        initialClient={null}
        initialProduct={null}
        clients={[]}
        cashShifts={[{
          id: "shift-1",
          register_id: "cash-1",
          opened_by: "operator-1",
          opened_at: "2026-09-16T08:00:00Z",
          opening_balance_cents: 0,
          expected_close_cents: 0,
          status: "open",
          closed_by: null,
          closed_at: null,
          actual_close_cents: null,
          difference_cents: null,
        }]}
        tariffs={tariffs}
        products={products}
        categories={categories}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Общий час/ }));
    fireEvent.click(screen.getByRole("button", { name: /Оформить продажу/ }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(confirmGuestSessionPayment).toHaveBeenCalledWith(expect.objectContaining({
      workstation_id: pc.id,
      tariff_id: "global-hour",
      guest_name: "Гость",
    }), "guest-payment-sale-session-sale-key-test");
    expect(startSession).toHaveBeenCalledWith(expect.objectContaining({
      workstation_id: pc.id,
      guest_name: "Гость",
      guest_payment_id: "payment-1",
    }), "sale-session-sale-key-test");
  });

  it("останавливает подтверждение продажи, если settlement гостя требует сверки", async () => {
    const confirmGuestSessionPayment = vi.fn().mockResolvedValue({
      id: "payment-1",
      status: "needs_review",
      settlement_error: "касса недоступна",
    });
    const startSession = vi.fn();
    const api = { confirmGuestSessionPayment, startSession } as unknown as GameClubApi;
    const onSaved = vi.fn();

    render(
      <SaleWorkspace
        api={api}
        pc={pc}
        initialClient={null}
        initialProduct={null}
        clients={[]}
        cashShifts={[{
          id: "shift-1",
          register_id: "cash-1",
          opened_by: "operator-1",
          opened_at: "2026-09-16T08:00:00Z",
          opening_balance_cents: 0,
          expected_close_cents: 0,
          status: "open",
          closed_by: null,
          closed_at: null,
          actual_close_cents: null,
          difference_cents: null,
        }]}
        tariffs={tariffs}
        products={products}
        categories={categories}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Общий час/ }));
    fireEvent.click(screen.getByRole("button", { name: /Оформить продажу/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("требует ручной сверки");
    expect(startSession).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("разрешает оператору оплатить пакет активного клиента наличными", async () => {
    const activePc: Workstation = { ...pc, status: "busy", clientId: "client-1", client: "NightFox" };
    const client = { id: "client-1", nickname: "NightFox", phone: "+79990000000", balance: 1250, bonus: 0, category: "Обычная" };
    const listAvailableTariffs = vi.fn().mockResolvedValue(tariffs);
    const purchaseEntitlement = vi.fn().mockResolvedValue({ id: "entitlement-1" });
    const api = { listAvailableTariffs, searchClients: vi.fn().mockResolvedValue([]), purchaseEntitlement } as unknown as GameClubApi;
    const onSaved = vi.fn();

    render(
      <SaleWorkspace
        api={api}
        pc={activePc}
        initialClient={client}
        initialProduct={null}
        clients={[client]}
        cashShifts={[{
          id: "shift-1",
          register_id: "cash-1",
          opened_by: "operator-1",
          opened_at: "2026-09-16T08:00:00Z",
          opening_balance_cents: 0,
          expected_close_cents: 0,
          status: "open",
          closed_by: null,
          closed_at: null,
          actual_close_cents: null,
          difference_cents: null,
        }]}
        tariffs={tariffs}
        products={products}
        categories={categories}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: /Час в основном зале/ })).toBeVisible());
    fireEvent.click(screen.getByRole("button", { name: /Час в основном зале/ }));
    fireEvent.click(screen.getByRole("button", { name: /Наличные/ }));
    fireEvent.click(screen.getByRole("button", { name: /Оформить продажу/ }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(purchaseEntitlement).toHaveBeenCalledWith(
      client.id,
      "main-hour",
      expect.any(String),
      [{ method: "cash", amount_cents: 400 }],
      "shift-1",
    );
  });

  it("проводит смешанную оплату только наличными и переводом", async () => {
    const sellProduct = vi.fn().mockResolvedValue({ status: "completed" });
    const api = { sellProduct } as unknown as GameClubApi;
    const onSaved = vi.fn();

    render(
      <SaleWorkspace
        api={api}
        pc={pc}
        initialClient={null}
        initialProduct={null}
        clients={[]}
        cashShifts={[{
          id: "shift-1",
          register_id: "cash-1",
          opened_by: "operator-1",
          opened_at: "2026-09-16T08:00:00Z",
          opening_balance_cents: 0,
          expected_close_cents: 0,
          status: "open",
          closed_by: null,
          closed_at: null,
          actual_close_cents: null,
          difference_cents: null,
        }]}
        tariffs={tariffs}
        products={products}
        categories={categories}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    fireEvent.click(screen.getByRole("tab", { name: /Товары и напитки/ }));
    fireEvent.click(screen.getByRole("button", { name: /Вода/ }));
    fireEvent.click(screen.getByRole("button", { name: /Смешанная/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Сумма наличными" }), { target: { value: "0.40" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Сумма переводом" }), { target: { value: "0.60" } });
    fireEvent.click(screen.getByRole("button", { name: /Оформить продажу/ }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(sellProduct).toHaveBeenCalledWith(expect.objectContaining({
      payment_method: "mixed",
      cash_shift_id: "shift-1",
      payment_parts: [
        { method: "cash", amount_cents: 40 },
        { method: "transfer", amount_cents: 60 },
      ],
    }), expect.any(String));
  });
});
