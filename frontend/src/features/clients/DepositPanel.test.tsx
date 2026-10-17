import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BackendClient, GameClubApi } from "../../api";
import { DepositPanel } from "./DepositPanel";
import type { Client, Workstation } from "../../types";
import { ApiError } from "../../api";

const client: Client = {
  id: "client-1",
  nickname: "NightFox",
  phone: "+79990000000",
  balance: 1250,
  bonus: 10,
  category: "Обычная",
};

const otherClient: Client = {
  ...client,
  id: "client-2",
  nickname: "OtherFox",
};

function renderBonusAdjustment(adjust = vi.fn().mockResolvedValue({ id: "operation" })) {
  const topUp = vi.fn();
  const createV2Deposit = vi.fn();
  const completed = vi.fn();
  render(<DepositPanel initialClient={client} bonusOnly target={{ sessionId: "active", deviceId: "device", workstationName: "PC" }}
    api={{ adjustBonus: adjust, topUp, createV2Deposit } as unknown as GameClubApi} clients={[client]} workstations={[]}
    onClose={vi.fn()} onCompleted={completed} />);
  return { adjust, topUp, createV2Deposit, completed };
}

describe("Точная корректировка бонусов", () => {
  it("начисляет сотые бонуса с причиной без кассы и изменения денежного баланса", async () => {
    const { adjust, topUp, createV2Deposit, completed } = renderBonusAdjustment();
    fireEvent.change(screen.getByLabelText("Количество бонусов"), { target: { value: "0,55" } });
    fireEvent.change(screen.getByLabelText("Причина корректировки"), { target: { value: "Подарок клиенту" } });
    fireEvent.click(screen.getByRole("button", { name: "Начислить бонусы" }));
    await screen.findByText("Корректировка бонусов сохранена");
    expect(adjust).toHaveBeenCalledWith(client.id, 55, "Подарок клиенту", expect.any(String));
    expect(topUp).not.toHaveBeenCalled();
    expect(createV2Deposit).not.toHaveBeenCalled();
    expect(completed).toHaveBeenCalledWith(false);
  });

  it("не округляет лишние знаки и требует причину", () => {
    const { adjust } = renderBonusAdjustment();
    fireEvent.change(screen.getByLabelText("Количество бонусов"), { target: { value: "1,005" } });
    fireEvent.click(screen.getByRole("button", { name: "Начислить бонусы" }));
    expect(screen.getByRole("alert")).toHaveTextContent("точностью до 0,01");
    fireEvent.change(screen.getByLabelText("Количество бонусов"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Начислить бонусы" }));
    expect(screen.getByRole("alert")).toHaveTextContent("причину");
    expect(adjust).not.toHaveBeenCalled();
  });

  it("подтверждает списание один раз и повторяет неопределённый результат с тем же ключом", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const adjust = vi.fn().mockRejectedValueOnce(new Error("lost response")).mockResolvedValue({ id: "op" });
    const { completed } = renderBonusAdjustment(adjust);
    fireEvent.change(screen.getByLabelText("Количество бонусов"), { target: { value: "-0,55" } });
    fireEvent.change(screen.getByLabelText("Причина корректировки"), { target: { value: "Исправление ошибки" } });
    fireEvent.click(screen.getByRole("button", { name: "Списать бонусы" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет подтверждения сервера");
    expect(completed).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Количество бонусов")).toBeDisabled();
    expect(screen.getByLabelText("Причина корректировки")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Повторить корректировку" }));
    await screen.findByText("Корректировка бонусов сохранена");
    expect(confirm).toHaveBeenCalledOnce();
    expect(adjust.mock.calls[0]).toEqual(adjust.mock.calls[1]);
    expect(adjust.mock.calls[0][1]).toBe(-55);
    confirm.mockRestore();
  });

  it("позволяет исправить сумму после однозначного отказа сервера", async () => {
    renderBonusAdjustment(vi.fn().mockRejectedValue(new ApiError(409, "Резерв нельзя списать")));
    fireEvent.change(screen.getByLabelText("Причина корректировки"), { target: { value: "Корректировка" } });
    fireEvent.click(screen.getByRole("button", { name: "Начислить бонусы" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Резерв нельзя списать");
    expect(screen.getByLabelText("Количество бонусов")).toBeEnabled();
  });
});

describe("Пополнение депозита", () => {
  it("не округляет дробный ввод в старом целом бонусном поле пополнения", () => {
    const topUp = vi.fn();
    render(<DepositPanel initialClient={client} api={{ topUp } as unknown as GameClubApi} onClose={vi.fn()} onCompleted={vi.fn()} clients={[client]} workstations={[]} />);
    fireEvent.change(screen.getByLabelText("Количество бонусов"), { target: { value: "0,55" } });
    fireEvent.click(screen.getByRole("button", { name: "Зачислить депозит" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Для дробных бонусов используйте корректировку");
    expect(topUp).not.toHaveBeenCalled();
  });
  it("предзаполняет текущего клиента из карточки игрового места", () => {
    /** Проверяет, что пополнение из занятого места сразу связано с текущим клиентом и доступно к подтверждению. */
    render(<DepositPanel initialClient={client} onClose={vi.fn()} onCompleted={vi.fn()} clients={[client]} workstations={[]} />);

    expect(screen.getByRole("textbox", { name: "Ник или номер телефона" })).toHaveValue("NightFox");
    expect(screen.getAllByText("NightFox")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeEnabled();

    fireEvent.change(screen.getByRole("textbox", { name: "Ник или номер телефона" }), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeDisabled();
  });

  it("требует явного подтверждения смены получателя", () => {
    /** Не даёт случайно перенаправить пополнение с активного клиента на другого. */
    render(<DepositPanel initialClient={client} onClose={vi.fn()} onCompleted={vi.fn()} clients={[client, otherClient]} workstations={[]} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Ник или номер телефона" }), { target: { value: "OtherFox" } });

    expect(screen.getByText(/Подтверждаю смену получателя/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeEnabled();
  });

  it("из V2-сессии отправляет пополнение только в её session и device", async () => {
    /** Не даёт пополнению активного V2 ПК случайно уйти в старый V1-маршрут. */
    const createV2Deposit = vi.fn().mockResolvedValue({
      delivery_status: "pending_delivery",
      is_duplicate: false,
    });
    const onCompleted = vi.fn();
    const api = { createV2Deposit } as unknown as GameClubApi;

    const { container } = render(<DepositPanel
      initialClient={client}
      target={{ sessionId: "session-v2-1", deviceId: "device-v2-1", workstationName: "VIP-07" }}
      cashShiftId="cash-shift-1"
      onClose={vi.fn()}
      onCompleted={onCompleted}
      clients={[client]}
      workstations={[]}
      api={api}
    />);

    expect(container.textContent).not.toContain("V2");
    expect(screen.getByRole("textbox", { name: "Ник или номер телефона" })).toBeDisabled();
    expect(screen.getByText("Игровое место").parentElement).toHaveTextContent("VIP-07");
    fireEvent.click(screen.getByRole("button", { name: "Зачислить депозит" }));

    await waitFor(() => expect(createV2Deposit).toHaveBeenCalledWith(
      client.id,
      expect.objectContaining({
        session_id: "session-v2-1",
        device_id: "device-v2-1",
        amount_cents: 100_000,
        currency: "RUB",
        cash_shift_id: "cash-shift-1",
      }),
      expect.any(String),
    ));
    expect(onCompleted).toHaveBeenCalledWith(false);
    expect(screen.getByRole("status")).toHaveTextContent("Пополнение оформлено. Баланс обновится, когда компьютер будет на связи.");
  });

  it("не отправляет V2 наличное пополнение без открытой кассовой смены", async () => {
    const createV2Deposit = vi.fn();
    const api = { createV2Deposit } as unknown as GameClubApi;
    render(<DepositPanel
      initialClient={client}
      target={{ sessionId: "session-v2-1", deviceId: "device-v2-1", workstationName: "VIP-07" }}
      onClose={vi.fn()}
      onCompleted={vi.fn()}
      clients={[client]}
      workstations={[]}
      api={api}
    />);

    fireEvent.click(screen.getByRole("button", { name: "Зачислить депозит" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Чтобы принять наличные, откройте кассовую смену или выберите перевод.",
    );
    expect(createV2Deposit).not.toHaveBeenCalled();
  });

  it("routes a client search to that client's active V2 session", async () => {
    const createV2Deposit = vi.fn().mockResolvedValue({
      delivery_status: "pending_delivery",
      is_duplicate: false,
    });
    const backendClient: BackendClient = {
      id: client.id,
      nickname: client.nickname,
      phone: client.phone,
      discount_category: null,
      balance_cents: 200,
      balance_bonus: 0,
      client_group_id: null,
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z",
    };
    const searchClients = vi.fn().mockResolvedValue([backendClient]);
    const api = { searchClients, createV2Deposit } as unknown as GameClubApi;
    const activeWorkstation: Workstation = {
      id: "pc-1",
      name: "VIP-07",
      group: "VIP",
      status: "busy",
      clientId: client.id,
      sessionId: "session-v2-1",
      deviceId: "device-v2-1",
    };

    render(<DepositPanel
      onClose={vi.fn()}
      onCompleted={vi.fn()}
      clients={[client]}
      workstations={[activeWorkstation]}
      cashShiftId="cash-shift-1"
      api={api}
    />);

    fireEvent.change(screen.getByRole("textbox", { name: "Ник или номер телефона" }), {
      target: { value: "NightFox" },
    });
    expect(await screen.findByText("Игровое место")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Зачислить депозит" }));

    await waitFor(() => expect(createV2Deposit).toHaveBeenCalledWith(
      client.id,
      expect.objectContaining({
        session_id: "session-v2-1",
        device_id: "device-v2-1",
        cash_shift_id: "cash-shift-1",
      }),
      expect.any(String),
    ));
  });

  it("requires choosing the workstation when a client has multiple active V2 sessions", async () => {
    const createV2Deposit = vi.fn().mockResolvedValue({
      delivery_status: "pending_delivery",
      is_duplicate: false,
    });
    const api = { createV2Deposit } as unknown as GameClubApi;
    const firstSession: Workstation = {
      id: "pc-1",
      name: "VIP-07",
      group: "VIP",
      status: "busy",
      clientId: client.id,
      sessionId: "session-v2-1",
      deviceId: "device-v2-1",
    };
    const secondSession: Workstation = {
      ...firstSession,
      id: "pc-2",
      name: "VIP-08",
      sessionId: "session-v2-2",
      deviceId: "device-v2-2",
    };

    render(<DepositPanel
      initialClient={client}
      cashShiftId="cash-shift-1"
      onClose={vi.fn()}
      onCompleted={vi.fn()}
      clients={[client]}
      workstations={[firstSession, secondSession]}
      api={api}
    />);

    const submit = screen.getByRole("button", { name: "Зачислить депозит" });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox", { name: "Игровое место" }), {
      target: { value: "session-v2-2" },
    });
    expect(screen.getByRole("combobox", { name: "Игровое место" })).toHaveValue("session-v2-2");
    fireEvent.click(submit);

    await waitFor(() => expect(createV2Deposit).toHaveBeenCalledWith(
      client.id,
      expect.objectContaining({
        session_id: "session-v2-2",
        device_id: "device-v2-2",
      }),
      expect.any(String),
    ));
  });
});
