import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BackendClient, GameClubApi } from "../../api";
import { DepositPanel } from "./DepositPanel";
import type { Client, Workstation } from "../../types";

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

describe("Пополнение депозита", () => {
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
