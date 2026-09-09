import { useEffect, useMemo, useState } from "react";
import { ChevronRight, UserX } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { Reservation } from "../../api";
import { toUiClient } from "../../adapters";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { formatRussianPhone, getSearchField, localDateTimeValue } from "../../shared/formatters";
import { PanelHeader } from "../../shared/components/PanelHeader";
import type { Client, Workstation } from "../../types";

export function BookingPanel({
  initialWorkstationId,
  onClose,
  onCreated,
  pcs,
  api,
}: {
  initialWorkstationId?: string;
  onClose: () => void;
  onCreated: () => void;
  pcs: Workstation[];
  api?: GameClubApi;
}) {
  const now = useMemo(() => new Date(Date.now() + 30 * 60 * 1000), []);
  const [workstationId, setWorkstationId] = useState(initialWorkstationId ?? pcs[0]?.id ?? "");
  const [startAt, setStartAt] = useState(localDateTimeValue(now));
  const [endAt, setEndAt] = useState(localDateTimeValue(new Date(now.getTime() + 60 * 60 * 1000)));
  const [clientQuery, setClientQuery] = useState("");
  const [clientId, setClientId] = useState<string | undefined>();
  const [clientCandidate, setClientCandidate] = useState<Client | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const clientField = getSearchField(clientQuery);

  useEffect(() => {
    if (!workstationId && pcs[0]) {
      setWorkstationId(pcs[0].id);
    }
  }, [pcs, workstationId]);

  useEffect(() => {
    if (!api || !clientField) {
      setClientCandidate(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(clientQuery, clientField);
        if (active) {
          setClientCandidate(found[0] ? toUiClient(found[0]) : undefined);
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
  }, [api, clientField, clientQuery]);

  const submit = async () => {
    if (!workstationId) {
      setError("Выберите игровое место");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
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
      await api.createReservation(payload, crypto.randomUUID());
      onCreated();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать бронь");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Новая бронь" subtitle="Игровое место и время" onClose={onClose} /><div className="booking-form"><label>Игровое место<select aria-label="Игровое место" value={workstationId} onChange={(event) => setWorkstationId(event.target.value)}>{pcs.map((pc) => <option value={pc.id} key={pc.id}>{pc.name} · {pc.group}</option>)}</select></label><label>Начало<DateTimePicker value={startAt} onChange={setStartAt} mode="datetime" label="Начало брони" /></label><label>Окончание<DateTimePicker value={endAt} onChange={setEndAt} mode="datetime" label="Окончание брони" /></label><label>Клиент <span className="field-hint">необязательно</span><input aria-label="Клиент" value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClientId(undefined); }} placeholder="Ник или телефон" /></label>{clientCandidate && !clientId && <button className="client-result" onClick={() => { setClientId(clientCandidate.id); setClientQuery(clientCandidate.nickname); }}><div className="client-avatar">{clientCandidate.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{clientCandidate.nickname}</strong><span>{formatRussianPhone(clientCandidate.phone)}</span></div><ChevronRight size={16} /></button>}<div className="guest-mode-card"><div className="guest-mode-icon"><UserX size={16} /></div><div><strong>{clientId ? "Бронь на клиента" : "Гостевая бронь"}</strong><span>{clientId ? "Ник клиента будет показан в расписании" : "Если клиент не выбран, участник будет указан как «Гость»"}</span></div></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !pcs.length} onClick={() => void submit()}>{submitting ? "Создаём..." : "Создать бронь"}</button><button className="secondary-button wide" onClick={onClose}>Отмена</button></div></div>;
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
  const [workstationId, setWorkstationId] = useState(reservation.workstation_ids[0] ?? "");
  const [startAt, setStartAt] = useState(localDateTimeValue(new Date(reservation.start_at)));
  const [endAt, setEndAt] = useState(localDateTimeValue(new Date(reservation.end_at)));
  const [notes, setNotes] = useState(reservation.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const canEdit = reservation.status === "confirmed";
  const clientName = reservation.client_id
    ? clients.find((client) => client.id === reservation.client_id)?.nickname ?? "Клиент"
    : "Гость";

  const submit = async () => {
    if (!canEdit) {
      setError("Изменять можно только подтверждённую бронь");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (!workstationId || !Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
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
        workstation_ids: workstationId === reservation.workstation_ids[0] ? reservation.workstation_ids : [workstationId],
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
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить бронь");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Бронь" subtitle="Подробности и изменение" onClose={onClose} /><div className="booking-form"><div className="detail-row"><span>Статус</span><strong>{reservation.status === "confirmed" ? "Подтверждена" : reservation.status}</strong></div><label>Игровое место<select aria-label="Игровое место брони" value={workstationId} onChange={(event) => setWorkstationId(event.target.value)} disabled={!canEdit}>{pcs.map((pc) => <option value={pc.id} key={pc.id}>{pc.name} · {pc.group}</option>)}</select></label><label>Начало<DateTimePicker value={startAt} onChange={setStartAt} mode="datetime" label="Начало изменяемой брони" disabled={!canEdit} /></label><label>Окончание<DateTimePicker value={endAt} onChange={setEndAt} mode="datetime" label="Окончание изменяемой брони" disabled={!canEdit} /></label><div className="detail-row"><span>Участник</span><strong>{clientName}</strong></div><label>Комментарий<textarea aria-label="Комментарий к брони" value={notes} onChange={(event) => setNotes(event.target.value)} disabled={!canEdit} rows={3} /></label>{!canEdit && <div className="search-hint">Для этой брони доступны только просмотр и действия в расписании.</div>}{error && <div className="form-error" role="alert">{error}</div>}{canEdit && <button className="primary-button wide" disabled={submitting} onClick={() => void submit()}>{submitting ? "Сохраняем..." : "Сохранить изменения"}</button>}<button className="secondary-button wide" onClick={onClose}>Закрыть</button></div></div>;
}
