import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronDown, ChevronRight, Clock3 } from "lucide-react";
import { localDateInputValue } from "../formatters";

export type PickerMode = "date" | "datetime" | "time";

function pickerTimeValue(value: string): { hour: number; minute: number } {
  const [, timePart = "00:00"] = value.split("T");
  const [hour, minute] = timePart.split(":").map(Number);
  return { hour: Number.isFinite(hour) ? hour : 0, minute: Number.isFinite(minute) ? minute : 0 };
}

export function parsePickerValue(value: string, mode: PickerMode): Date {
  const fallback = new Date();
  if (mode === "time") {
    const { hour, minute } = pickerTimeValue(value);
    return new Date(fallback.getFullYear(), fallback.getMonth(), fallback.getDate(), hour, minute);
  }
  const [datePart, timePart = "00:00"] = value.split("T");
  const [year, month, day] = (datePart || localDateInputValue(fallback)).split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  return new Date(
    Number.isFinite(year) ? year : fallback.getFullYear(),
    Number.isFinite(month) ? month - 1 : fallback.getMonth(),
    Number.isFinite(day) ? day : fallback.getDate(),
    mode === "date" ? 12 : Number.isFinite(hour) ? hour : 0,
    mode === "date" ? 0 : Number.isFinite(minute) ? minute : 0,
  );
}

export function DateTimePicker({ value, onChange, mode, label, disabled = false, className = "" }: {
  value: string;
  onChange: (value: string) => void;
  mode: PickerMode;
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectedDate = parsePickerValue(value, mode);
  const [open, setOpen] = useState(false);
  const [viewDate, setViewDate] = useState(selectedDate);
  const time = pickerTimeValue(value);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => { if (open) setViewDate(selectedDate); }, [open, value]);

  const dateText = selectedDate.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
  const displayValue = mode === "time"
    ? `${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`
    : mode === "date" ? dateText : `${dateText} · ${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`;
  const monthLabel = viewDate.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
  const firstDay = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
  const leadingDays = (firstDay.getDay() + 6) % 7;
  const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
  const calendarDays = Array.from({ length: Math.ceil((leadingDays + daysInMonth) / 7) * 7 }, (_, index) => new Date(viewDate.getFullYear(), viewDate.getMonth(), index - leadingDays + 1));
  const selectedDateKey = localDateInputValue(selectedDate);

  const selectDate = (date: Date) => {
    const nextDate = localDateInputValue(date);
    onChange(mode === "datetime" ? `${nextDate}T${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}` : nextDate);
    setViewDate(date);
    if (mode === "date") setOpen(false);
  };
  const selectTime = (hour: number, minute: number) => {
    const date = localDateInputValue(selectedDate);
    onChange(mode === "time" ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` : `${date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  };

  return <div className={`date-time-picker ${open ? "open" : ""} ${className}`} ref={wrapperRef} onClick={(event) => event.stopPropagation()}>
    <button type="button" className="date-time-trigger" aria-label={label} aria-expanded={open} disabled={disabled} onClick={() => setOpen((current) => !current)}>
      {mode === "time" ? <Clock3 size={15} /> : <CalendarDays size={15} />}<span>{displayValue}</span><ChevronDown size={14} className="date-time-chevron" />
    </button>
    {open && <div className={`date-time-popover ${mode === "time" ? "time-only" : ""}`} role="dialog" aria-label={`${label}: выбор значения`}>
      {mode !== "time" && <>
        <div className="picker-month-head"><button type="button" aria-label="Предыдущий месяц" onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1))}><ChevronRight size={15} className="rotate-180" /></button><strong>{monthLabel}</strong><button type="button" aria-label="Следующий месяц" onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1))}><ChevronRight size={15} /></button></div>
        <div className="picker-weekdays">{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => <span key={day}>{day}</span>)}</div>
        <div className="picker-calendar">{calendarDays.map((day) => <button type="button" key={localDateInputValue(day)} className={`${day.getMonth() !== viewDate.getMonth() ? "outside" : ""} ${localDateInputValue(day) === selectedDateKey ? "selected" : ""}`} onClick={() => selectDate(day)}>{day.getDate()}</button>)}</div>
        <button type="button" className="picker-today" onClick={() => selectDate(new Date())}>Сегодня</button>
      </>}
      {mode !== "date" && <div className="picker-time-panel"><span>Время</span><div className="picker-time-selects"><label><span>Часы</span><select aria-label={`${label}: часы`} value={time.hour} onChange={(event) => selectTime(Number(event.target.value), time.minute)}>{Array.from({ length: 24 }, (_, hour) => <option value={hour} key={hour}>{String(hour).padStart(2, "0")}</option>)}</select></label><b>:</b><label><span>Минуты</span><select aria-label={`${label}: минуты`} value={time.minute} onChange={(event) => selectTime(time.hour, Number(event.target.value))}>{Array.from({ length: 60 }, (_, minute) => <option value={minute} key={minute}>{String(minute).padStart(2, "0")}</option>)}</select></label></div></div>}
      {mode !== "date" && <button type="button" className="picker-done" onClick={() => setOpen(false)}>Готово</button>}
    </div>}
  </div>;
}
