import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GameClubApi } from "../../api";
import { DepositPanel } from "./DepositPanel";
import type { Client } from "../../types";

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
    render(<DepositPanel initialClient={client} onClose={vi.fn()} onCompleted={vi.fn()} clients={[client]} />);

    expect(screen.getByRole("textbox", { name: "Ник или номер телефона" })).toHaveValue("NightFox");
    expect(screen.getAllByText("NightFox")).toHaveLength(2);
    expect(screen.getByText("Средства будут зачислены на").parentElement).toHaveTextContent("NightFox");
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeEnabled();

    fireEvent.change(screen.getByRole("textbox", { name: "Ник или номер телефона" }), { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeDisabled();
  });

  it("требует явного подтверждения смены получателя", () => {
    /** Не даёт случайно перенаправить пополнение с активного клиента на другого. */
    render(<DepositPanel initialClient={client} onClose={vi.fn()} onCompleted={vi.fn()} clients={[client, otherClient]} />);

    fireEvent.change(screen.getByRole("textbox", { name: "Ник или номер телефона" }), { target: { value: "OtherFox" } });

    expect(screen.getByText(/Подтверждаю смену получателя/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: "Зачислить депозит" })).toBeEnabled();
  });

  it("из V2-сессии отправляет пополнение только в её session и device", async () => {
    /** Защищает от случайного ухода пополнения активного V2 ПК в старый V1 маршрут. */
    const createV2Deposit = vi.fn().mockResolvedValue({
      delivery_status: "pending_delivery",
      is_duplicate: false,
    });
    const onCompleted = vi.fn();
    const api = { createV2Deposit } as unknown as GameClubApi;

    render(<DepositPanel
      initialClient={client}
      v2Target={{ sessionId: "session-v2-1", deviceId: "device-v2-1", workstationName: "VIP-07" }}
      onClose={vi.fn()}
      onCompleted={onCompleted}
      clients={[client]}
      api={api}
    />);

    expect(screen.getByRole("textbox", { name: "Ник или номер телефона" })).toBeDisabled();
    expect(screen.getByText("Целевая V2-сессия").parentElement).toHaveTextContent("VIP-07");
    fireEvent.click(screen.getByRole("button", { name: "Зачислить депозит" }));

    await waitFor(() => expect(createV2Deposit).toHaveBeenCalledWith(
      client.id,
      expect.objectContaining({
        session_id: "session-v2-1",
        device_id: "device-v2-1",
        amount_cents: 100_000,
        currency: "RUB",
      }),
      expect.any(String),
    ));
    expect(onCompleted).toHaveBeenCalledWith(false);
    expect(screen.getByRole("status")).toHaveTextContent("Пополнение принято сервером");
  });
});
