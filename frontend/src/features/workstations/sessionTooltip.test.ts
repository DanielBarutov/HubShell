import { describe, expect, it } from "vitest";
import { sessionTooltip } from "./sessionTooltip";
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
});
