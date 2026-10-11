import { useEffect, useState } from "react";
import {
  CalendarDays,
  ChevronRight,
  Crown,
  Flag,
  Monitor,
  Play,
  Plus,
  UserRound,
  UserX,
  X,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { Client, Workstation } from "../../types";
import type { Reservation } from "../../api";
import {
  DateTimePicker,
  parsePickerValue,
} from "../../shared/components/DateTimePicker";
import { Segmented } from "../../shared/components/Segmented";
import { localDateInputValue } from "../../shared/formatters";
import { useAppDispatch } from "../../app/hooks";
import { refreshBookings } from "../workspace/workspaceSlice";

export function BookingsView({
  api,
  pcs,
  clients,
  reservations,
  bookingLoading,
  bookingError,
  zoneOptions,
  onNewBooking,
  onEditBooking,
  refreshKey,
}: {
  api?: GameClubApi;
  pcs: Workstation[];
  clients: Client[];
  reservations: Reservation[];
  bookingLoading: boolean;
  bookingError: string | null;
  zoneOptions: string[];
  onNewBooking: () => void;
  onEditBooking: (reservation: Reservation) => void;
  refreshKey: number;
}) {
  return api ? (
    <LiveBookingsView
      api={api}
      pcs={pcs}
      clients={clients}
      reservations={reservations}
      bookingLoading={bookingLoading}
      bookingError={bookingError}
      zoneOptions={zoneOptions}
      onNewBooking={onNewBooking}
      onEditBooking={onEditBooking}
      refreshKey={refreshKey}
    />
  ) : (
    <MockBookingsView zoneOptions={zoneOptions} onNewBooking={onNewBooking} />
  );
}

function BookingFooter({
  total,
  free,
  vip,
  next,
}: {
  total: number;
  free: number;
  vip: number;
  next: string;
}) {
  return (
    <>
      <div className="booking-legend mt-3 flex flex-wrap gap-2 text-xs text-base-content/75!">
        {[
          "Активная бронь",
          "Резерв",
          "VIP бронь",
          "Ночная бронь",
          "Ожидание оплаты",
          "Текущее время",
          "Технический перерыв",
        ].map((label, index) => (
          <span
            className="badge badge-outline gap-2 border-primary/20! bg-base-100/65! px-3 py-3"
            key={label}
          >
            <i
              className={`h-2.5 w-2.5 rounded-full ${index === 0 ? "bg-success" : index === 1 ? "bg-warning" : index === 2 ? "bg-[#a05fff]" : index === 3 ? "bg-error" : index === 4 ? "bg-neutral-content/60" : index === 5 ? "bg-primary" : "bg-base-300"}`}
            />
            {label}
          </span>
        ))}
      </div>
      <div className="booking-summary-grid mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        <div className="card min-h-[108px] flex-row items-center gap-3 border border-primary/25! bg-base-100/85! p-4 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/30! bg-primary/15! text-primary!">
            <CalendarDays size={19} />
          </div>
          <div className="min-w-0">
            <strong className="block text-sm">Сегодня: {total} броней</strong>
            <span className="text-xs text-base-content/60">
              Из 24 возможных мест
            </span>
          </div>
          <div className="ml-auto grid size-12 shrink-0 place-items-center rounded-full border-4 border-primary/20 border-t-primary border-r-primary text-sm font-bold text-primary">
            {Math.round((total / 24) * 100)}%
          </div>
        </div>
        <div className="card min-h-[108px] flex-row items-center gap-3 border border-primary/25! bg-base-100/85! p-4 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-success/30! bg-success/15! text-success!">
            <Monitor size={19} />
          </div>
          <div>
            <strong className="block text-sm">Свободных слотов</strong>
            <span className="text-xs text-base-content/60">
              Доступно для бронирования
            </span>
          </div>
          <div className="ml-auto text-right">
            <strong className="block text-xl text-success">{free}</strong>
            <div
              className="mt-1 flex items-end justify-end gap-1"
              aria-hidden="true"
            >
              {Array.from({ length: 5 }, (_, index) => (
                <i
                  className={`w-1.5 rounded-full ${index < Math.min(5, Math.ceil(free / 4)) ? "h-4 bg-success" : "h-2 bg-base-300"}`}
                  key={index}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="card min-h-[108px] flex-row items-center gap-3 border border-primary/25! bg-base-100/85! p-4 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-[#a05fff]/40! bg-[#a05fff]/15! text-[#c9a8ff]!">
            <Crown size={19} />
          </div>
          <div className="min-w-0">
            <strong className="block text-sm">VIP брони</strong>
            <span className="text-xs text-base-content/60">
              {total
                ? `${Math.round((vip / total) * 100)}% от всех броней`
                : "Нет броней"}
            </span>
          </div>
          <div className="ml-auto text-right" aria-label={`${vip} VIP брони`}>
            <strong className="block text-xl text-[#c9a8ff]">{vip}</strong>
            <div
              className="mt-1 flex items-end justify-end gap-1"
              aria-hidden="true"
            >
              {Array.from({ length: 4 }, (_, index) => (
                <i
                  className={`w-1.5 rounded-full ${index < Math.min(4, vip) ? "h-4 bg-[#a05fff]" : "h-2 bg-base-300"}`}
                  key={index}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="card min-h-[108px] flex-row items-center gap-3 border border-primary/25! bg-base-100/85! p-4 shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-accent/30! bg-accent/15! text-accent!">
            <UserRound size={19} />
          </div>
          <div className="min-w-0">
            <strong className="block text-sm">Ближайшая бронь</strong>
            <span className="text-xs text-base-content/60">
              Следующее событие
            </span>
          </div>
          <span className="ml-auto truncate text-right text-sm font-bold text-primary">
            {next}
          </span>
        </div>
      </div>
    </>
  );
}

export function LiveBookingsView({
  api,
  pcs,
  clients,
  reservations,
  bookingLoading,
  bookingError,
  zoneOptions,
  onNewBooking,
  onEditBooking,
  refreshKey,
}: {
  api: GameClubApi;
  pcs: Workstation[];
  clients: Client[];
  reservations: Reservation[];
  bookingLoading: boolean;
  bookingError: string | null;
  zoneOptions: string[];
  onNewBooking: () => void;
  onEditBooking: (reservation: Reservation) => void;
  refreshKey: number;
}) {
  const dispatch = useAppDispatch();
  const [actionError, setActionError] = useState<string | null>(null);
  const error = actionError ?? bookingError;
  const [transitioningId, setTransitioningId] = useState<string | null>(null);
  const [bookingGroup, setBookingGroup] = useState("Все зоны");
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const hours = Array.from(
    { length: 24 },
    (_, hour) => `${String(hour).padStart(2, "0")}:00`,
  );
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

  const resources = pcs.filter(
    (pc) => bookingGroup === "Все зоны" || pc.group === bookingGroup,
  );
  const timelineStart = new Date(selectedDate);
  timelineStart.setHours(0, 0, 0, 0);
  const timelineEnd = new Date(timelineStart);
  timelineEnd.setDate(timelineEnd.getDate() + 1);
  const totalMinutes =
    (timelineEnd.getTime() - timelineStart.getTime()) / 60000;
  const blockStyle = (reservation: Reservation) => {
    const start = new Date(reservation.start_at).getTime();
    const end = new Date(reservation.end_at).getTime();
    const left = Math.max(
      0,
      Math.min(
        100,
        ((start - timelineStart.getTime()) / 60000 / totalMinutes) * 100,
      ),
    );
    const right = Math.max(
      left + 4,
      Math.min(
        100,
        ((end - timelineStart.getTime()) / 60000 / totalMinutes) * 100,
      ),
    );
    return { left: `${left}%`, width: `${right - left}%` };
  };
  const statusClass = (status: string) =>
    status === "active"
      ? "active border-success/70! bg-success/25! text-success-content!"
      : status === "confirmed"
        ? "confirmed border-primary/70! bg-primary/25! text-primary-content!"
        : status === "completed"
          ? "completed border-accent/70! bg-accent/20! text-accent-content!"
          : status === "no_show"
            ? "no-show border-error/70! bg-error/20! text-error-content!"
            : "pending border-warning/70! bg-warning/20! text-warning-content!";
  const clientNames = new Map(
    clients.map((client) => [client.id, client.nickname]),
  );
  const clientLabel = (reservation: Reservation) =>
    reservation.guest_name ||
    (reservation.client_id
      ? clientNames.get(reservation.client_id) || "Клиент"
      : "Гость");
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
      if (
        !window.confirm(
          `${actionLabels[action].replace(/^./, (value) => value.toUpperCase())} бронь ${clientLabel(reservation)}?`,
        )
      ) {
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
      setActionError(
        requestError instanceof ApiError
          ? requestError.message
          : `Не удалось ${actionLabels[action]} бронь`,
      );
    } finally {
      setTransitioningId(null);
    }
  };

  const cancel = async (reservation: Reservation) => {
    await transition(reservation, "cancel");
  };

  const visibleReservations = reservations.filter(
    (reservation) => reservation.status !== "cancelled",
  );
  const vipReservations = visibleReservations.filter((reservation) =>
    reservation.workstation_ids.some(
      (id) => pcs.find((pc) => pc.id === id)?.group === "VIP-зона",
    ),
  ).length;
  const occupiedSlotCount = new Set(
    visibleReservations.flatMap((reservation) => reservation.workstation_ids),
  ).size;
  const capacity = Math.max(24, resources.length);
  const nextReservation = visibleReservations.sort(
    (left, right) => Date.parse(left.start_at) - Date.parse(right.start_at),
  )[0];
  return (
    <>
      <div className="mt-7 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs text-base-content/60!">
            Расписание ·{" "}
            {selectedDate.toLocaleDateString("ru-RU", {
              day: "numeric",
              month: "long",
            })}
          </p>
          <h1 className="text-3xl font-bold tracking-tight">Бронирования</h1>
          <p className="mt-1 text-sm text-base-content/65!">
            Выбранная дата · {resources.length} мест в расписании
          </p>
        </div>
        <div className="heading-actions booking-heading-actions flex flex-wrap items-center gap-2">
          <DateTimePicker
            value={localDateInputValue(selectedDate)}
            onChange={(value) => {
              const next = parsePickerValue(value, "date");
              if (Number.isFinite(next.getTime())) setSelectedDate(next);
            }}
            mode="date"
            label="Дата расписания"
            className="booking-date-picker"
          />
          <button
            className="primary-button btn btn-primary btn-sm"
            onClick={onNewBooking}
          >
            <Plus size={17} /> Новая бронь
          </button>
        </div>
      </div>
      <div className="booking-toolbar mb-4 flex flex-wrap items-center gap-2">
        <div className="date-chip flex items-center gap-1 rounded-lg border border-primary/20! bg-base-100/55! px-3 py-2 text-sm shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <ChevronRight size={15} className="rotate-180" />{" "}
          <strong>
            {selectedDate.toLocaleDateString("ru-RU", {
              day: "numeric",
              month: "long",
            })}
          </strong>{" "}
          <ChevronRight size={15} />
        </div>
        <Segmented
          value={bookingGroup}
          onChange={setBookingGroup}
          options={zoneOptions}
        />
        <div className="timeline-note flex items-center gap-2 text-xs text-base-content/60!">
          <i className="h-1.5 w-1.5 rounded-full bg-primary" />{" "}
          {bookingLoading ? "Обновляем расписание…" : "Актуальное расписание"}
        </div>
      </div>
      {error && (
        <div className="search-hint error mb-3 rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!">
          {error}
        </div>
      )}
      <div className="timeline flex flex-col overflow-auto rounded-xl border border-primary/35! bg-base-100/55! pt-4 text-base-content! shadow-[0_0_28px_rgba(168,255,77,.08)] backdrop-blur-md">
        <div className="timeline-hours grid min-w-[980px] grid-cols-[120px_repeat(24,minmax(36px,1fr))] border-b border-primary/20! bg-base-200/70! text-xs text-base-content/70!">
          <div className="resource-head flex items-center px-3 py-3">Место</div>
          {hours.map((hour) => (
            <span className="px-1 py-3 text-center" key={hour}>
              {hour}
            </span>
          ))}
        </div>
        {resources.map((resource) => (
          <div
            className="timeline-row relative grid min-h-[70px] min-w-[980px] grid-cols-[120px_repeat(24,minmax(36px,1fr))] border-b border-primary/15! last:border-b-0"
            key={resource.id}
          >
            <div className="resource-name z-10 flex items-center gap-1 bg-base-200/70! px-3 text-xs font-semibold">
              <span
                className={`pc-status-dot h-2 w-2 rounded-full ${resource.status === "online" ? "bg-success" : resource.status === "busy" ? "bg-secondary" : "bg-warning"}`}
              />
              {resource.name}
            </div>
            {hours.map((hour) => (
              <div
                className="timeline-cell border-l border-primary/10!"
                key={hour}
              />
            ))}
            {reservations
              .filter(
                (reservation) =>
                  reservation.workstation_ids.includes(resource.id) &&
                  reservation.status !== "cancelled",
              )
              .map((reservation) => (
                <div
                  className={`booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-primary/30! bg-primary/20! px-2 py-1 text-xs text-base-content! shadow-sm ${statusClass(reservation.status)}`}
                  style={blockStyle(reservation)}
                  key={reservation.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`Открыть бронь ${clientLabel(reservation)}`}
                  onClick={() => onEditBooking(reservation)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onEditBooking(reservation);
                    }
                  }}
                >
                  <strong className="truncate">
                    {clientLabel(reservation)}
                  </strong>
                  <span className="truncate text-[10px]">
                    {new Date(reservation.start_at).toLocaleTimeString(
                      "ru-RU",
                      { hour: "2-digit", minute: "2-digit" },
                    )}{" "}
                    —{" "}
                    {new Date(reservation.end_at).toLocaleTimeString("ru-RU", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  <div className="booking-actions mt-1 flex gap-1">
                    {reservation.status === "confirmed" && (
                      <>
                        <button
                          className="booking-action btn btn-ghost btn-xs"
                          aria-label={`Активировать бронь ${clientLabel(reservation)}`}
                          title="Активировать"
                          disabled={transitioningId === reservation.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void transition(reservation, "activate");
                          }}
                        >
                          <Play size={10} />
                        </button>
                        <button
                          className="booking-action btn btn-ghost btn-xs"
                          aria-label={`Отметить неявку ${clientLabel(reservation)}`}
                          title="No-show"
                          disabled={transitioningId === reservation.id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void transition(reservation, "no-show");
                          }}
                        >
                          <UserX size={11} />
                        </button>
                      </>
                    )}
                    {reservation.status === "active" && (
                      <button
                        className="booking-action btn btn-ghost btn-xs"
                        aria-label={`Завершить бронь ${clientLabel(reservation)}`}
                        title="Завершить"
                        disabled={transitioningId === reservation.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void transition(reservation, "complete");
                        }}
                      >
                        <Flag size={10} />
                      </button>
                    )}
                    {(reservation.status === "confirmed" ||
                      reservation.status === "active") && (
                      <button
                        className="booking-action danger btn btn-ghost btn-xs"
                        aria-label={`Отменить бронь ${clientLabel(reservation)}`}
                        title="Отменить бронь"
                        disabled={transitioningId === reservation.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void cancel(reservation);
                        }}
                      >
                        <X size={11} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
          </div>
        ))}
        {!resources.length && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-6 text-sm text-base-content/60!">
            Нет зарегистрированных мест
          </div>
        )}
      </div>
      <BookingFooter
        total={visibleReservations.length}
        free={Math.max(0, capacity - occupiedSlotCount)}
        vip={vipReservations}
        next={
          nextReservation
            ? new Date(nextReservation.start_at).toLocaleTimeString("ru-RU", {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "Нет броней"
        }
      />
    </>
  );
}

export function MockBookingsView({
  zoneOptions,
  onNewBooking,
}: {
  zoneOptions: string[];
  onNewBooking: () => void;
}) {
  const hours = Array.from(
    { length: 24 },
    (_, hour) => `${String(hour).padStart(2, "0")}:00`,
  );
  const slots = [
    "Avalonia Linux smoke",
    "PC5",
    "VIP-01",
    "VIP-02",
    "VIP-03",
    "VIP-04",
  ];
  return (
    <>
      <div className="mt-4 mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs text-base-content/60!">
            Расписание · 3 октября
          </p>
          <h1 className="text-3xl font-bold tracking-tight">Бронирования</h1>
          <p className="mt-1 text-sm text-base-content/65!">
            Выбранная дата · 6 мест в расписании
          </p>
        </div>
        <div className="heading-actions flex flex-wrap items-center gap-2">
          <button
            className="secondary-button btn btn-outline btn-sm"
            onClick={onNewBooking}
          >
            <CalendarDays size={16} /> 03 окт. 2026 г.
          </button>
          <button
            className="primary-button btn btn-primary btn-sm"
            onClick={onNewBooking}
          >
            <Plus size={17} /> Новая бронь
          </button>
        </div>
      </div>
      <div className="booking-toolbar mb-4 flex flex-wrap items-center gap-2">
        <div className="date-chip flex items-center gap-1 rounded-lg border border-primary/20! bg-base-100/55! px-3 py-2 text-sm shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <ChevronRight size={15} className="rotate-180" />{" "}
          <strong>3 октября</strong> <ChevronRight size={15} />
        </div>
        <Segmented
          value="Все зоны"
          onChange={() => undefined}
          options={zoneOptions}
        />
        <div className="timeline-note flex items-center gap-2 text-xs text-base-content/60!">
          <i className="h-1.5 w-1.5 rounded-full bg-success" /> Актуальное
          расписание
        </div>
      </div>
      <div className="timeline relative flex flex-col overflow-auto rounded-xl border border-primary/35! bg-base-100/55! pt-4 text-base-content! shadow-[0_0_28px_rgba(168,255,77,.08)] backdrop-blur-md">
        <div className="timeline-hours grid min-w-[980px] grid-cols-[120px_repeat(24,minmax(36px,1fr))] border-b border-primary/20! bg-base-200/70! text-xs text-base-content/70!">
          <div className="resource-head flex items-center px-3 py-3">Место</div>
          {hours.map((hour) => (
            <span className="px-1 py-3 text-center" key={hour}>
              {hour}
            </span>
          ))}
        </div>
        <div
          className="pointer-events-none absolute bottom-4 top-4 z-30 w-px border-l-2 border-dashed border-primary shadow-[0_0_8px_rgba(168,255,77,.9)]"
          style={{ left: "62%" }}
          aria-hidden="true"
        >
          <span className="absolute top-1 left-1/2 -translate-x-1/2 rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold text-primary-content">
            14:00
          </span>
        </div>
        {slots.map((resource) => (
          <div
            className="timeline-row relative grid min-h-[70px] min-w-[980px] grid-cols-[120px_repeat(24,minmax(36px,1fr))] border-b border-primary/15! last:border-b-0"
            key={resource}
          >
            <div className="resource-name z-10 flex items-center gap-1 bg-base-200/70! px-3 text-xs font-semibold">
              <span
                className={`pc-status-dot h-2 w-2 rounded-full ${resource === "PC5" ? "bg-warning" : resource === "VIP-02" ? "bg-secondary" : "bg-success"}`}
              />
              {resource}
            </div>
            {hours.map((hour) => (
              <div
                className="timeline-cell border-l border-primary/10!"
                key={hour}
              />
            ))}
            {resource === "VIP-01" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-[#a05fff]/75! bg-[#a05fff]/25! py-1 pl-10 pr-2 text-xs text-[#f0e2ff]! shadow-sm"
                style={{ left: "66.7%", width: "12.5%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-[#a05fff]/80 text-[10px] font-bold text-[#f0e2ff]">
                  SM
                </span>
                <strong className="truncate">SilverMoon</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  VIP
                </span>
                <span className="truncate text-[10px]">
                  16:00 — 19:00 · VIP
                </span>
              </div>
            )}
            {resource === "Avalonia Linux smoke" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-success/70! bg-success/25! py-1 pl-10 pr-2 text-xs text-base-content! shadow-sm"
                style={{ left: "54.2%", width: "8.3%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-primary text-[10px] font-bold text-primary-content">
                  DA
                </span>
                <strong className="truncate">DanielBarutov</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  Поминутно
                </span>
                <span className="truncate text-[10px]">13:00 — 15:00</span>
              </div>
            )}
            {resource === "PC5" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-warning/70! bg-warning/20! py-1 pl-10 pr-2 text-xs text-base-content! shadow-sm"
                style={{ left: "75%", width: "12.5%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-base-300 text-base-content/70">
                  <UserRound size={13} />
                </span>
                <strong className="truncate">Резерв</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  Обычный зал
                </span>
                <span className="truncate text-[10px]">18:00 — 21:00</span>
              </div>
            )}
            {resource === "VIP-03" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-neutral-content/50! bg-neutral-content/20! py-1 pl-10 pr-2 text-xs text-base-content! shadow-sm"
                style={{ left: "41.7%", width: "8.3%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-base-300 text-base-content/70">
                  <UserRound size={13} />
                </span>
                <strong className="truncate">Ожидание оплаты</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  Обычный зал
                </span>
                <span className="truncate text-[10px]">10:00 — 12:00</span>
              </div>
            )}
            {resource === "VIP-02" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-error/70! bg-error/25! py-1 pl-10 pr-2 text-xs text-base-content! shadow-sm"
                style={{ left: "83.3%", width: "12.5%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-error/80 text-[10px] font-bold text-error-content">
                  NB
                </span>
                <strong className="truncate">Ночная бронь</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  VIP
                </span>
                <span className="truncate text-[10px]">20:00 — 23:00</span>
              </div>
            )}
            {resource === "VIP-04" && (
              <div
                className="booking-block absolute top-1 bottom-1 z-20 flex min-w-16 flex-col justify-center overflow-hidden rounded-lg border border-success/70! bg-success/25! py-1 pl-10 pr-2 text-xs text-base-content! shadow-sm"
                style={{ left: "37.5%", width: "6.25%" }}
              >
                <span className="absolute left-2 grid size-6 place-items-center rounded-full bg-success text-[10px] font-bold text-success-content">
                  MR
                </span>
                <strong className="truncate">m1rage</strong>
                <span className="truncate text-[10px] text-base-content/70!">
                  VIP
                </span>
                <span className="truncate text-[10px]">09:00 — 10:30</span>
              </div>
            )}
          </div>
        ))}
      </div>
      <BookingFooter total={6} free={18} vip={2} next="Сегодня, 09:00" />
    </>
  );
}
