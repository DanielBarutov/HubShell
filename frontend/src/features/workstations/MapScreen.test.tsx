import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MapView } from "./MapScreen";
import type { Workstation } from "../../types";

const workstations: Workstation[] = [
  { id: "pc-online", name: "VIP-01", group: "VIP", groupId: "vip", status: "online", position: 1 },
  { id: "pc-offline", name: "Main-02", group: "Основной зал", groupId: "main", status: "offline", position: 2 },
];

describe("Карта игровых мест", () => {
  it("маршрутизирует к продаже свободное место, а недоступное — в карточку ПК", () => {
    const onSalePc = vi.fn();
    const onPc = vi.fn();

    render(
      <MapView
        onPc={onPc}
        onSalePc={onSalePc}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={workstations}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны", "VIP", "Основной зал"]}
      />,
    );

    expect(screen.getByLabelText("Карта игровых мест")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "VIP-01: Свободен" }));
    fireEvent.click(screen.getByRole("button", { name: "Main-02: Не в сети" }));

    expect(onSalePc).toHaveBeenCalledWith(workstations[0]);
    expect(onPc).toHaveBeenCalledWith(workstations[1]);
  });

  it("открывает контекстное меню с доступными действиями для места", () => {
    const onSalePc = vi.fn();

    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={onSalePc}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={workstations}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны"]}
      />,
    );

    fireEvent.contextMenu(screen.getByRole("button", { name: "VIP-01: Свободен" }));
    expect(screen.getByRole("menu")).toBeVisible();
    fireEvent.click(screen.getByRole("menuitem", { name: "Оформить продажу" }));

    expect(onSalePc).toHaveBeenCalledWith(workstations[0]);
  });

  it("открывает продажу товара верхней кнопкой карты", () => {
    const onSellProduct = vi.fn();

    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onSellProduct={onSellProduct}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={workstations}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны"]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Продать товар" }));

    expect(onSellProduct).toHaveBeenCalledTimes(1);
  });

  it("показывает hover-карточку server snapshot для занятого места", () => {
    const busyPc: Workstation = {
      id: "pc-busy",
      name: "VIP-02",
      group: "VIP",
      groupId: "vip",
      status: "busy",
      client: "NightFox",
      sessionSnapshot: {
        server_time: "2026-09-17T20:00:00Z",
        balance_cents: 35000,
        balance_remaining_minutes: 150,
        entitlements: [{ status: "active", tariff_name: "Ночной VIP", remaining_minutes: 48, duration_minutes: 120 }],
        active_entitlement: null,
        active_tariff: null,
      } as never,
    };

    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={[busyPc]}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны"]}
      />,
    );

    const workstation = screen.getByRole("button", { name: "VIP-02: Занят" });
    fireEvent.mouseEnter(workstation);

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("NightFox");
    expect(tooltip).toHaveTextContent("Ночной VIP · 2 ч");
    expect(tooltip).toHaveTextContent("осталось 48 мин");
    expect(tooltip).toHaveTextContent("350");
    expect(tooltip).toHaveTextContent("Всего по пакетам");
    expect(tooltip).toHaveTextContent("Общее время");
    expect(tooltip).toHaveTextContent("3 ч 18 мин");
    expect(tooltip).not.toHaveTextContent("pc-busy");

    fireEvent.mouseLeave(workstation);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("не отодвигает окончание, когда задержавшийся снимок приходит до списания пакета", () => {
    const pcAtMinuteFive = busyWorkstationSnapshot("2026-09-17T12:05:00Z", 3);
    const { rerender } = render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={[pcAtMinuteFive]}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны"]}
      />,
    );

    rerender(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={[busyWorkstationSnapshot("2026-09-17T12:06:00Z", 3)]}
        group="Все зоны"
        setGroup={vi.fn()}
        zoneOptions={["Все зоны"]}
      />,
    );

    fireEvent.mouseEnter(screen.getByRole("button", { name: "VIP-06: Занят" }));

    expect(screen.getByRole("tooltip")).toHaveTextContent("Окончание15:17");
  });
});

function busyWorkstationSnapshot(serverTime: string, packageMinutes: number): Workstation {
  return {
    id: "pc-server-delay",
    name: "VIP-06",
    group: "VIP",
    groupId: "vip",
    status: "busy",
    client: "MinuteFox",
    sessionSnapshot: {
      server_time: serverTime,
      session: { id: "session-server-delay" },
      balance_cents: 15_000,
      balance_remaining_minutes: 9,
      login_grant_remaining_minutes: 0,
      active_entitlement: { id: "three-minutes", duration_minutes: 3, remaining_minutes: packageMinutes, status: "active" },
      entitlements: [{ id: "three-minutes", duration_minutes: 3, remaining_minutes: packageMinutes, status: "active" }],
      active_tariff: null,
    } as never,
  };
}
