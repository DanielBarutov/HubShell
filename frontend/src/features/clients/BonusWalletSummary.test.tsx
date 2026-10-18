import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GameClubApi } from "../../api";
import { BonusWalletSummary } from "./BonusWalletSummary";

describe("Бонусный счёт", () => {
  it("загружает историю по запросу и показывает точную дельту, причину и автора", async () => {
    const api = new GameClubApi("/api/v1");
    vi.spyOn(api, "getBonusWallet").mockResolvedValue({ total_cents: 55, available_cents: 55, reserved_cents: 0, pending_cents: 0 });
    const history = vi.spyOn(api, "listBonusOperations").mockResolvedValue([{
      id: "op", client_id: "client-1", kind: "adjust", amount_cents: 55, actor_id: "owner", reason: "Подарок",
      idempotency_key: "key", session_id: null, wallet_after: { total_cents: 55, available_cents: 55, reserved_cents: 0 },
      total_delta_cents: 55, reserved_delta_cents: 0, created_at: "2026-10-17T10:00:00Z",
    }]);
    render(<BonusWalletSummary api={api} clientId="client-1" />);
    await screen.findByLabelText("Бонусный счёт");
    expect(history).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "История бонусов" }));
    expect(await screen.findByText("Подарок")).toBeVisible();
    expect(screen.getByText(/Бонусы: \+0,55/)).toBeVisible();
    expect(screen.getByText(/Автор: owner/)).toBeVisible();
  });
  it("разделяет доступный остаток, резерв и ожидающее начисление с копейками", async () => {
    const api = new GameClubApi("/api/v1");
    vi.spyOn(api, "getBonusWallet").mockResolvedValue({ total_cents: 1234, available_cents: 1100, reserved_cents: 134, pending_cents: 5 });
    render(<BonusWalletSummary api={api} clientId="client-1" />);
    const summary = await screen.findByLabelText("Бонусный счёт");
    for (const value of ["12,34 ₽", "11,00 ₽", "1,34 ₽", "0,05 ₽"]) expect(within(summary).getByText(value)).toBeVisible();
  });

  it("не заменяет ошибку фиктивным нулевым остатком и допускает повтор", async () => {
    const api = new GameClubApi("/api/v1");
    vi.spyOn(api, "getBonusWallet").mockRejectedValueOnce(new Error("Нет связи")).mockResolvedValue({ total_cents: 100, available_cents: 100, reserved_cents: 0, pending_cents: 0 });
    render(<BonusWalletSummary api={api} clientId="client-1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи");
    expect(screen.queryByText("0,00 ₽")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Обновить бонусы" }));
    expect(await screen.findByLabelText("Бонусный счёт")).toHaveTextContent("1,00 ₽");
  });
});
