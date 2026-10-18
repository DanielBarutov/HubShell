import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MapView } from "./MapScreen";
import type { Workstation } from "../../types";

const workstations: Workstation[] = [
  { id: "pc-online", name: "VIP-01", group: "VIP", groupId: "vip", status: "online", position: 1 },
  { id: "pc-offline", name: "Main-02", group: "Основной зал", groupId: "main", status: "offline", position: 2 },
];

afterEach(() => window.localStorage.clear());

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
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Продать товар" }));

    expect(onSellProduct).toHaveBeenCalledTimes(1);
  });

  it("показывает пустую ячейку и сохраняет перенос в неё", async () => {
    const onPositionsChange = vi.fn().mockResolvedValue(undefined);
    const dataTransfer = {
      dropEffect: "",
      effectAllowed: "",
      getData: vi.fn(() => "pc-offline"),
      setData: vi.fn(),
    };

    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        onPositionsChange={onPositionsChange}
        pcs={workstations}
      />,
    );

    expect(
      screen.getByLabelText("Пустая ячейка 3").firstElementChild,
    ).toBeEmptyDOMElement();
    fireEvent.click(screen.getByRole("button", { name: "Редактировать карту" }));
    fireEvent.dragStart(
      screen.getByRole("button", { name: "Main-02: Не в сети" }),
      { dataTransfer },
    );
    const target = screen.getByLabelText("Пустая ячейка 3");
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });

    await waitFor(() =>
      expect(onPositionsChange).toHaveBeenCalledWith([
        { workstationId: "pc-offline", position: 3 },
      ]),
    );
  });

  it("меняет местами занятые ячейки в одной зоне", async () => {
    const onPositionsChange = vi.fn().mockResolvedValue(undefined);
    const dataTransfer = {
      dropEffect: "",
      effectAllowed: "",
      getData: vi.fn(() => "pc-first"),
      setData: vi.fn(),
    };
    const positionedWorkstations: Workstation[] = [
      { id: "pc-first", name: "PC-01", group: "Основной зал", status: "online", position: 1 },
      { id: "pc-third", name: "PC-03", group: "Основной зал", status: "online", position: 3 },
    ];

    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        onPositionsChange={onPositionsChange}
        pcs={positionedWorkstations}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Редактировать карту" }));
    fireEvent.dragStart(screen.getByRole("button", { name: "PC-01: Свободен" }), {
      dataTransfer,
    });
    const target = screen
      .getByRole("button", { name: "PC-03: Свободен" })
      .closest(".map-slot");
    if (!target) throw new Error("Не найдена ячейка PC-03");
    fireEvent.dragOver(target, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });

    await waitFor(() =>
      expect(onPositionsChange).toHaveBeenCalledWith([
        { workstationId: "pc-first", position: 3 },
        { workstationId: "pc-third", position: 1 },
      ]),
    );
  });

  it("объединяет зоны в одну настраиваемую сетку", () => {
    render(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={workstations}
      />,
    );

    expect(screen.queryByText("Обычный зал")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Столбцы карты")).toHaveValue("10");
    expect(screen.getByLabelText("Ряды карты")).toHaveValue("4");
    fireEvent.change(screen.getByLabelText("Столбцы карты"), {
      target: { value: "4" },
    });
    fireEvent.change(screen.getByLabelText("Ряды карты"), {
      target: { value: "2" },
    });

    expect(window.localStorage.getItem("gameshell.map-grid-columns")).toBe("4");
    expect(window.localStorage.getItem("gameshell.map-grid-rows")).toBe("2");
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
      />,
    );

    rerender(
      <MapView
        onPc={vi.fn()}
        onSalePc={vi.fn()}
        onBookPc={vi.fn()}
        onEditPc={vi.fn()}
        pcs={[busyWorkstationSnapshot("2026-09-17T12:06:00Z", 3)]}
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
