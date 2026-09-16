import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BookingEditPanel, BookingPanel } from "./BookingPanels";
import type { GameClubApi, Reservation } from "../../api";
import type { Workstation } from "../../types";

const workstation: Workstation = {
  id: "pc-main-01",
  name: "Main-01",
  group: "Основной зал",
  groupId: "main",
  status: "online",
};

const reservation: Reservation = {
  id: "reservation-1",
  workstation_ids: [workstation.id],
  client_id: null,
  guest_id: null,
  guest_name: "Гость",
  start_at: "2026-09-16T12:00:00Z",
  end_at: "2026-09-16T14:00:00Z",
  status: "active",
  notes: null,
  tariff_id: null,
  created_by: "operator-1",
  created_at: "2026-09-16T10:00:00Z",
  cancelled_at: null,
  idempotency_key: "reservation-key",
};

function renderBookingPanel(api?: GameClubApi) {
  return render(
    <BookingPanel
      api={api}
      pcs={[workstation]}
      onClose={vi.fn()}
      onCreated={vi.fn()}
    />,
  );
}

describe("Панель бронирования", () => {
  it("не создаёт бронь, если проверка доступности возвращает конфликт", async () => {
    const checkReservationAvailability = vi.fn().mockResolvedValue({
      available: false,
      conflicting_reservation_ids: ["reservation-2"],
      reason: "workstation_reserved",
    });
    const createReservation = vi.fn();
    const api = { checkReservationAvailability, createReservation } as unknown as GameClubApi;

    renderBookingPanel(api);
    fireEvent.click(screen.getByRole("button", { name: "Создать бронь" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Игровое место уже занято");
    expect(checkReservationAvailability).toHaveBeenCalledWith(expect.objectContaining({
      workstation_ids: [workstation.id],
    }));
    expect(createReservation).not.toHaveBeenCalled();
  });

  it("создаёт бронь после подтверждения доступности с idempotency key", async () => {
    const checkReservationAvailability = vi.fn().mockResolvedValue({
      available: true,
      conflicting_reservation_ids: [],
      reason: null,
    });
    const createReservation = vi.fn().mockResolvedValue(reservation);
    const api = { checkReservationAvailability, createReservation } as unknown as GameClubApi;
    const onCreated = vi.fn();
    vi.stubGlobal("crypto", { randomUUID: () => "reservation-key-test" });

    render(
      <BookingPanel
        api={api}
        pcs={[workstation]}
        onClose={vi.fn()}
        onCreated={onCreated}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Создать бронь" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
    expect(createReservation).toHaveBeenCalledWith(expect.objectContaining({
      workstation_ids: [workstation.id],
      client_id: null,
      guest_name: "Гость",
    }), "reservation-key-test");
  });

  it("оставляет завершённую или активную бронь только для просмотра", () => {
    render(
      <BookingEditPanel
        api={undefined}
        reservation={reservation}
        clients={[]}
        pcs={[workstation]}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );

    expect(screen.getByText(/Для этой брони доступны только просмотр/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Сохранить изменения" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Комментарий к брони" })).toBeDisabled();
  });
});
