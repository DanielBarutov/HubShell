import { useEffect, useState } from "react";
import {
  ArrowLeftRight,
  Banknote,
  Clock3,
  MoreHorizontal,
  Plus,
  ReceiptText,
  Settings,
  X,
} from "lucide-react";
import { ApiError, GameClubApi } from "../../api";
import type {
  BackendCashMovement,
  BackendCashShift,
  BackendCashShiftSchedule,
} from "../../api";
import { PanelHeader } from "../../shared/components/PanelHeader";
import { DateTimePicker } from "../../shared/components/DateTimePicker";
import { cashMoney, cashIdempotencyKey } from "../../shared/formatters";
import { cashDirectionLabels } from "../../shared/constants";

function CashRegisterIllustration() {
  return (
    <img
      src="/cash-register.png"
      alt=""
      className="h-24 w-32 object-contain mix-blend-screen"
      aria-hidden="true"
    />
  );
}

export function CashScheduleEditor({
  api,
  schedule,
  onSaved,
  onCancel,
}: {
  api: GameClubApi;
  schedule?: BackendCashShiftSchedule;
  onSaved: (schedule: BackendCashShiftSchedule) => void;
  onCancel?: () => void;
}) {
  const [registerId, setRegisterId] = useState(
    schedule?.register_id ?? "front-desk",
  );
  const [timezone, setTimezone] = useState(
    schedule?.timezone ?? "Europe/Moscow",
  );
  const [autoOpen, setAutoOpen] = useState(schedule?.auto_open ?? false);
  const [autoOpenAt, setAutoOpenAt] = useState(
    schedule?.auto_open_at?.slice(0, 5) ?? "10:00",
  );
  const [autoClose, setAutoClose] = useState(schedule?.auto_close ?? false);
  const [autoCloseAt, setAutoCloseAt] = useState(
    schedule?.auto_close_at?.slice(0, 5) ?? "23:59",
  );
  const [openingBalance, setOpeningBalance] = useState(
    ((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2),
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRegisterId(schedule?.register_id ?? "front-desk");
    setTimezone(schedule?.timezone ?? "Europe/Moscow");
    setAutoOpen(schedule?.auto_open ?? false);
    setAutoOpenAt(schedule?.auto_open_at?.slice(0, 5) ?? "10:00");
    setAutoClose(schedule?.auto_close ?? false);
    setAutoCloseAt(schedule?.auto_close_at?.slice(0, 5) ?? "23:59");
    setOpeningBalance(
      ((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2),
    );
  }, [schedule]);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const opening = Number(openingBalance);
    if (
      !registerId.trim() ||
      !timezone.trim() ||
      !Number.isFinite(opening) ||
      opening < 0 ||
      (autoOpen && !autoOpenAt) ||
      (autoClose && !autoCloseAt)
    ) {
      setError(
        "Заполните название кассы, часовой пояс и время включённых правил",
      );
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
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось сохранить расписание",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="schedule-editor flex flex-col gap-3"
      onSubmit={(event) => void save(event)}
    >
      <div className="schedule-editor-head flex items-start justify-between gap-3 border-b border-primary/15! pb-3">
        <div>
          <strong>
            {schedule ? `Касса · ${schedule.register_id}` : "Новая касса"}
          </strong>
          <span className="text-sm text-base-content/50 ml-10">
            {schedule
              ? "Расписание можно изменить в любое время"
              : "Автоматические правила применятся после сохранения"}
          </span>
        </div>
        {onCancel && (
          <button
            type="button"
            className="icon-button btn btn-ghost btn-circle btn-sm"
            aria-label="Отменить добавление кассы"
            onClick={onCancel}
          >
            <X size={16} />
          </button>
        )}
      </div>
      <div className="schedule-fields grid grid-cols-1 gap-1 md:grid-cols-3">
        <label className="text-sm">
          Название кассы
          <input
            className="input input-xs ml-2"
            value={registerId}
            onChange={(event) => setRegisterId(event.target.value)}
            disabled={Boolean(schedule)}
          />
        </label>
        <label className="text-sm">
          Часовой пояс
          <input
            className="input input-xs ml-2"
            value={timezone}
            onChange={(event) => setTimezone(event.target.value)}
            placeholder="Europe/Moscow"
          />
        </label>
        <label className="text-sm">
          Остаток при автооткрытии, ₽
          <input
            className="input input-xs ml-2"
            type="number"
            min="0"
            step="0.01"
            value={openingBalance}
            onChange={(event) => setOpeningBalance(event.target.value)}
          />
        </label>
      </div>
      <div className="schedule-rules flex flex-col gap-3">
        <div className="schedule-toggle flex items-center gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <input
            className="toggle toggle-primary toggle-sm"
            id="cash-auto-open"
            type="checkbox"
            checked={autoOpen}
            onChange={(event) => setAutoOpen(event.target.checked)}
          />
          <label htmlFor="cash-auto-open">
            <strong>Автооткрытие</strong>
            <small>Открыть смену в начале рабочего дня</small>
          </label>
          <DateTimePicker
            value={autoOpenAt}
            onChange={setAutoOpenAt}
            mode="time"
            label="Время автооткрытия"
            disabled={!autoOpen}
            className="schedule-time-picker ml-auto"
          />
        </div>
        <div className="schedule-toggle flex items-center gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
          <input
            className="toggle toggle-primary toggle-sm"
            id="cash-auto-close"
            type="checkbox"
            checked={autoClose}
            onChange={(event) => setAutoClose(event.target.checked)}
          />
          <label htmlFor="cash-auto-close">
            <strong>Автозакрытие</strong>
            <small>Закрыть смену в конце рабочего дня</small>
          </label>
          <DateTimePicker
            value={autoCloseAt}
            onChange={setAutoCloseAt}
            mode="time"
            label="Время автозакрытия"
            disabled={!autoClose}
            className="schedule-time-picker ml-auto"
            popoverPlacement="top"
          />
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
      <div className="schedule-editor-actions flex flex-wrap items-center gap-2">
        <button
          className="primary-button btn btn-primary btn-sm"
          disabled={saving}
        >
          {saving ? "Сохраняем..." : "Сохранить расписание"}
        </button>
        {onCancel && (
          <button
            type="button"
            className="secondary-button btn btn-outline btn-sm"
            onClick={onCancel}
          >
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}

export function CashView({
  api,
  shifts,
  cashShiftSchedules,
  cashMovements,
  onRefresh,
  onOpenShift,
  onRecordMovement,
  onCloseShift,
}: {
  api?: GameClubApi;
  shifts: BackendCashShift[];
  cashShiftSchedules: BackendCashShiftSchedule[];
  cashMovements: BackendCashMovement[];
  onRefresh: () => void;
  onOpenShift?: () => void;
  onRecordMovement?: (shift: BackendCashShift) => void;
  onCloseShift?: (shift: BackendCashShift) => void;
}) {
  const [addingSchedule, setAddingSchedule] = useState(false);
  const openShift = shifts.find((shift) => shift.status === "open");

  if (!api) {
    const movementRows = [
      ["03.10.2026, 19:31:56", "Оплата гостевого тарифа", "+50,00 ₽"],
      ["03.10.2026, 19:31:47", "Оплата гостевого тарифа", "+50,00 ₽"],
      ["03.10.2026, 19:31:33", "Оплата гостевого тарифа", "+100,00 ₽"],
      ["03.10.2026, 10:38:31", "Пополнение баланса клиента V2", "+1 000,00 ₽"],
      ["03.10.2026, 10:36:25", "Оплата гостевого тарифа", "+50,00 ₽"],
      ["03.10.2026, 10:35:30", "Оплата гостевого тарифа", "+280,00 ₽"],
      ["03.10.2026, 10:23:15", "Оплата гостевого тарифа", "+280,00 ₽"],
      ["03.10.2026, 10:21:03", "Оплата гостевого тарифа", "+280,00 ₽"],
    ];
    return (
      <>
        <div
          className="relative mb-3 flex flex-wrap items-end justify-between gap-3 overflow-hidden border-b border-primary/15! bg-base-100/25! p-3"
          style={{
            backgroundImage:
              "linear-gradient(90deg, rgba(7,24,27,.44), rgba(7,24,27,.06)), url(/neon-club-room.png)",
            backgroundPosition: "center 46%",
            backgroundSize: "cover",
            backgroundRepeat: "no-repeat",
          }}
        >
          <div className="relative z-10 flex items-start gap-3">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border border-primary/40! bg-primary/10! text-primary!">
              <Banknote size={24} />
            </div>
            <div>
              <p className="mb-1 text-sm text-base-content/65!">
                Финансы · Сегодня
              </p>
              <h1 className="text-3xl font-bold tracking-tight">Касса</h1>
              <p className="mt-1 max-w-3xl text-xs text-base-content/65!">
                Наличные операции хранятся отдельно от депозитов клиентов и
                оплаты игрового времени.
              </p>
            </div>
          </div>
          <button className="relative z-10 btn btn-primary btn-sm" disabled>
            <Plus size={17} /> Открыть смену
          </button>
        </div>
        <section
          className="card relative mb-3 gap-2 overflow-hidden border-primary/45! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md"
          style={{
            backgroundImage:
              "linear-gradient(90deg, rgba(3,25,27,.96) 0%, rgba(3,25,27,.88) 48%, rgba(3,25,27,.58)), url(/neon-club-room.png)",
            backgroundPosition: "center",
            backgroundSize: "cover",
            backgroundRepeat: "no-repeat",
          }}
        >
          <div className="relative z-10 flex flex-wrap items-start justify-between gap-2">
            <div className="flex items-center gap-3">
              <div className="grid h-24 w-32 shrink-0 place-items-center rounded-2xl border border-primary/30 bg-primary/10">
                <CashRegisterIllustration />
              </div>
              <div>
                <h2 className="text-lg font-bold">Смена · front-desk</h2>
                <p className="text-xs text-base-content/65!">
                  Открыта 01.10.2026, 18:04:30 · dev-operator
                </p>
              </div>
            </div>
            <span className="badge badge-success badge-soft gap-2 px-3 py-2">
              <i className="size-2 rounded-full bg-success" /> Открыта
            </span>
          </div>
          <div className="relative z-10 grid grid-cols-1 gap-2 md:grid-cols-3">
            {[
              ["В начале", "0,00 ₽", "Banknote"],
              ["Ожидается", "2 942,00 ₽", "Clock"],
              ["Разница", "—", "Arrow"],
            ].map(([label, value, icon]) => (
              <div
                className="flex items-center justify-between rounded-xl border border-primary/15! bg-base-200/55! p-2"
                key={label}
              >
                <div className="flex items-center gap-3">
                  <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
                    {icon === "Clock" ? (
                      <Clock3 size={18} />
                    ) : icon === "Arrow" ? (
                      <ArrowLeftRight size={18} />
                    ) : (
                      <Banknote size={18} />
                    )}
                  </span>
                  <span className="text-xs text-base-content/60!">{label}</span>
                </div>
                <strong className="text-lg">{value}</strong>
              </div>
            ))}
          </div>
          <div className="relative z-10 flex gap-2">
            <button className="btn btn-outline btn-sm">
              <Plus size={15} /> Движение
            </button>
            <button className="btn btn-primary btn-sm">Закрыть смену</button>
          </div>
        </section>
        <section className="card mb-3 gap-3 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
                <ReceiptText size={17} />
              </span>
              <div>
                <h2 className="font-semibold">Последние движения</h2>
                <p className="text-xs text-base-content/60!">
                  Сегодня · подтверждённые операции
                </p>
              </div>
            </div>
            <span className="badge badge-neutral badge-sm">16</span>
          </div>
          <div className="overflow-x-auto">
            <div className="grid min-w-[760px] grid-cols-[24px_180px_1fr_140px_100px_24px] gap-3 border-b border-primary/15! px-2 py-1 text-xs text-base-content/55!">
              <span />
              <span>Время</span>
              <span>Описание</span>
              <span>Тип операции</span>
              <span className="text-right">Сумма</span>
              <span />
            </div>
            {movementRows.map(([time, description, amount]) => (
              <div
                className="grid min-w-[760px] grid-cols-[24px_180px_1fr_140px_100px_24px] items-center gap-3 border-b border-primary/10! px-2 py-0.5 text-sm last:border-b-0"
                key={time + description}
              >
                <ReceiptText size={14} className="text-base-content/60!" />
                <span className="text-base-content/70!">{time}</span>
                <span>{description}</span>
                <span className="flex items-center gap-2 text-base-content/65!">
                  <i className="grid size-5 place-items-center rounded-full bg-primary/15 text-primary">
                    ↑
                  </i>{" "}
                  Приход
                </span>
                <strong className="text-right text-primary!">{amount}</strong>
                <button
                  className="btn btn-ghost btn-square btn-xs text-base-content/60!"
                  aria-label={`Действия: ${description}`}
                >
                  <MoreHorizontal size={14} />
                </button>
              </div>
            ))}
          </div>
        </section>
        <section className="card mb-3 gap-3 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
                <Settings size={17} />
              </span>
              <div>
                <h2 className="font-semibold">Автоматизация смен</h2>
                <p className="text-xs text-base-content/60!">
                  Ручное открытие и закрытие остаются доступными всегда.
                </p>
              </div>
            </div>
            <button className="btn btn-outline btn-sm">
              <Plus size={14} /> Добавить кассу
            </button>
          </div>
          <div className="mt-2 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm text-base-content/65! shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            Авторасписаний пока нет. Ручное управление сменой уже доступно выше.
          </div>
        </section>
        <section className="card gap-3 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-primary/12 text-primary">
              <Clock3 size={17} />
            </span>
            <div>
              <h2 className="font-semibold">История смен</h2>
              <p className="text-xs text-base-content/60!">
                Закрытые смены доступны только для чтения.
              </p>
            </div>
          </div>
          <div className="mt-2 grid gap-2 text-sm">
            <div className="flex items-center justify-between border-t border-primary/15! pt-2">
              <span>front-desk · 17.09.2026 · закрыта 17:52</span>
              <span className="badge badge-success badge-soft">Закрыта</span>
            </div>
            <div className="flex items-center justify-between border-t border-primary/15! pt-2">
              <span>front-desk · 28.08.2026 · закрыта 11:14</span>
              <span className="badge badge-success badge-soft">Закрыта</span>
            </div>
          </div>
        </section>
      </>
    );
  }
  return (
    <>
      <div className="relative mt-7 flex flex-wrap items-start justify-between gap-4">
        <div className="relative z-10 flex items-start gap-3">
          <div>
            <p className="mb-1 text-sm text-primary/80!">Финансы · Сегодня</p>
            <h1 className="text-3xl font-bold tracking-tight">Касса</h1>
            <p className="mt-1 text-sm text-base-content/65!">
              Наличные операции хранятся отдельно от депозитов клиентов и оплаты
              игрового времени.
            </p>
          </div>
        </div>
        <button
          className="relative z-10 primary-button btn btn-primary btn-sm"
          disabled={Boolean(openShift)}
          onClick={onOpenShift}
        >
          <Plus size={17} /> Открыть смену
        </button>
      </div>
      {openShift ? (
        <div
          className="card relative mb-4 gap-3 overflow-hidden border border-primary/35! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_28px_rgba(49,217,120,0.14)] backdrop-blur-md"
          style={{
            backgroundImage:
              "linear-gradient(90deg, rgba(3,25,27,.96) 0%, rgba(3,25,27,.88) 48%, rgba(3,25,27,.58)), url(/neon-club-room.png)",
            backgroundPosition: "center",
            backgroundSize: "cover",
            backgroundRepeat: "no-repeat",
          }}
        >
          <div className="card-heading relative z-10 flex items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="grid h-24 w-32 shrink-0 place-items-center rounded-xl border border-primary/30! bg-primary/10">
                <CashRegisterIllustration />
              </div>
              <div>
                <h3>Смена · {openShift.register_id}</h3>
                <p>
                  Открыта{" "}
                  {new Date(openShift.opened_at).toLocaleString("ru-RU")} ·{" "}
                  {openShift.opened_by}
                </p>
              </div>
            </div>
            <span className="active-chip badge badge-success badge-soft">
              Открыта
            </span>
          </div>
          <div className="cash-summary-grid relative z-10 grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className="card min-h-20 gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary!">
                  <Banknote size={16} />
                </span>
                <span className="metric-title text-xs text-base-content/60!">
                  В начале
                </span>
              </div>
              <div className="metric-value text-xl font-bold text-base-content!">
                {cashMoney(openShift.opening_balance_cents)}
              </div>
            </div>
            <div className="card min-h-20 gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary!">
                  <Banknote size={16} />
                </span>
                <span className="metric-title text-xs text-base-content/60!">
                  Ожидается
                </span>
              </div>
              <div className="metric-value text-xl font-bold text-base-content!">
                {cashMoney(openShift.expected_close_cents)}
              </div>
            </div>
            <div className="card min-h-20 gap-2 border border-primary/25! bg-base-100/85! p-3 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
              <div className="flex items-center gap-2">
                <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary/10 text-primary!">
                  <Banknote size={16} />
                </span>
                <span className="metric-title text-xs text-base-content/60!">
                  Разница
                </span>
              </div>
              <div className="metric-value text-xl font-bold text-base-content!">
                —
              </div>
            </div>
          </div>
          <div className="panel-actions relative z-10 flex flex-wrap items-center gap-2">
            <button
              className="secondary-button btn btn-outline btn-sm"
              onClick={() => onRecordMovement?.(openShift)}
            >
              <Plus size={15} /> Движение
            </button>
            <button
              className="primary-button btn btn-primary btn-sm"
              onClick={() => onCloseShift?.(openShift)}
            >
              Закрыть смену
            </button>
          </div>
          <div className="operation-section relative z-10 rounded-lg border border-primary/15! bg-base-100/25! p-3 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <div className="operation-heading mb-2 flex items-center justify-between gap-3">
              <h3>Последние движения</h3>
              <span>{cashMovements.length}</span>
            </div>
            {!!cashMovements.length && (
              <div className="hidden grid-cols-[24px_minmax(8rem,1.15fr)_minmax(0,2fr)_minmax(8rem,1fr)_auto_24px]! gap-3 border-b border-primary/15! px-2 py-1.5 text-xs text-base-content/55 md:grid">
                <span />
                <span>Время</span>
                <span>Описание</span>
                <span>Тип операции</span>
                <span className="text-right">Сумма</span>
                <span />
              </div>
            )}
            {!cashMovements.length && (
              <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
                Движений пока нет
              </div>
            )}
            {cashMovements.map((movement) => (
              <div
                className="operation-row grid grid-cols-[24px_minmax(8rem,1.15fr)_minmax(0,2fr)_minmax(8rem,1fr)_auto_24px]! items-center gap-3 border-t border-primary/10! py-1 text-sm"
                key={movement.id}
              >
                <ReceiptText size={14} className="text-base-content/60!" />
                <time
                  className="truncate text-xs text-base-content/65"
                  dateTime={movement.created_at}
                >
                  {new Date(movement.created_at).toLocaleString("ru-RU")}
                </time>
                <span className="truncate text-sm">{movement.reason}</span>
                <div className="flex min-w-0 items-center gap-2">
                  <div
                    className={`grid size-6! place-items-center rounded-lg ${movement.direction === "cash_out" ? "bg-error/15! text-error!" : "bg-primary/15! text-primary!"}`}
                  >
                    <Banknote size={14} />
                  </div>
                  <span className="truncate text-xs text-base-content/65">
                    {cashDirectionLabels[movement.direction]}
                  </span>
                </div>
                <b
                  className={
                    movement.direction === "cash_out" ||
                    movement.amount_cents < 0
                      ? "whitespace-nowrap text-error!"
                      : "whitespace-nowrap text-primary!"
                  }
                >
                  {movement.direction === "cash_out"
                    ? "-"
                    : movement.amount_cents > 0
                      ? "+"
                      : ""}
                  {cashMoney(Math.abs(movement.amount_cents))}
                </b>
                <button
                  className="btn btn-ghost btn-square btn-xs text-base-content/60!"
                  aria-label={`Действия: ${movement.reason}`}
                >
                  <MoreHorizontal size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="card mb-4 gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.12)] backdrop-blur-md">
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center p-4 text-sm text-base-content!">
            <Banknote size={38} />
            <strong>Открытой смены нет</strong>
            <span className="text-xs">
              Откройте смену перед приёмом наличных.
            </span>
          </div>
        </div>
      )}
      <div className="card mb-4 gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.1)] backdrop-blur-md">
        <div className="card-heading flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">Автоматизация смен</h3>
            <p className="text-sm text-base-content/65">
              Ручное открытие и закрытие остаются доступными всегда.
            </p>
          </div>
          <button
            className="secondary-button btn btn-outline btn-sm"
            onClick={() => setAddingSchedule(true)}
            disabled={addingSchedule}
          >
            <Plus size={15} /> Добавить кассу
          </button>
        </div>

        {cashShiftSchedules.map((schedule) => (
          <CashScheduleEditor
            key={schedule.register_id}
            api={api}
            schedule={schedule}
            onSaved={() => onRefresh()}
          />
        ))}
        {addingSchedule && (
          <CashScheduleEditor
            api={api}
            onSaved={() => {
              onRefresh();
              setAddingSchedule(false);
            }}
            onCancel={() => setAddingSchedule(false)}
          />
        )}
        {!cashShiftSchedules.length && !addingSchedule && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center  p-4 text-sm text-base-content/60!">
            Авторасписаний пока нет. Ручное управление сменой уже доступно выше.
          </div>
        )}
      </div>
      <div className="card gap-3 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.1)] backdrop-blur-md">
        <div className="card-heading flex items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold">История смен</h3>
            <p className="text-sm text-base-content/65">
              Закрытые смены доступны только для чтения.
            </p>
          </div>
        </div>
        {shifts
          .filter((shift) => shift.status === "closed")
          .map((shift) => (
            <div
              className="settings-row flex flex-wrap items-center gap-3 border-t border-primary/15! py-3"
              key={shift.id}
            >
              <div className="justify-self-start">
                <strong className="mx-15">{shift.register_id}</strong>
                <span>
                  {new Date(shift.opened_at).toLocaleDateString("ru-RU")} ·
                  закрыта{" "}
                  {shift.closed_at
                    ? new Date(shift.closed_at).toLocaleTimeString("ru-RU", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"}
                </span>
              </div>
              <b className="mx-15">
                {shift.difference_cents === null
                  ? "—"
                  : `${shift.difference_cents >= 0 ? "+" : ""}${cashMoney(shift.difference_cents)}`}
              </b>
              <span className="active-chip badge badge-success badge-soft">
                Закрыта
              </span>
            </div>
          ))}
        {!shifts.some((shift) => shift.status === "closed") && (
          <div className="flex min-h-40 flex-col items-center justify-center gap-3 text-center before:grid before:size-14 before:place-items-center before:rounded-2xl before:border-2 before:border-primary/25 before:bg-base-200/60 before:text-3xl before:font-light before:leading-none before:text-base-content/35 before:content-['×'] p-4 text-sm text-base-content/60!">
            Закрытых смен пока нет
          </div>
        )}
      </div>
    </>
  );
}

export function CashOpenPanel({
  api,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [registerId, setRegisterId] = useState("front-desk");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(openingBalance);
    if (!registerId.trim() || !Number.isFinite(rubles) || rubles < 0) {
      setError("Укажите название кассы и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.openCashShift(
        {
          register_id: registerId.trim(),
          opening_balance_cents: Math.round(rubles * 100),
        },
        cashIdempotencyKey("cash-open"),
      );
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось открыть смену",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Открыть смену"
        subtitle="Касса · новый рабочий день"
        onClose={onClose}
      />
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Название кассы
          <input
            className="input input-sm"
            value={registerId}
            onChange={(event) => setRegisterId(event.target.value)}
            autoFocus
          />
        </label>
        <label>
          Остаток на начало, ₽
          <input
            className="input input-sm"
            type="number"
            min="0"
            step="0.01"
            value={openingBalance}
            onChange={(event) => setOpeningBalance(event.target.value)}
          />
        </label>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting}
        >
          {submitting ? "Открываем..." : "Открыть смену"}
        </button>
        <p className="mt-1 text-sm text-base-content/70! text-sm text-base-content/65!">
          Для одной кассы одновременно допускается только одна открытая смена.
        </p>
      </form>
    </div>
  );
}

export function CashMovementPanel({
  api,
  shift,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  shift: BackendCashShift;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [direction, setDirection] =
    useState<BackendCashMovement["direction"]>("cash_in");
  const [amount, setAmount] = useState("0");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operationKey] = useState(() => cashIdempotencyKey("cash-movement"));

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(amount);
    if (
      !Number.isFinite(rubles) ||
      (direction !== "correction" && rubles <= 0) ||
      (direction === "correction" && rubles === 0) ||
      !reason.trim()
    ) {
      setError("Укажите сумму и причину движения");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        direction,
        amount_cents: Math.round(rubles * 100),
        reason: reason.trim(),
      };
      const approval =
        direction === "correction"
          ? await api.createCashApproval(
              shift.id,
              {
                kind: "correction",
                target_key: operationKey,
                reason: `Одобрение: ${reason.trim()}`,
              },
              `approval-${operationKey}`,
            )
          : undefined;
      await api.recordCashMovement(
        shift.id,
        { ...payload, approval_id: approval?.id },
        operationKey,
      );
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось записать движение",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Движение наличных"
        subtitle={`Смена · ${shift.register_id}`}
        onClose={onClose}
      />
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <label>
          Тип
          <select
            className="select select-sm"
            value={direction}
            onChange={(event) =>
              setDirection(
                event.target.value as BackendCashMovement["direction"],
              )
            }
          >
            <option value="cash_in">Приход</option>
            <option value="cash_out">Расход</option>
            <option value="correction">Корректировка</option>
          </select>
        </label>
        {direction === "correction" && (
          <p className="mt-1 text-sm text-base-content/70! text-sm text-base-content/65!">
            Для корректировки автоматически запрашивается отдельное supervisor
            approval и сохраняется audit.
          </p>
        )}
        <label>
          Сумма, ₽
          <input
            className="input input-sm"
            type="number"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label>
          Причина
          <input
            className="input input-sm"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Приём наличных"
          />
        </label>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting}
        >
          {submitting ? "Сохраняем..." : "Записать движение"}
        </button>
      </form>
    </div>
  );
}

export function CashClosePanel({
  api,
  shift,
  onClose,
  onSaved,
}: {
  api: GameClubApi;
  shift: BackendCashShift;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [actualBalance, setActualBalance] = useState(
    (shift.expected_close_cents / 100).toFixed(2),
  );
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
      const approval =
        actualCloseCents !== shift.expected_close_cents
          ? await api.createCashApproval(
              shift.id,
              {
                kind: "close_difference",
                target_key: operationKey,
                reason: "Supervisor verified the final count",
              },
              `approval-${operationKey}`,
            )
          : undefined;
      await api.closeCashShift(
        shift.id,
        actualCloseCents,
        operationKey,
        approval?.id,
      );
      onSaved();
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : "Не удалось закрыть смену",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-inner flex flex-col gap-4 p-5">
      <PanelHeader
        title="Закрыть смену"
        subtitle={`Смена · ${shift.register_id}`}
        onClose={onClose}
      />
      <form className="booking-form flex flex-col gap-3" onSubmit={submit}>
        <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/15! bg-base-200/55! p-3 text-sm">
          <span className="text-base-content/60!">Ожидаемый остаток</span>
          <strong>{cashMoney(shift.expected_close_cents)}</strong>
        </div>
        <label>
          Фактический остаток, ₽
          <input
            className="input input-sm"
            type="number"
            min="0"
            step="0.01"
            value={actualBalance}
            onChange={(event) => setActualBalance(event.target.value)}
            autoFocus
          />
        </label>
        {error && (
          <div
            className="form-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
            role="alert"
          >
            {error}
          </div>
        )}
        <button
          className="primary-button btn btn-primary btn-block w-full bg-primary! text-primary-content!"
          disabled={submitting}
        >
          {submitting ? "Закрываем..." : "Закрыть смену"}
        </button>
        <p className="mt-1 text-sm text-base-content/70! text-sm text-base-content/65!">
          После закрытия смена становится неизменяемой, а разница попадает в
          историю.
        </p>
      </form>
    </div>
  );
}
