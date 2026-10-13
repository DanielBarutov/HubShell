import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkstationPanel } from "./WorkstationPanel";
import { PcPanel } from "./PcPanel";
import { MapView } from "./MapScreen";
import { ApiError } from "../../api";
import { TariffPanel } from "../catalog/CatalogScreen";
import { SaleWorkspace } from "../catalog/SaleWorkspace";
import type { BackendTariff, GameClubApi } from "../../api";
import type { Workstation } from "../../types";

const xbox: Workstation = {id: "xbox-1", name: "Xbox 1", equipmentType: "xbox", group: "Зал", groupId: "main", status: "online"};
const tariff: BackendTariff = {id: "xbox-hour", name: "Xbox час", equipment_type: "xbox", group_id: null, duration_minutes: 60, price_cents: 10000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "xbox-hour", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0, audience: "guest", sale_channel: "operator"};

describe("Xbox", () => {
  it("показывает сохранённый отказ OFF на карте и в панели свободного Xbox", () => {
    const pending = {...xbox, relayOffPending: true};
    render(<MapView pcs={[pending]} onPc={vi.fn()} onSalePc={vi.fn()} onBookPc={vi.fn()} onEditPc={vi.fn()} />);
    expect(screen.getByText("OFF не подтверждён")).toBeVisible();
    render(<PcPanel pc={pending} onClose={vi.fn()} onEdit={vi.fn()} onBook={vi.fn()} onDeposit={vi.fn()} onOpenSale={vi.fn()} onSessionChanged={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("сервер повторит OFF");
  });

  it("предупреждает об отказе OFF после успешного завершения", async () => {
    const stopXboxSession = vi.fn().mockResolvedValue({status: "completed", relay_off_pending: true});
    const onSessionChanged = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<PcPanel pc={{...xbox, status: "busy", sessionId: "session-1"}} api={{stopXboxSession} as unknown as GameClubApi} onClose={vi.fn()} onEdit={vi.fn()} onBook={vi.fn()} onDeposit={vi.fn()} onOpenSale={vi.fn()} onSessionChanged={onSessionChanged} />);
    fireEvent.click(screen.getByRole("button", {name: "Прервать сессию"}));
    await screen.findByText(/Реле не подтвердило выключение; сервер повторит OFF/);
    expect(onSessionChanged).toHaveBeenCalledTimes(1);
  });

  it("показывает ошибку ON и не объявляет продажу успешной", async () => {
    const confirmXboxSale = vi.fn().mockRejectedValue(new ApiError(503, "Реле не подтвердило включение"));
    const onSaved = vi.fn();
    render(<SaleWorkspace api={{confirmXboxSale} as unknown as GameClubApi} pc={xbox} initialClient={null} initialProduct={null} clients={[]} cashShifts={[]} tariffs={[tariff]} products={[]} categories={[]} onClose={vi.fn()} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", {name: /Xbox час/}));
    fireEvent.click(screen.getByRole("button", {name: /Перевод/}));
    fireEvent.click(screen.getByRole("button", {name: /Оформить продажу/}));
    await screen.findByText("Реле не подтвердило включение");
    expect(onSaved).not.toHaveBeenCalled();
  });
  it("проверяет сохранённое реле и блокирует тест после изменения адреса", async () => {
    const testWorkstationRelay = vi.fn().mockResolvedValue({state: "on"});
    render(<WorkstationPanel workstation={{...xbox, relaySettings: {ip: "192.168.3.10", port: 8081, deviceid: "1001ee63f1"}}} api={{testWorkstationRelay} as unknown as GameClubApi} groups={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("IP реле")).toHaveValue("192.168.3.10");
    fireEvent.click(screen.getByRole("button", {name: "Тест: включить"}));
    await screen.findByText("Реле включено; состояние подтверждено");
    expect(testWorkstationRelay).toHaveBeenCalledWith("xbox-1", "on");
    testWorkstationRelay.mockResolvedValue({state: "off"});
    fireEvent.click(screen.getByRole("button", {name: "Тест: выключить"}));
    await screen.findByText("Реле выключено; состояние подтверждено");
    expect(testWorkstationRelay).toHaveBeenLastCalledWith("xbox-1", "off");
    fireEvent.change(screen.getByLabelText("IP реле"), {target: {value: "192.168.3.11"}});
    expect(screen.getByRole("button", {name: "Тест: включить"})).toBeDisabled();
    expect(screen.getByRole("button", {name: "Тест: выключить"})).toBeDisabled();
  });

  it("удаляет настройки реле при отключении опции", async () => {
    const updateWorkstation = vi.fn().mockResolvedValue({});
    render(<WorkstationPanel workstation={{...xbox, relaySettings: {ip: "192.168.3.10", port: 8081, deviceid: "1001ee63f1"}}} api={{updateWorkstation} as unknown as GameClubApi} groups={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Настроить реле"));
    fireEvent.click(screen.getByRole("button", {name: "Сохранить изменения"}));
    await waitFor(() => expect(updateWorkstation).toHaveBeenCalledWith("xbox-1", expect.objectContaining({relay_settings: null})));
  });

  it("создаёт место без MAC, клиента и возможностей ПК", async () => {
    const registerWorkstation = vi.fn().mockResolvedValue({});
    render(<WorkstationPanel api={{registerWorkstation} as unknown as GameClubApi} groups={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Тип места"), {target: {value: "xbox"}});
    expect(screen.queryByLabelText("MAC-адрес игрового ПК")).not.toBeInTheDocument();
    expect(screen.queryByText(/После запуска EXE/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Название"), {target: {value: "Xbox 1"}});
    fireEvent.click(screen.getByRole("button", {name: "Добавить место"}));
    await waitFor(() => expect(registerWorkstation).toHaveBeenCalledWith(expect.objectContaining({name: "Xbox 1", equipment_type: "xbox", mac_address: undefined, capabilities: []})));
  });

  it("создаёт простой опубликованный тариф Xbox без расписания", async () => {
    const createTariff = vi.fn().mockResolvedValue(tariff);
    render(<TariffPanel api={{createTariff} as unknown as GameClubApi} groups={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Тип оборудования"), {target: {value: "xbox"}});
    expect(screen.queryByLabelText("Зона")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Для кого доступен тариф")).not.toBeInTheDocument();
    expect(screen.queryByText("Ограничить тариф ежедневными окнами")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Название"), {target: {value: "Xbox час"}});
    fireEvent.click(screen.getByRole("button", {name: "Создать тариф"}));
    await waitFor(() => expect(createTariff).toHaveBeenCalledWith(expect.objectContaining({equipment_type: "xbox", name: "Xbox час", group_id: null, audience: "guest", lifecycle: "published", time_restricted: false})));
  });

  it("продаёт гостю только Xbox-время и не выдаёт V2-допуск", async () => {
    const confirmXboxSale = vi.fn().mockResolvedValue({id: "payment-1", status: "confirmed"});
    const prepareGuestSessionAccess = vi.fn();
    const onSaved = vi.fn();
    render(<SaleWorkspace api={{confirmXboxSale, prepareGuestSessionAccess} as unknown as GameClubApi} pc={{...xbox, status: "busy", sessionId: "session-1"}} initialClient={null} initialProduct={null} clients={[]} cashShifts={[]} tariffs={[tariff, {...tariff, id: "pc-hour", equipment_type: "pc", name: "ПК час"}]} products={[]} categories={[]} onClose={vi.fn()} onSaved={onSaved} />);
    expect(screen.queryByRole("button", {name: /ПК час/})).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name: /Клиент/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: /Xbox час/}));
    fireEvent.click(screen.getByRole("button", {name: /Перевод/}));
    fireEvent.click(screen.getByRole("button", {name: /Оформить продажу/}));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(confirmXboxSale).toHaveBeenCalledWith(expect.objectContaining({workstation_id: "xbox-1", session_id: "session-1", tariff_id: "xbox-hour", payment_parts: [{method: "transfer", amount_cents: 10000}]}), expect.any(String));
    expect(prepareGuestSessionAccess).not.toHaveBeenCalled();
  });

  it("завершает Xbox без команд ПК, депозита и бронирования", async () => {
    const stopXboxSession = vi.fn().mockResolvedValue({});
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<PcPanel pc={{...xbox, status: "busy", sessionId: "session-1"}} api={{stopXboxSession} as unknown as GameClubApi} onClose={vi.fn()} onEdit={vi.fn()} onBook={vi.fn()} onDeposit={vi.fn()} onOpenSale={vi.fn()} onSessionChanged={vi.fn()} />);
    expect(screen.queryByRole("button", {name: "Заблокировать клиент"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Перезапустить ПК"})).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name: "Забронировать место"})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {name: "Прервать сессию"}));
    await waitFor(() => expect(stopXboxSession).toHaveBeenCalledWith("session-1"));
  });
});
