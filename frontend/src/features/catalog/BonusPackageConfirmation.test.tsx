import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { BonusPackageConfirmation } from "./BonusPackageConfirmation";
import type { BackendBonusGameQuote } from "../../api";

const quote: BackendBonusGameQuote = { earning_rate_bps: 500, price_cents: 10000, bonus_cents: 10000, money_cents: 0, earned_bonus_cents: 0, payment_limit_bps: 10000, available_bonus_cents: 12000, reserved_bonus_cents: 100, bonus_allowed: true, can_pay: true };
beforeAll(() => { HTMLDialogElement.prototype.showModal = function () { this.open = true; }; });

describe("Подтверждение бонусной оплаты", () => {
  it("показывает серверные суммы и подтверждает полностью бонусную покупку", () => {
    const confirm = vi.fn();
    render(<BonusPackageConfirmation quote={quote} name="Час" position="1 из 2" onConfirm={confirm} onCancel={vi.fn()} />);
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Подтвердить оплату бонусами");
    expect(screen.getByText("Час · пакет 1 из 2")).toBeVisible();
    expect(screen.getAllByText("0,00 ₽")).toHaveLength(2);
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить покупку пакета" }));
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("блокирует недостаток средств и позволяет отменить оставшиеся покупки", () => {
    const cancel = vi.fn();
    render(<BonusPackageConfirmation quote={{ ...quote, can_pay: false }} name="Час" position="2 из 2" onConfirm={vi.fn()} onCancel={cancel} />);
    expect(screen.getByRole("button", { name: "Подтвердить покупку пакета" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Отменить оставшуюся продажу" }));
    expect(cancel).toHaveBeenCalledOnce();
  });
});
