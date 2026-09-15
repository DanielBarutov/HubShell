import { useEffect, useState } from "react";
import { CalendarDays, Check, ChevronRight, Play, Plus, UserX, X } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { Client, Workstation } from "../../types";
import type { Reservation } from "../../api";
import { DateTimePicker, parsePickerValue } from "../../shared/components/DateTimePicker";
import { Segmented } from "../../shared/components/Segmented";
import { localDateInputValue } from "../../shared/formatters";
import { useAppDispatch } from "../../app/hooks";
import { refreshBookings } from "../workspace/workspaceSlice";

export function BookingsView({ api, pcs, clients, reservations, bookingLoading, bookingError, zoneOptions, onNewBooking, onEditBooking, refreshKey }: { api?: GameClubApi; pcs: Workstation[]; clients: Client[]; reservations: Reservation[]; bookingLoading: boolean; bookingError: string | null; zoneOptions: string[]; onNewBooking: () => void; onEditBooking: (reservation: Reservation) => void; refreshKey: number }) {
  return api ? <LiveBookingsView api={api} pcs={pcs} clients={clients} reservations={reservations} bookingLoading={bookingLoading} bookingError={bookingError} zoneOptions={zoneOptions} onNewBooking={onNewBooking} onEditBooking={onEditBooking} refreshKey={refreshKey} /> : <MockBookingsView zoneOptions={zoneOptions} onNewBooking={onNewBooking} />;
}

