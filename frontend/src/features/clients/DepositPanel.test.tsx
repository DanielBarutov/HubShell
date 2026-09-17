import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
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
});
