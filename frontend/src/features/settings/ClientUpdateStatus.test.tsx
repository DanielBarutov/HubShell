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
  it("в независимом режиме ошибка одного ПК не закрывает весь парк", async () => {
    const { api } = setup({ deployment: { ...delivery, mode: "independent", phase: "failed", devices: [
      { ...delivery.devices[0], assigned_release_id: "v2.4.0" },
      { ...delivery.devices[1], status: "rolled_back", assigned_release_id: "v-previous-job", error_code: "startup_failed" },
    ] } });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(await screen.findByText("Есть ошибки на ПК")).toBeInTheDocument();
    expect(screen.getByText("Ошибка удерживает только соответствующий ПК.")).toBeInTheDocument();
    expect(screen.getByText("К установке: v-previous-job")).toBeInTheDocument();
    expect(screen.getByText("1/2 ПК")).toBeInTheDocument();
    expect(screen.queryByText("Парк остаётся закрытым до устранения ошибки.")).not.toBeInTheDocument();
    expect(screen.queryByText(/задерживает обновление всего парка/)).not.toBeInTheDocument();
  });

  it("показывает ожидание службы и отключённый ПК отдельными состояниями", async () => {
    const { api } = setup({ deployment: { ...delivery, mode: "independent", confirmed: 0, phase: "polling", devices: [
      { ...delivery.devices[0], status: "awaiting_agent" },
      { ...delivery.devices[1], status: "disabled" },
    ] } });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(await screen.findByText("Ожидаем службу обновления")).toBeInTheDocument();
    expect(screen.getByText("Отключён оператором")).toBeInTheDocument();
    expect(screen.getByText(/ПК обновляются независимо/)).toBeInTheDocument();
    expect(screen.queryByText("Все ПК обновлены")).not.toBeInTheDocument();
  });

  it("пустой парк с назначенным выпуском не показывает успех 0/0", async () => {
    const { api } = setup({ deployment: { ...delivery, mode: "independent", confirmed: 0, total: 0,
      phase: "polling", devices: [],
    } });
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    expect(await screen.findByText("Управляемых ПК пока нет.")).toBeInTheDocument();
    expect(screen.queryByText(/0\/0/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Все ПК обновлены")).not.toBeInTheDocument();
  });

  it("повторяет только выбранный ПК и сохраняет ключ после потери ответа", async () => {
    const failed = { ...delivery, mode: "independent" as const, phase: "failed" as const, devices: [
      delivery.devices[0], { ...delivery.devices[1], deployment_id: "job-2", status: "rolled_back" as const },
    ] };
    const { api, read } = setup({ deployment: failed });
    const retry = vi.spyOn(api, "retryClientUpdateCurrent")
      .mockRejectedValueOnce(new Error("Ответ потерян")).mockResolvedValueOnce(undefined);
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    const button = await screen.findByRole("button", { name: "Повторить обновление на device-2" });
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("Ответ потерян");
    expect(screen.getByText("1/2 ПК")).toBeInTheDocument();
    read.mockResolvedValueOnce({ deployment: { ...failed, phase: "preparing", devices: [
      delivery.devices[0], { ...failed.devices[1], status: "ready" },
    ] } });
    fireEvent.click(screen.getByRole("button", { name: "Повторить обновление на device-2" }));
    expect(await screen.findByText("Готов")).toBeInTheDocument();
    expect(retry).toHaveBeenCalledTimes(2);
    expect(retry.mock.calls[0][0]).toBe("job-2");
    expect(retry.mock.calls[1][1]).toBe(retry.mock.calls[0][1]);
    expect(screen.queryByRole("button", { name: /Повторить обновление/ })).not.toBeInTheDocument();
  });

  it("отменяет зависший повтор при закрытии карточки", async () => {
    const { api } = setup({ deployment: { ...delivery, mode: "independent", phase: "failed", devices: [
      { ...delivery.devices[1], deployment_id: "job-2", status: "failed" },
    ] } });
    let requestSignal: AbortSignal | undefined;
    vi.spyOn(api, "retryClientUpdateCurrent").mockImplementation((_id, _operation, signal) => {
      requestSignal = signal;
      return new Promise((_, reject) => signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError"))));
    });
    const view = render(<ClientUpdateStatus api={api} pcs={[]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Повторить обновление на device-2" }));
    expect(screen.getByRole("button", { name: "Повторить обновление на device-2" })).toBeDisabled();
    view.unmount();
    expect(requestSignal?.aborted).toBe(true);
    await act(async () => {});
  });

  it("новый неудачный раунд получает новый ключ после потерянного ответа прежнего", async () => {
    const failed = { ...delivery, mode: "independent" as const, phase: "failed" as const, devices: [
      { ...delivery.devices[1], deployment_id: "job-2", round_id: "round-1", status: "failed" as const },
    ] };
    const { api, read } = setup({ deployment: failed });
    const retry = vi.spyOn(api, "retryClientUpdateCurrent")
      .mockRejectedValueOnce(new Error("Ответ потерян")).mockResolvedValueOnce(undefined);
    render(<ClientUpdateStatus api={api} pcs={[]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Повторить обновление на device-2" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ответ потерян");
    read.mockResolvedValue({ deployment: { ...failed, devices: [
      { ...failed.devices[0], round_id: "round-2", error_code: "next_attempt_failed" },
    ] } });
    fireEvent.click(screen.getByRole("button", { name: "Обновить статус доставки" }));
    expect(await screen.findByText("Код: next_attempt_failed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Повторить обновление на device-2" }));
    await act(async () => {});
    expect(retry).toHaveBeenCalledTimes(2);
    expect(retry.mock.calls[1][1]).not.toBe(retry.mock.calls[0][1]);
  });

});
