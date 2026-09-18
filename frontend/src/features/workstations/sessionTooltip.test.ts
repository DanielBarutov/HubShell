import { describe, expect, it } from "vitest";
import { getSessionTooltipDetails, sessionTooltip } from "./sessionTooltip";
import type { Workstation } from "../../types";

describe("sessionTooltip", () => {
  it("показывает snapshot, только активные пакеты и расчетное окончание", () => {
    const pc: Workstation = {
      id: "pc-1",
      name: "VIP-01",
      group: "VIP-зона",
      status: "busy",
      client: "NightFox",
      sessionSnapshot: {
        server_time: "2026-09-17T12:00:00Z",
        balance_cents: 35_000,
        balance_remaining_minutes: 150,
        active_entitlement: { id: "e1", duration_minutes: 120, remaining_minutes: 48, status: "active" } as never,
        entitlements: [
          { id: "e1", duration_minutes: 120, remaining_minutes: 48, status: "active" } as never,
          { id: "e2", duration_minutes: 180, remaining_minutes: 180, status: "queued" } as never,
          { id: "e3", duration_minutes: 30, remaining_minutes: 0, status: "exhausted" } as never,
        ],
        active_tariff: null,
      } as never,
    };

    const tooltip = sessionTooltip(pc);
    expect(tooltip).toContain("NightFox");
    expect(tooltip).toContain("350");
    expect(tooltip).toContain("Активный");
    expect(tooltip).toContain("В очереди");
    expect(tooltip).not.toContain("exhausted");
    expect(tooltip).toContain("Окончание");
  });

  it("не включает ночной пакет вне окна расходования в окончание сессии", () => {
    const pc: Workstation = {
      id: "pc-2",
      name: "VIP-02",
      group: "VIP-зона",
      status: "busy",
      client: "NightFox",
      sessionSnapshot: {
        server_time: "2026-09-17T12:00:00Z",
        balance_cents: 0,
        balance_remaining_minutes: 0,
        login_grant_remaining_minutes: 0,
        active_entitlement: null,
        active_tariff: null,
        entitlements: [
          { id: "night", duration_minutes: 660, remaining_minutes: 660, status: "queued", time_restricted: true, usage_window_start_minute: 22 * 60, usage_window_end_minute: 8 * 60, window_timezone: "Europe/Moscow" },
          { id: "test", duration_minutes: 3, remaining_minutes: 3, status: "queued", time_restricted: false },
        ],
      } as never,
    };

    const details = getSessionTooltipDetails(pc);

    expect(details?.packages[0]?.availableNow).toBe(false);
    expect(details?.packages[1]?.availableNow).toBe(true);
    expect(details?.packageMinutes).toBe(3);
    expect(details?.totalMinutes).toBe(3);
  });

  it("завершает расчёт через активный час, не дожидаясь ночного пакета", () => {
    const pc: Workstation = {
      id: "pc-3",
      name: "VIP-03",
      group: "VIP-зона",
      status: "busy",
      client: "DayFox",
      sessionSnapshot: {
        server_time: "2026-09-17T12:00:00Z",
        balance_cents: 0,
        balance_remaining_minutes: 0,
        login_grant_remaining_minutes: 0,
        active_entitlement: { id: "hour", duration_minutes: 60, remaining_minutes: 60, status: "active" } as never,
        active_tariff: null,
        entitlements: [
          { id: "hour", duration_minutes: 60, remaining_minutes: 60, status: "active", time_restricted: false },
          { id: "night", duration_minutes: 660, remaining_minutes: 660, status: "queued", time_restricted: true, usage_window_start_minute: 22 * 60, usage_window_end_minute: 8 * 60, window_timezone: "Europe/Moscow" },
        ],
      } as never,
    };

    const details = getSessionTooltipDetails(pc);

    expect(details?.packageMinutes).toBe(60);
    expect(details?.totalMinutes).toBe(60);
    expect(details?.ending?.toISOString()).toBe("2026-09-17T13:00:00.000Z");
  });

  it("ограничивает ночную сессию закрытием окна в восемь утра", () => {
    const pc: Workstation = {
      id: "pc-4",
      name: "VIP-04",
      group: "VIP-зона",
      status: "busy",
      client: "NightFox",
      sessionSnapshot: {
        server_time: "2026-09-17T22:00:00Z",
        balance_cents: 0,
        balance_remaining_minutes: 0,
        login_grant_remaining_minutes: 0,
        active_entitlement: { id: "night", duration_minutes: 660, remaining_minutes: 660, status: "active" } as never,
        active_tariff: null,
        entitlements: [
          { id: "night", duration_minutes: 660, remaining_minutes: 660, status: "active", time_restricted: true, usage_window_start_minute: 21 * 60, usage_window_end_minute: 8 * 60, window_timezone: "Europe/Moscow" },
        ],
      } as never,
    };

    const details = getSessionTooltipDetails(pc);

    expect(details?.packageMinutes).toBe(7 * 60);
    expect(details?.totalMinutes).toBe(7 * 60);
    expect(details?.ending?.toISOString()).toBe("2026-09-18T05:00:00.000Z");
  });
});
