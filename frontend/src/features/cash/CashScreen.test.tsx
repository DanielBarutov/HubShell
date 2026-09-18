import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GameClubApi } from "../../api";
import { CashScheduleEditor } from "./CashScreen";

describe("Настройка автоматической смены", () => {
  it("позволяет выбрать время автооткрытия, не выключая правило", async () => {
    const saveCashShiftSchedule = vi.fn().mockResolvedValue({
      register_id: "front-desk",
      timezone: "Europe/Moscow",
      auto_open: true,
      auto_open_at: "08:30:00",
      auto_close: false,
      auto_close_at: null,
      opening_balance_cents: 0,
    });
    const api = { saveCashShiftSchedule } as unknown as GameClubApi;

    render(<CashScheduleEditor api={api} onSaved={vi.fn()} />);

    fireEvent.click(screen.getByRole("checkbox", { name: /Автооткрытие/ }));
    fireEvent.click(screen.getByRole("button", { name: "Время автооткрытия" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Время автооткрытия: часы" }), { target: { value: "8" } });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Время автооткрытия: часы" })).toHaveValue("8"));
    fireEvent.change(screen.getByRole("combobox", { name: "Время автооткрытия: минуты" }), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: "Готово" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить расписание" }));

    await waitFor(() => expect(saveCashShiftSchedule).toHaveBeenCalledWith(
      "front-desk",
      expect.objectContaining({ auto_open: true, auto_open_at: "08:30" }),
    ));
  });
});
