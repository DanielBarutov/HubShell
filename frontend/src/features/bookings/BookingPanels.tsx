import { useEffect, useMemo, useState } from "react";
import { ChevronRight, Search, UserX } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { Reservation } from "../../api";
import { toUiClient } from "../../adapters";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import {
  formatRussianPhone,
  getSearchField,
  localDateTimeValue,
} from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client, Workstation } from "../../types";
import { generateUUID } from "../../utils/uuid";

export function BookingPanel({
  initialWorkstationId,
  onClose,
  onCreated,
  pcs,
  clients: clientList,
  api,
}: {
  initialWorkstationId?: string;
  onClose: () => void;
  onCreated: () => void;
  pcs: Workstation[];
  clients: Client[];
  api?: GameClubApi;
}) {
  const now = useMemo(() => {
    const value = new Date();
    value.setMinutes(value.getMinutes() < 30 ? 30 : 0, 0, 0);
    if (value.getMinutes() === 0) value.setHours(value.getHours() + 1);
    return value;
  }, []);
  const [workstationId, setWorkstationId] = useState(
    initialWorkstationId ?? pcs[0]?.id ?? "",
  );
  const [startAt, setStartAt] = useState(localDateTimeValue(now));
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [clientQuery, setClientQuery] = useState("");
  const [clientId, setClientId] = useState<string | undefined>();
  const [clientCandidate, setClientCandidate] = useState<Client | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const clientField = getSearchField(clientQuery);
  const endAt = useMemo(
    () => localDateTimeValue(new Date(new Date(startAt).getTime() + durationMinutes * 60 * 1000)),
    [durationMinutes, startAt],
  );

  useEffect(() => {
    if (!workstationId && pcs[0]) {
      setWorkstationId(pcs[0].id);
    }
  }, [pcs, workstationId]);

  useEffect(() => {
    if (!clientField) {
      setClientCandidate(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const normalized = clientQuery.trim().toLowerCase();
        const digits = clientQuery.replace(/\D/g, "");
        const found = api
          ? (await api.searchClients(clientQuery, clientField)).map(toUiClient)
          : clientList.filter((client) => clientField === "phone"
            ? client.phone.replace(/\D/g, "").includes(digits)
            : client.nickname.toLowerCase().includes(normalized));
        if (active) {
          setClientCandidate(found[0]);
        }
      } catch {
        if (active) {
          setClientCandidate(undefined);
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientField, clientList, clientQuery]);

  const submit = async () => {
    if (!workstationId) {
      setError("Выберите игровое место");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (
      !Number.isFinite(start.getTime()) ||
      !Number.isFinite(end.getTime()) ||
      end <= start ||
      !Number.isInteger(durationMinutes) ||
      durationMinutes < 60 ||
      durationMinutes % 60 !== 0
    ) {
      setError("Проверьте период бронирования");
      return;
    }
    if (!api) {
      onCreated();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        workstation_ids: [workstationId],
        client_id: clientId ?? null,
        guest_id: null,
        guest_name: clientId ? null : "Гость",
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        notes: null,
        tariff_id: null,
      };
      const availability = await api.checkReservationAvailability(payload);
      if (!availability.available) {
        setError(
          availability.reason === "workstation_disabled"
            ? "Игровое место отключено"
            : "Игровое место уже занято в выбранный период",
        );
        return;
      }
      await api.createReservation(payload, generateUUID());
      onCreated();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось создать бронь",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Новая бронь"
        subtitle="Игровое место и время"
        onClose={onClose}
      />
      <div className="booking-form flex flex-col gap-3">
        <label>
          Игровое место
          <select
            className="select select-sm"
            aria-label="Игровое место"
            value={workstationId}
            onChange={(event) => setWorkstationId(event.target.value)}
          >
            {pcs.map((pc) => (
              <option value={pc.id} key={pc.id}>
                {pc.name} · {pc.group}
              </option>
            ))}
          </select>
        </label>
        <label>
          Начало
          <DateTimePicker
            value={startAt}
            onChange={setStartAt}
            mode="datetime"
            label="Начало брони"
            minuteStep={30}
          />
        </label>
        <div className="rounded-xl border border-primary/15! bg-base-200/55! p-3">
          <div className="flex items-center justify-between gap-3"><span className="text-sm">Длительность</span><strong className="text-sm">До {new Date(endAt).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</strong></div>
          <div className="mt-2 flex flex-wrap items-center gap-2" aria-label="Быстрый выбор длительности">{[60, 120, 180, 300].map((minutes) => <button type="button" key={minutes} className={`badge h-7 cursor-pointer border-primary/30! px-3 ${durationMinutes === minutes ? "badge-primary" : "badge-outline"}`} aria-pressed={durationMinutes === minutes} onClick={() => setDurationMinutes(minutes)}>{minutes / 60} {minutes === 60 ? "час" : "часа"}</button>)}<label className="input input-xs ml-auto flex w-24 items-center gap-1"><input className="w-full" aria-label="Другая длительность в часах" type="number" min="1" step="1" value={durationMinutes / 60} onChange={(event) => setDurationMinutes(Number(event.target.value) * 60)} /><span className="text-base-content/60!">ч</span></label></div>
        </div>
        <label>
          Клиент{" "}
          <span className="field-hint text-xs text-base-content/60!">
            необязательно
          </span>
          <div className="input input-sm flex items-center gap-2"><Search size={16} className="shrink-0 text-base-content/60!" /><input className="min-w-0 grow bg-transparent outline-none" aria-label="Клиент" value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClientId(undefined); }} placeholder="Введите 3 буквы или 4 цифры" /></div>
        </label>
        {clientCandidate && !clientId && (
          <button
            className="client-result btn btn-ghost flex w-full items-center justify-start gap-3 rounded-lg border border-primary/20! bg-base-200/55! p-3"
            onClick={() => {
              setClientId(clientCandidate.id);
              setClientQuery(clientCandidate.nickname);
              setClientCandidate(undefined);
            }}
          >
            <div className="client-avatar grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary! text-sm font-bold text-primary-content!">
              {clientCandidate.nickname.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <strong>{clientCandidate.nickname}</strong>
              <span>{formatRussianPhone(clientCandidate.phone)}</span>
            </div>
            <ChevronRight size={16} />
          </button>
        )}
        <div className="guest-mode-card rounded-xl border border-primary/20! bg-base-200/55! p-4">
          <UserX size={16} className="guest-mode-icon mb-2 text-primary!" />
          <div className="text-sm">
            <strong>{clientId ? "Бронь на клиента" : "Гостевая бронь"}</strong>
          </div>
          <div className="text-xs text-base-content/60!">
            <span>
              {clientId
                ? "Ник клиента будет показан в расписании"
                : "Если клиент не выбран, участник будет указан как «Гость»"}
            </span>
          </div>
        </div>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-block wide w-full bg-primary! text-primary-content!"
          disabled={submitting || !pcs.length}
          onClick={() => void submit()}
        >
          {submitting ? "Создаём..." : "Создать бронь"}
        </button>
        <button
          className="secondary-button btn btn-outline btn-block wide w-full"
          onClick={onClose}
        >
          Отмена
        </button>
      </div>
    </div>
  );
}

export function BookingEditPanel({
  reservation,
  clients,
  onClose,
  onSaved,
  pcs,
  api,
}: {
  reservation: Reservation;
  clients: Client[];
  onClose: () => void;
  onSaved: () => void;
  pcs: Workstation[];
  api?: GameClubApi;
}) {
  const [workstationId, setWorkstationId] = useState(
    reservation.workstation_ids[0] ?? "",
  );
  const [startAt, setStartAt] = useState(
    localDateTimeValue(new Date(reservation.start_at)),
  );
  const [endAt, setEndAt] = useState(
    localDateTimeValue(new Date(reservation.end_at)),
  );
  const [notes, setNotes] = useState(reservation.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const canEdit = reservation.status === "confirmed";
  const clientName = reservation.client_id
    ? (clients.find((client) => client.id === reservation.client_id)
        ?.nickname ?? "Клиент")
    : "Гость";

  const submit = async () => {
    if (!canEdit) {
      setError("Изменять можно только подтверждённую бронь");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (
      !workstationId ||
      !Number.isFinite(start.getTime()) ||
      !Number.isFinite(end.getTime()) ||
      end <= start
    ) {
      setError("Проверьте место и период бронирования");
      return;
    }
    if (!api) {
      onSaved();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.updateReservation(reservation.id, {
        workstation_ids:
          workstationId === reservation.workstation_ids[0]
            ? reservation.workstation_ids
            : [workstationId],
        client_id: reservation.client_id,
        guest_id: reservation.guest_id,
        guest_name: reservation.client_id ? null : "Гость",
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        notes: notes.trim() || null,
        tariff_id: reservation.tariff_id,
      });
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось изменить бронь",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Бронь"
        subtitle="Подробности и изменение"
        onClose={onClose}
      />
      <div className="booking-form flex flex-col gap-3">
        <div className="detail-row flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
          <span>Статус</span>
          <strong>
            {reservation.status === "confirmed"
              ? "Подтверждена"
              : reservation.status}
          </strong>
        </div>
        <label>
          Игровое место
          <select
            className="select select-sm"
            aria-label="Игровое место брони"
            value={workstationId}
            onChange={(event) => setWorkstationId(event.target.value)}
            disabled={!canEdit}
          >
            {pcs.map((pc) => (
              <option value={pc.id} key={pc.id}>
                {pc.name} · {pc.group}
              </option>
            ))}
          </select>
        </label>
        <label>
          Начало
          <DateTimePicker
            value={startAt}
            onChange={setStartAt}
            mode="datetime"
            label="Начало изменяемой брони"
            disabled={!canEdit}
          />
        </label>
        <label>
          Окончание
          <DateTimePicker
            value={endAt}
            onChange={setEndAt}
            mode="datetime"
            label="Окончание изменяемой брони"
            disabled={!canEdit}
          />
        </label>
        <div className="detail-row flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
          <span>Участник</span>
          <strong>{clientName}</strong>
        </div>
        <label>
          Комментарий
          <textarea
            className="textarea textarea-sm"
            aria-label="Комментарий к брони"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            disabled={!canEdit}
            rows={3}
          />
        </label>
        {!canEdit && (
          <div className="search-hint rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm text-base-content/60!">
            Для этой брони доступны только просмотр и действия в расписании.
          </div>
        )}
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        {canEdit && (
          <button
            className="primary-button btn btn-primary btn-block wide w-full bg-primary! text-primary-content!"
            disabled={submitting}
            onClick={() => void submit()}
          >
            {submitting ? "Сохраняем..." : "Сохранить изменения"}
          </button>
        )}
        <button
          className="secondary-button btn btn-outline btn-block wide w-full"
          onClick={onClose}
        >
          Закрыть
        </button>
      </div>
    </div>
  );
}
