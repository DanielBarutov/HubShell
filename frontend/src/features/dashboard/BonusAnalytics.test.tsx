import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GameClubApi, type BackendBonusReport } from "../../api";
import { BonusAnalytics } from "./BonusAnalytics";

const report: BackendBonusReport = {
  start_at: "2026-10-16T00:00:00Z", end_at: "2026-10-17T00:00:00Z", observed_at: "2026-10-17T12:00:00Z",
  period: { credited_cents: 123, spent_cents: 234, adjustments_cents: -55, opening_cents: 500, reserved_in_cents: 1000, released_cents: 400 },
  total_cents: 900, available_cents: 300, reserved_cents: 600, pending_cents: 77,
};

describe("Бонусная аналитика", () => {
  it("разделяет потоки за период и текущие остатки, обновляет даты", async () => {
    const api = new GameClubApi("/api/v1");
    const load = vi.spyOn(api, "getBonusReport").mockResolvedValue(report);
    const props = { api, startAt: report.start_at, endAt: report.end_at, refreshGeneration: 0 };
    const view = render(<BonusAnalytics {...props} />);
    expect(await screen.findByText("1,23")).toBeVisible();
    for (const value of ["2,34", "-0,55", "9,00", "3,00", "6,00", "0,77"]) expect(screen.getByText(value)).toBeVisible();
    expect(screen.getByText(/дополнительные фильтры продаж не применяются/)).toBeVisible();
    view.rerender(<BonusAnalytics {...props} startAt="2026-10-15T00:00:00Z" />);
    await screen.findByText("1,23");
    expect(load).toHaveBeenLastCalledWith("2026-10-15T00:00:00Z", report.end_at);
  });
  it("показывает ошибку без нулей и повторяет запрос", async () => {
    const api = new GameClubApi("/api/v1");
    vi.spyOn(api, "getBonusReport").mockRejectedValueOnce(new Error("Нет связи")).mockResolvedValue(report);
    render(<BonusAnalytics api={api} startAt={report.start_at} endAt={report.end_at} refreshGeneration={0} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Нет связи");
    expect(screen.queryByText("0,00")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Повторить загрузку бонусов" }));
    expect(await screen.findByText("1,23")).toBeVisible();
  });
});
