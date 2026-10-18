import { describe, expect, it } from "vitest";
import { getSessionTooltipDetails, sessionTooltip, SessionEndingProjection } from "./sessionTooltip";
import type { Workstation } from "../../types";

describe("sessionTooltip", () => {
  it("показывает точный серверный срок Xbox без округления до лишней минуты", () => {
    const xbox: Workstation = {
      id: "xbox", name: "Xbox", group: "Зал", status: "busy", equipmentType: "xbox",
      sessionSnapshot: {
        server_time: "2026-10-13T10:00:35Z",
        session: { id: "session", expires_at: "2026-10-13T10:30:02Z" },
        entitlements: [], active_tariff: { remaining_minutes: 30 },
      } as never,
    };
    expect(getSessionTooltipDetails(xbox)?.ending?.toISOString()).toBe("2026-10-13T10:30:02.000Z");
  });
  it("суммирует текущий пакет и все допроданные гостевые пакеты без двойного счёта", () => {
    const pc: Workstation = {
      id: "guest-pc", name: "Guest PC", group: "Зал", status: "busy", client: "Гость",
      sessionSnapshot: {
        server_time: "2026-10-11T11:14:00Z", session: { id: "guest-session" },
        entitlements: [], balance_cents: null, balance_remaining_minutes: null,
        login_grant_remaining_minutes: 0,
        active_tariff: { remaining_minutes: 2 },
        guest_packages: [
          { id: "first", tariff_id: "three", tariff_name: "Три минуты", duration_minutes: 3,
            remaining_minutes: 2, status: "active" },
          { id: "second", tariff_id: "six", tariff_name: "Шесть минут", duration_minutes: 6,
            remaining_minutes: 6, status: "queued" },
        ],
      } as never,
    };
    const details = getSessionTooltipDetails(pc)!;
    expect(details.packageMinutes).toBe(8);
    expect(details.totalMinutes).toBe(8);
    expect(details.packages.map(item => item.tariffName)).toEqual(["Три минуты", "Шесть минут"]);
    expect(details.ending?.toISOString()).toBe("2026-10-11T11:22:00.000Z");
  });

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

  it("обновляет баланс, но не переносит окончание вперёд между минутными тиками", () => {
    const projection = new SessionEndingProjection();
    const snapshot = (serverTime: string, balanceCents: number): Workstation => ({
      id: "pc-v2-minute",
      name: "VIP-09",
      group: "VIP-зона",
      status: "busy",
      sessionSnapshot: {
        server_time: serverTime,
        session: { id: "session-v2-minute" },
        balance_cents: balanceCents,
        balance_remaining_minutes: Math.floor(balanceCents / 100),
        login_grant_remaining_minutes: 0,
        active_entitlement: null,
        active_tariff: null,
        entitlements: [],
      } as never,
    });

    const first = sessionTooltip(
      snapshot("2026-10-01T15:00:00Z", 4_400),
      projection,
    )!;
    const nextMinute = sessionTooltip(
      snapshot("2026-10-01T15:01:00Z", 4_300),
      projection,
    )!;

    expect(first).toContain("Баланс: 44");
    expect(nextMinute).toContain("Баланс: 43");
    expect(nextMinute.match(/Окончание: .+/)?.[0]).toBe(
      first.match(/Окончание: .+/)?.[0],
    );
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

  it("не сдвигает окончание при каждом расходе бесплатной и пакетной минуты", () => {
    const steps = [
      { elapsed: 0, grant: 5, packageMinutes: 3 },
      { elapsed: 1, grant: 4, packageMinutes: 3 },
      { elapsed: 2, grant: 3, packageMinutes: 3 },
      { elapsed: 3, grant: 2, packageMinutes: 3 },
      { elapsed: 4, grant: 1, packageMinutes: 3 },
      { elapsed: 5, grant: 0, packageMinutes: 3 },
      { elapsed: 6, grant: 0, packageMinutes: 2 },
      { elapsed: 7, grant: 0, packageMinutes: 1 },
    ];

    for (const step of steps) {
      const pc: Workstation = {
        id: "pc-minute-by-minute",
        name: "VIP-05",
        group: "VIP-зона",
        status: "busy",
        client: "MinuteFox",
        sessionSnapshot: {
          server_time: `2026-09-17T12:${String(step.elapsed).padStart(2, "0")}:00Z`,
          balance_cents: 15_000,
          balance_remaining_minutes: 9,
          login_grant_remaining_minutes: step.grant,
          active_entitlement: { id: "three-minutes", duration_minutes: 3, remaining_minutes: step.packageMinutes, status: "active" } as never,
          active_tariff: null,
          entitlements: [{ id: "three-minutes", duration_minutes: 3, remaining_minutes: step.packageMinutes, status: "active" } as never],
        } as never,
      };

      expect(getSessionTooltipDetails(pc)?.ending?.toISOString()).toBe("2026-09-17T12:17:00.000Z");
    }

    const stopped: Workstation = {
      id: "pc-minute-by-minute",
      name: "VIP-05",
      group: "VIP-зона",
      status: "online",
    };
    expect(getSessionTooltipDetails(stopped)).toBeNull();
  });

  it("не переносит окончание вперёд из-за запоздалого снимка сервера", () => {
    const endingProjection = new SessionEndingProjection();
    const steps = [
      { minute: 5, packageMinutes: 3 },
      { minute: 6, packageMinutes: 3 },
      { minute: 7, packageMinutes: 3 },
      { minute: 8, packageMinutes: 2 },
      { minute: 9, packageMinutes: 1 },
    ];

    for (const step of steps) {
      const pc: Workstation = {
        id: "pc-server-delay",
        name: "VIP-06",
        group: "VIP-зона",
        status: "busy",
        sessionSnapshot: {
          server_time: `2026-09-17T12:${String(step.minute).padStart(2, "0")}:00Z`,
          session: { id: "session-server-delay" },
          balance_cents: 15_000,
          balance_remaining_minutes: 9,
          login_grant_remaining_minutes: 0,
          active_entitlement: { id: "three-minutes", duration_minutes: 3, remaining_minutes: step.packageMinutes, status: "active" } as never,
          active_tariff: null,
          entitlements: [{ id: "three-minutes", duration_minutes: 3, remaining_minutes: step.packageMinutes, status: "active" } as never],
        } as never,
      };

      expect(getSessionTooltipDetails(pc, endingProjection)?.ending?.toISOString()).toBe("2026-09-17T12:17:00.000Z");
    }
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