export function LiveBookingsView({ api, pcs, clients, reservations, bookingLoading, bookingError, zoneOptions, onNewBooking, onEditBooking, refreshKey }: { api: GameClubApi; pcs: Workstation[]; clients: Client[]; reservations: Reservation[]; bookingLoading: boolean; bookingError: string | null; zoneOptions: string[]; onNewBooking: () => void; onEditBooking: (reservation: Reservation) => void; refreshKey: number }) {
  const dispatch = useAppDispatch();
  const [actionError, setActionError] = useState<string | null>(null);
  const error = actionError ?? bookingError;
  const [transitioningId, setTransitioningId] = useState<string | null>(null);
  const [bookingGroup, setBookingGroup] = useState("Все зоны");
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const hours = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`);
  const reservationRange = (date: Date) => {
    const start = new Date(date);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return { startAt: start.toISOString(), endAt: end.toISOString() };
  };

  useEffect(() => {
    void dispatch(refreshBookings(reservationRange(selectedDate)));
    return undefined;
  }, [dispatch, refreshKey, selectedDate]);

  const resources = pcs.filter((pc) => bookingGroup === "Все зоны" || pc.group === bookingGroup);
  const timelineStart = new Date(selectedDate);
  timelineStart.setHours(0, 0, 0, 0);
  const timelineEnd = new Date(timelineStart);
  timelineEnd.setDate(timelineEnd.getDate() + 1);
  const totalMinutes = (timelineEnd.getTime() - timelineStart.getTime()) / 60000;
  const blockStyle = (reservation: Reservation) => {
    const start = new Date(reservation.start_at).getTime();
    const end = new Date(reservation.end_at).getTime();
    const left = Math.max(0, Math.min(100, ((start - timelineStart.getTime()) / 60000 / totalMinutes) * 100));
    const right = Math.max(left + 4, Math.min(100, ((end - timelineStart.getTime()) / 60000 / totalMinutes) * 100));
    return { left: `${left}%`, width: `${right - left}%` };
  };
  const statusClass = (status: string) => status === "active" ? "active" : status === "confirmed" ? "confirmed" : status === "completed" ? "completed" : status === "no_show" ? "no-show" : "pending";
  const clientNames = new Map(clients.map((client) => [client.id, client.nickname]));
  const clientLabel = (reservation: Reservation) => reservation.guest_name || (reservation.client_id ? clientNames.get(reservation.client_id) || "Клиент" : "Гость");
  const transition = async (
    reservation: Reservation,
    action: "activate" | "complete" | "no-show" | "cancel",
  ) => {
    const actionLabels = {
      activate: "активировать",
      complete: "завершить",
      "no-show": "отметить как неявку",
      cancel: "отменить",
    } as const;
    if (action === "no-show" || action === "cancel") {
      if (!window.confirm(`${actionLabels[action].replace(/^./, (value) => value.toUpperCase())} бронь ${clientLabel(reservation)}?`)) {
        return;
      }
    }
    setTransitioningId(reservation.id);
    setActionError(null);
    try {
      await (action === "activate"
        ? api.activateReservation(reservation.id)
        : action === "complete"
          ? api.completeReservation(reservation.id)
          : action === "no-show"
            ? api.markNoShowReservation(reservation.id)
            : api.cancelReservation(reservation.id));
      dispatch(refreshBookings(reservationRange(selectedDate)));
    } catch (requestError) {
      setActionError(requestError instanceof ApiError ? requestError.message : `Не удалось ${actionLabels[action]} бронь`);
    } finally {
      setTransitioningId(null);
    }
  };

  const cancel = async (reservation: Reservation) => {
    await transition(reservation, "cancel");
  };

  return <><div className="page-heading"><div><p className="eyebrow">Расписание · {selectedDate.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</p><h1>Бронирования</h1><p className="subheading">Выбранная дата · {resources.length} мест в расписании</p></div><div className="heading-actions booking-heading-actions"><DateTimePicker value={localDateInputValue(selectedDate)} onChange={(value) => { const next = parsePickerValue(value, "date"); if (Number.isFinite(next.getTime())) setSelectedDate(next); }} mode="date" label="Дата расписания" className="booking-date-picker" /><button className="primary-button" onClick={onNewBooking}><Plus size={17} /> Новая бронь</button></div></div><div className="booking-toolbar"><div className="date-chip"><ChevronRight size={15} className="rotate-180" /> <strong>{selectedDate.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</strong> <ChevronRight size={15} /></div><Segmented value={bookingGroup} onChange={setBookingGroup} options={zoneOptions} /><div className="timeline-note"><i /> {bookingLoading ? "Обновляем расписание…" : "Актуальное расписание"}</div></div>{error && <div className="search-hint error">{error}</div>}<div className="timeline"><div className="timeline-hours"><div className="resource-head">Место</div>{hours.map((hour) => <span key={hour}>{hour}</span>)}</div>{resources.map((resource) => <div className="timeline-row" key={resource.id}><div className="resource-name"><span className={`pc-status-dot ${resource.status}`} />{resource.name}</div>{hours.map((hour) => <div className="timeline-cell" key={hour} />)}{reservations.filter((reservation) => reservation.workstation_ids.includes(resource.id) && reservation.status !== "cancelled").map((reservation) => <div className={`booking-block ${statusClass(reservation.status)}`} style={blockStyle(reservation)} key={reservation.id} role="button" tabIndex={0} aria-label={`Открыть бронь ${clientLabel(reservation)}`} onClick={() => onEditBooking(reservation)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onEditBooking(reservation); } }}><strong>{clientLabel(reservation)}</strong><span>{new Date(reservation.start_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} — {new Date(reservation.end_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span><div className="booking-actions">{reservation.status === "confirmed" && <><button className="booking-action" aria-label={`Активировать бронь ${clientLabel(reservation)}`} title="Активировать" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "activate"); }}><Play size={10} /></button><button className="booking-action" aria-label={`Отметить неявку ${clientLabel(reservation)}`} title="No-show" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "no-show"); }}><UserX size={11} /></button></>}{reservation.status === "active" && <button className="booking-action" aria-label={`Завершить бронь ${clientLabel(reservation)}`} title="Завершить" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "complete"); }}><Check size={10} /></button>}{(reservation.status === "confirmed" || reservation.status === "active") && <button className="booking-action danger" aria-label={`Отменить бронь ${clientLabel(reservation)}`} title="Отменить бронь" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void cancel(reservation); }}><X size={11} /></button>}</div></div>)}</div>)}{!resources.length && <div className="timeline-empty">Нет зарегистрированных мест</div>}</div></>;
}

export function MockBookingsView({ zoneOptions, onNewBooking }: { zoneOptions: string[]; onNewBooking: () => void }) {
  const hours = Array.from({ length: 24 }, (_, hour) => `${String(hour).padStart(2, "0")}:00`);
  return <><div className="page-heading"><div><p className="eyebrow">Расписание · Сегодня</p><h1>Бронирования</h1><p className="subheading">Сегодня · 24 места в расписании</p></div><div className="heading-actions"><button className="secondary-button"><CalendarDays size={16} /> Выбрать дату</button><button className="primary-button" onClick={onNewBooking}><Plus size={17} /> Новая бронь</button></div></div><div className="booking-toolbar"><div className="date-chip"><ChevronRight size={15} className="rotate-180" /> <strong>Сегодня</strong> <ChevronRight size={15} /></div><Segmented value="Все зоны" onChange={() => undefined} options={zoneOptions} /><div className="timeline-note"><i /> Демо-расписание</div></div><div className="timeline"><div className="timeline-hours"><div className="resource-head">Место</div>{hours.map((hour) => <span key={hour}>{hour}</span>)}</div>{["VIP-01", "VIP-02", "VIP-03", "A-01", "A-02", "A-03"].map((resource) => <div className="timeline-row" key={resource}><div className="resource-name"><span className="pc-status-dot online" />{resource}</div>{hours.map((hour) => <div className="timeline-cell" key={hour} />)}{resource === "VIP-02" && <div className="booking-block confirmed" style={{ left: "26%", width: "25%" }}><strong>s1lent</strong><span>12:00 — 14:00</span></div>}{resource === "A-01" && <div className="booking-block pending" style={{ left: "43%", width: "19%" }}><strong>night_walker</strong><span>13:30 — 15:00</span></div>}{resource === "A-03" && <div className="booking-block active" style={{ left: "61%", width: "32%" }}><strong>Dasha</strong><span>14:00 — 17:00</span></div>}</div>)}</div></>;
}
