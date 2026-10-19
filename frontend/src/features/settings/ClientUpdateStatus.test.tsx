import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GameClubApi } from "../../api";
import type { BackendClientUpdateStatus } from "../../api";
import { ClientUpdateStatus } from "./ClientUpdateStatus";

const delivery: NonNullable<BackendClientUpdateStatus["deployment"]> = {
  id: "delivery-1", release_id: "v2.4.0", phase: "authorized",
  created_at: "2026-10-19T10:00:00Z", observed_at: "2026-10-19T10:01:00Z",
  confirmed: 1, total: 2,
  devices: [
    { device_id: "device-1", workstation_id: "pc-1", status: "confirmed", old_release_id: "v-old",
      running_release_id: "v2.4.0", received_at: "2026-10-19T10:01:00Z", error_code: null },
    { device_id: "device-2", workstation_id: "pc-2", status: "unreachable", old_release_id: null,
      running_release_id: null, received_at: null, error_code: null },
  ],
};
function setup(value: BackendClientUpdateStatus = { deployment: delivery }) {
  const api = new GameClubApi();
  const read = vi.spyOn(api, "getClientUpdateStatus").mockResolvedValue(value);
  return { api, read };
}
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

describe("Статус доставки клиентов", () => {
  it("показывает загрузку и отсутствие доставок без ложного успеха 0/0", async () => {
    const { api } = setup({ deployment: null });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("Загружаем статус");
    expect(await screen.findByText("Доставок ещё не было.")).toBeInTheDocument();
    expect(screen.queryByText(/0\/0/)).not.toBeInTheDocument();
  });

  it("сохраняет в знаменателе недоступный ПК и показывает его отдельной строкой", async () => {
    const { api } = setup();
    render(<ClientUpdateStatus api={api} pcs={[{ id: "pc-1", name: "PC 01", group: "Зал", status: "online" }]} />);
    expect(await screen.findByText("1/2 ПК")).toBeInTheDocument();
    expect(screen.getByText("PC 01")).toBeInTheDocument();
    expect(screen.getByText("device-2")).toBeInTheDocument();
    expect(screen.getByText("Нет свежего ответа")).toBeInTheDocument();
    expect(screen.queryByText("Доставка завершена")).not.toBeInTheDocument();
  });

  it("откат показывает ошибкой и оставляет парк закрытым", async () => {
    const { api } = setup({ deployment: { ...delivery, phase: "failed", devices: [
      delivery.devices[0], { ...delivery.devices[1], status: "rolled_back", error_code: "install_failed" },
    ] } });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(await screen.findByText("Выполнен откат")).toBeInTheDocument();
    expect(screen.getByText("Парк остаётся закрытым до устранения ошибки.")).toBeInTheDocument();
    expect(screen.getByText("Код: install_failed")).toBeInTheDocument();
    expect(screen.getByText("1/2 ПК")).toBeInTheDocument();
  });

  it("после потери связи скрывает прежний успех и позволяет получить статус заново", async () => {
    const { api, read } = setup({ deployment: { ...delivery, phase: "completed", confirmed: 2,
      devices: delivery.devices.map((device) => ({ ...device, status: "confirmed", running_release_id: "v2.4.0" })),
    } });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(await screen.findByText("Доставка завершена")).toBeInTheDocument();
    read.mockRejectedValueOnce(new Error("Сервер недоступен"));
    fireEvent.click(screen.getByRole("button", { name: "Обновить статус доставки" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Сервер недоступен");
    expect(screen.queryByText("Доставка завершена")).not.toBeInTheDocument();
    expect(screen.queryByText("2/2 ПК")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Обновить статус доставки" }));
    expect(await screen.findByText("Доставка завершена")).toBeInTheDocument();
  });

  it("опрашивает сервер и прекращает опрос после закрытия компонента", async () => {
    vi.useFakeTimers();
    const { api, read } = setup();
    const view = render(<ClientUpdateStatus api={api} pcs={[]} />);
    await act(async () => {});
    expect(read).toHaveBeenCalledTimes(1);
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(read).toHaveBeenCalledTimes(2);
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("при зависшем запросе снимает прежний статус после таймаута", async () => {
    vi.useFakeTimers();
    const { api, read } = setup();
    const view = render(<ClientUpdateStatus api={api} pcs={[]} />);
    await act(async () => {});
    expect(screen.getByText("1/2 ПК")).toBeInTheDocument();
    read.mockImplementationOnce((signal) => new Promise((_, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    await act(() => vi.advanceTimersByTimeAsync(5000));
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(screen.getByRole("alert")).toHaveTextContent("Сервер не отвечает");
    expect(screen.queryByText("1/2 ПК")).not.toBeInTheDocument();
    view.unmount();
  });
});
