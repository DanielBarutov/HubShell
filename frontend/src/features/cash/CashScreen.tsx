import { useEffect, useState } from "react";
import { Banknote, Plus, Settings, X } from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type { BackendCashMovement, BackendCashShift, BackendCashShiftSchedule } from "../../api";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { cashMoney, cashIdempotencyKey } from "../../shared/formatters";
import { cashDirectionLabels } from "../../shared/constants";

export function CashScheduleEditor({ api, schedule, onSaved, onCancel }: { api: GameClubApi; schedule?: BackendCashShiftSchedule; onSaved: (schedule: BackendCashShiftSchedule) => void; onCancel?: () => void }) {
  const [registerId, setRegisterId] = useState(schedule?.register_id ?? "front-desk");
  const [timezone, setTimezone] = useState(schedule?.timezone ?? "Europe/Moscow");
  const [autoOpen, setAutoOpen] = useState(schedule?.auto_open ?? false);
  const [autoOpenAt, setAutoOpenAt] = useState(schedule?.auto_open_at?.slice(0, 5) ?? "10:00");
  const [autoClose, setAutoClose] = useState(schedule?.auto_close ?? false);
  const [autoCloseAt, setAutoCloseAt] = useState(schedule?.auto_close_at?.slice(0, 5) ?? "23:59");
  const [openingBalance, setOpeningBalance] = useState(((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRegisterId(schedule?.register_id ?? "front-desk");
    setTimezone(schedule?.timezone ?? "Europe/Moscow");
    setAutoOpen(schedule?.auto_open ?? false);
    setAutoOpenAt(schedule?.auto_open_at?.slice(0, 5) ?? "10:00");
    setAutoClose(schedule?.auto_close ?? false);
    setAutoCloseAt(schedule?.auto_close_at?.slice(0, 5) ?? "23:59");
    setOpeningBalance(((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2));
  }, [schedule]);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const opening = Number(openingBalance);
    if (!registerId.trim() || !timezone.trim() || !Number.isFinite(opening) || opening < 0 || (autoOpen && !autoOpenAt) || (autoClose && !autoCloseAt)) {
      setError("Заполните register, часовой пояс и время включённых правил");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveCashShiftSchedule(registerId.trim(), {
        timezone: timezone.trim(),
        auto_open: autoOpen,
        auto_open_at: autoOpen ? autoOpenAt : null,
        auto_close: autoClose,
        auto_close_at: autoClose ? autoCloseAt : null,
        opening_balance_cents: Math.round(opening * 100),
      });
      onSaved(saved);
      onCancel?.();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить расписание");
    } finally {
      setSaving(false);
    }
  };

  return <form className="schedule-editor" onSubmit={(event) => void save(event)}><div className="schedule-editor-head"><div><strong>{schedule ? `Register · ${schedule.register_id}` : "Новая касса"}</strong><span>{schedule ? "Расписание можно изменить в любое время" : "Автоматические правила применятся после сохранения"}</span></div>{onCancel && <button type="button" className="icon-button" aria-label="Отменить добавление кассы" onClick={onCancel}><X size={16} /></button>}</div><div className="schedule-fields"><label>Register<input value={registerId} onChange={(event) => setRegisterId(event.target.value)} disabled={Boolean(schedule)} /></label><label>Часовой пояс<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Europe/Moscow" /></label><label>Остаток при автооткрытии, ₽<input type="number" min="0" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /></label></div><div className="schedule-rules"><label className="schedule-toggle"><input type="checkbox" checked={autoOpen} onChange={(event) => setAutoOpen(event.target.checked)} /><span><strong>Автооткрытие</strong><small>Открыть смену в начале рабочего дня</small></span><DateTimePicker value={autoOpenAt} onChange={setAutoOpenAt} mode="time" label="Время автооткрытия" disabled={!autoOpen} className="schedule-time-picker" /></label><label className="schedule-toggle"><input type="checkbox" checked={autoClose} onChange={(event) => setAutoClose(event.target.checked)} /><span><strong>Автозакрытие</strong><small>Закрыть смену в конце рабочего дня</small></span><DateTimePicker value={autoCloseAt} onChange={setAutoCloseAt} mode="time" label="Время автозакрытия" disabled={!autoClose} className="schedule-time-picker" /></label></div>{error && <div className="form-error" role="alert">{error}</div>}<div className="schedule-editor-actions"><button className="primary-button" disabled={saving}>{saving ? "Сохраняем..." : "Сохранить расписание"}</button>{onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Отмена</button>}</div></form>;
}

export function CashView({
  api,
  shifts,
  onOpenShift,
  onRecordMovement,
  onCloseShift,
}: {
  api?: GameClubApi;
  shifts: BackendCashShift[];
  onOpenShift?: () => void;
  onRecordMovement?: (shift: BackendCashShift) => void;
  onCloseShift?: (shift: BackendCashShift) => void;
}) {
  const [movements, setMovements] = useState<BackendCashMovement[]>([]);
  const [schedules, setSchedules] = useState<BackendCashShiftSchedule[]>([]);
  const [addingSchedule, setAddingSchedule] = useState(false);
  const [movementError, setMovementError] = useState<string | null>(null);
  const openShift = shifts.find((shift) => shift.status === "open");

  useEffect(() => {
    if (!api) {
      setSchedules([]);
      return undefined;
    }
    let active = true;
    void api.listCashShiftSchedules().then((items) => {
      if (active) setSchedules(items);
    }).catch(() => {
      if (active) setSchedules([]);
    });
    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => {
    if (!api || !openShift) {
      setMovements([]);
      return undefined;
    }
    let active = true;
    void api.listCashMovements(openShift.id).then((items) => {
      if (active) {
        setMovements(items);
        setMovementError(null);
      }
    }).catch((error) => {
      if (active) {
        setMovementError(error instanceof ApiError ? error.message : "Не удалось загрузить движения");
      }
    });
    return () => {
      active = false;
    };
  }, [api, openShift?.id, shifts]);

  if (!api) {
    return <><div className="page-heading"><div><p className="eyebrow">Финансы · Демонстрация</p><h1>Касса</h1><p className="subheading">Открытие смены, наличные движения и закрытие дня.</p></div></div><div className="white-card product-list-card"><div className="timeline-empty">Подключите live-режим, чтобы управлять кассовой сменой через backend.</div></div></>;
  }

  return <><div className="page-heading"><div><p className="eyebrow">Финансы · Сегодня</p><h1>Касса</h1><p className="subheading">Наличный ledger отделён от клиентских депозитов и session charge.</p></div><button className="primary-button" disabled={Boolean(openShift)} onClick={onOpenShift}><Plus size={17} /> Открыть смену</button></div>{openShift ? <div className="white-card product-list-card"><div className="card-heading"><div><h3>Смена · {openShift.register_id}</h3><p>Открыта {new Date(openShift.opened_at).toLocaleString("ru-RU")} · {openShift.opened_by}</p></div><span className="active-chip">Открыта</span></div><div className="cash-summary-grid"><div><span>В начале</span><strong>{cashMoney(openShift.opening_balance_cents)}</strong></div><div><span>Ожидается</span><strong>{cashMoney(openShift.expected_close_cents)}</strong></div><div><span>Разница</span><strong>—</strong></div></div><div className="panel-actions"><button className="secondary-button" onClick={() => onRecordMovement?.(openShift)}><Plus size={15} /> Движение</button><button className="primary-button" onClick={() => onCloseShift?.(openShift)}>Закрыть смену</button></div><div className="operation-section"><div className="operation-heading"><h3>Последние движения</h3><span>{movements.length}</span></div>{movementError && <div className="form-error" role="alert">{movementError}</div>}{!movementError && !movements.length && <div className="timeline-empty">Движений пока нет</div>}{movements.map((movement) => <div className="operation-row" key={movement.id}><div className={`operation-icon ${movement.direction === "cash_out" ? "expense" : "income"}`}><Banknote size={14} /></div><div><strong>{cashDirectionLabels[movement.direction]}</strong><span>{movement.reason} · {new Date(movement.created_at).toLocaleString("ru-RU")}</span></div><b className={movement.direction === "cash_out" || movement.amount_cents < 0 ? "expense-text" : "income-text"}>{movement.direction === "cash_out" ? "-" : movement.amount_cents > 0 ? "+" : ""}{cashMoney(Math.abs(movement.amount_cents))}</b></div>)}</div></div> : <div className="white-card product-list-card"><div className="timeline-empty"><Banknote size={20} /><strong>Открытой смены нет</strong><span>Откройте смену перед приёмом наличных.</span></div></div>}<div className="white-card product-list-card schedule-card"><div className="card-heading"><div><h3>Автоматизация смен</h3><p>Ручное открытие и закрытие остаются доступными всегда.</p></div><button className="secondary-button" onClick={() => setAddingSchedule(true)} disabled={addingSchedule}><Plus size={15} /> Добавить кассу</button></div><div className="schedule-note"><Settings size={15} /><span>Автозакрытие использует ожидаемый остаток из ledger. Фактический пересчёт наличных оператор подтверждает вручную.</span></div>{schedules.map((schedule) => <CashScheduleEditor key={schedule.register_id} api={api} schedule={schedule} onSaved={(saved) => setSchedules((items) => items.map((item) => item.register_id === saved.register_id ? saved : item))} />)}{addingSchedule && <CashScheduleEditor api={api} onSaved={(saved) => { setSchedules((items) => [...items, saved]); setAddingSchedule(false); }} onCancel={() => setAddingSchedule(false)} />}{!schedules.length && !addingSchedule && <div className="timeline-empty">Авторасписаний пока нет. Ручное управление сменой уже доступно выше.</div>}</div><div className="white-card product-list-card"><div className="card-heading"><div><h3>История смен</h3><p>Закрытые смены доступны только для чтения.</p></div></div>{shifts.filter((shift) => shift.status === "closed").map((shift) => <div className="settings-row" key={shift.id}><div><strong>{shift.register_id}</strong><span>{new Date(shift.opened_at).toLocaleDateString("ru-RU")} · закрыта {shift.closed_at ? new Date(shift.closed_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "—"}</span></div><b>{shift.difference_cents === null ? "—" : `${shift.difference_cents >= 0 ? "+" : ""}${cashMoney(shift.difference_cents)}`}</b><span className="active-chip">Закрыта</span></div>)}{!shifts.some((shift) => shift.status === "closed") && <div className="timeline-empty">Закрытых смен пока нет</div>}</div></>;
}

export function CashOpenPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
  const [registerId, setRegisterId] = useState("front-desk");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(openingBalance);
    if (!registerId.trim() || !Number.isFinite(rubles) || rubles < 0) {
      setError("Укажите register и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.openCashShift(
        { register_id: registerId.trim(), opening_balance_cents: Math.round(rubles * 100) },
        cashIdempotencyKey("cash-open"),
      );
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось открыть смену");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Открыть смену" subtitle="Касса · новый рабочий день" onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Register<input value={registerId} onChange={(event) => setRegisterId(event.target.value)} autoFocus /></label><label>Остаток на начало, ₽<input type="number" min="0" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Открываем..." : "Открыть смену"}</button><p className="subheading">Для одного register одновременно допускается только одна открытая смена.</p></form></div>;
}

export function CashMovementPanel({ api, shift, onClose, onSaved }: { api: GameClubApi; shift: BackendCashShift; onClose: () => void; onSaved: () => void }) {
  const [direction, setDirection] = useState<BackendCashMovement["direction"]>("cash_in");
  const [amount, setAmount] = useState("0");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operationKey] = useState(() => cashIdempotencyKey("cash-movement"));

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(amount);
    if (!Number.isFinite(rubles) || (direction !== "correction" && rubles <= 0) || (direction === "correction" && rubles === 0) || !reason.trim()) {
      setError("Укажите сумму и причину движения");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { direction, amount_cents: Math.round(rubles * 100), reason: reason.trim() };
      const approval = direction === "correction"
        ? await api.createCashApproval(
            shift.id,
            { kind: "correction", target_key: operationKey, reason: `Одобрение: ${reason.trim()}` },
            `approval-${operationKey}`,
          )
        : undefined;
      await api.recordCashMovement(shift.id, { ...payload, approval_id: approval?.id }, operationKey);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось записать движение");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Движение наличных" subtitle={`Смена · ${shift.register_id}`} onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Тип<select value={direction} onChange={(event) => setDirection(event.target.value as BackendCashMovement["direction"])}><option value="cash_in">Приход</option><option value="cash_out">Расход</option><option value="correction">Корректировка</option></select></label>{direction === "correction" && <p className="subheading">Для корректировки автоматически запрашивается отдельное supervisor approval и сохраняется audit.</p>}<label>Сумма, ₽<input type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} /></label><label>Причина<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Приём наличных" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Записать движение"}</button></form></div>;
}

export function CashClosePanel({ api, shift, onClose, onSaved }: { api: GameClubApi; shift: BackendCashShift; onClose: () => void; onSaved: () => void }) {
  const [actualBalance, setActualBalance] = useState((shift.expected_close_cents / 100).toFixed(2));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operationKey] = useState(() => cashIdempotencyKey("cash-close"));

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(actualBalance);
    if (!Number.isFinite(rubles) || rubles < 0) {
      setError("Укажите корректный фактический остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const actualCloseCents = Math.round(rubles * 100);
      const approval = actualCloseCents !== shift.expected_close_cents
        ? await api.createCashApproval(
            shift.id,
            { kind: "close_difference", target_key: operationKey, reason: "Supervisor verified the final count" },
            `approval-${operationKey}`,
          )
        : undefined;
      await api.closeCashShift(shift.id, actualCloseCents, operationKey, approval?.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось закрыть смену");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Закрыть смену" subtitle={`Смена · ${shift.register_id}`} onClose={onClose} /><form className="booking-form" onSubmit={submit}><div className="detail-row"><span>Ожидаемый остаток</span><strong>{cashMoney(shift.expected_close_cents)}</strong></div><label>Фактический остаток, ₽<input type="number" min="0" step="0.01" value={actualBalance} onChange={(event) => setActualBalance(event.target.value)} autoFocus /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Закрываем..." : "Закрыть смену"}</button><p className="subheading">После закрытия смена становится неизменяемой; расхождение сохраняется в ledger.</p></form></div>;
}
