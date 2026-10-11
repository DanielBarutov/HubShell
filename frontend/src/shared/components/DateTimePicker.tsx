import { useEffect, useRef, useState } from "react";
import { CalendarDays, ChevronDown, ChevronRight, Clock3 } from "lucide-react";
import { localDateInputValue } from "../formatters";

export type PickerMode = "date" | "datetime" | "time";

function pickerTimeValue(value: string): { hour: number; minute: number } {
  const timePart = value.includes("T")
    ? (value.split("T")[1] ?? "00:00")
    : value || "00:00";
  const [hour, minute] = timePart.split(":").map(Number);
  return {
    hour: Number.isFinite(hour) ? hour : 0,
    minute: Number.isFinite(minute) ? minute : 0,
  };
}

export function parsePickerValue(value: string, mode: PickerMode): Date {
  const fallback = new Date();
  if (mode === "time") {
    const { hour, minute } = pickerTimeValue(value);
    return new Date(
      fallback.getFullYear(),
      fallback.getMonth(),
      fallback.getDate(),
      hour,
      minute,
    );
  }
  const [datePart, timePart = "00:00"] = value.split("T");
  const [year, month, day] = (datePart || localDateInputValue(fallback))
    .split("-")
    .map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  return new Date(
    Number.isFinite(year) ? year : fallback.getFullYear(),
    Number.isFinite(month) ? month - 1 : fallback.getMonth(),
    Number.isFinite(day) ? day : fallback.getDate(),
    mode === "date" ? 12 : Number.isFinite(hour) ? hour : 0,
    mode === "date" ? 0 : Number.isFinite(minute) ? minute : 0,
  );
}

export function DateTimePicker({
  value,
  onChange,
  mode,
  label,
  disabled = false,
  className = "",
  minuteStep = 1,
  popoverPlacement = "bottom",
}: {
  value: string;
  onChange: (value: string) => void;
  mode: PickerMode;
  label: string;
  disabled?: boolean;
  className?: string;
  minuteStep?: 1 | 30;
  popoverPlacement?: "bottom" | "top";
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectedDate = parsePickerValue(value, mode);
  const [open, setOpen] = useState(false);
  const [viewDate, setViewDate] = useState(selectedDate);
  const time = pickerTimeValue(value);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      )
        setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => {
    if (open) setViewDate(selectedDate);
  }, [open, value]);

  const dateText = selectedDate.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const displayValue =
    mode === "time"
      ? `${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`
      : mode === "date"
        ? dateText
        : `${dateText} · ${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`;
  const monthLabel = viewDate.toLocaleDateString("ru-RU", {
    month: "long",
    year: "numeric",
  });
  const firstDay = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
  const leadingDays = (firstDay.getDay() + 6) % 7;
  const daysInMonth = new Date(
    viewDate.getFullYear(),
    viewDate.getMonth() + 1,
    0,
  ).getDate();
  const calendarDays = Array.from(
    { length: Math.ceil((leadingDays + daysInMonth) / 7) * 7 },
    (_, index) =>
      new Date(
        viewDate.getFullYear(),
        viewDate.getMonth(),
        index - leadingDays + 1,
      ),
  );
  const selectedDateKey = localDateInputValue(selectedDate);

  const selectDate = (date: Date) => {
    const nextDate = localDateInputValue(date);
    onChange(
      mode === "datetime"
        ? `${nextDate}T${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`
        : nextDate,
    );
    setViewDate(date);
    if (mode === "date") setOpen(false);
  };
  const selectTime = (hour: number, minute: number) => {
    const date = localDateInputValue(selectedDate);
    onChange(
      mode === "time"
        ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`
        : `${date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`,
    );
  };

  return (
    <div
      className={`date-time-picker relative ${open ? "z-30" : ""} ${className}`}
      ref={wrapperRef}
      onClick={(event) => event.stopPropagation()}
    >
      <button
        type="button"
        className="date-time-trigger btn btn-outline btn-sm gap-2 border-primary/20! bg-base-200/55! text-base-content!"
        aria-label={label}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {mode === "time" ? <Clock3 size={15} /> : <CalendarDays size={15} />}
        <span>{displayValue}</span>
        <ChevronDown size={14} className="date-time-chevron" />
      </button>
      {open && (
        <div
          className={`date-time-popover absolute right-0 z-50 w-72 rounded-xl border border-primary/25! bg-base-100! p-3 text-base-content! shadow-2xl ${popoverPlacement === "top" ? "bottom-full mb-2" : "top-full mt-2"} ${mode === "time" ? "time-only" : ""}`}
          role="dialog"
          aria-label={`${label}: выбор значения`}
        >
          {mode !== "time" && (
            <>
              <div className="picker-month-head flex items-center justify-between">
                <button
                  type="button"
                  className="btn btn-ghost btn-circle btn-xs"
                  aria-label="Предыдущий месяц"
                  onClick={() =>
                    setViewDate(
                      new Date(
                        viewDate.getFullYear(),
                        viewDate.getMonth() - 1,
                        1,
                      ),
                    )
                  }
                >
                  <ChevronRight size={15} className="rotate-180" />
                </button>
                <strong className="text-sm capitalize">{monthLabel}</strong>
                <button
                  type="button"
                  className="btn btn-ghost btn-circle btn-xs"
                  aria-label="Следующий месяц"
                  onClick={() =>
                    setViewDate(
                      new Date(
                        viewDate.getFullYear(),
                        viewDate.getMonth() + 1,
                        1,
                      ),
                    )
                  }
                >
                  <ChevronRight size={15} />
                </button>
              </div>
              <div className="picker-weekdays grid grid-cols-7 gap-1 py-2 text-center text-[10px] text-base-content/50!">
                {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>
              <div className="picker-calendar grid grid-cols-7 gap-1">
                {calendarDays.map((day) => (
                  <button
                    type="button"
                    key={localDateInputValue(day)}
                    className={`btn btn-ghost btn-xs ${day.getMonth() !== viewDate.getMonth() ? "text-base-content/30!" : ""} ${localDateInputValue(day) === selectedDateKey ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : ""}`}
                    onClick={() => selectDate(day)}
                  >
                    {day.getDate()}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="picker-today btn btn-ghost btn-sm mt-2 w-full text-primary!"
                onClick={() => selectDate(new Date())}
              >
                Сегодня
              </button>
            </>
          )}
          {mode !== "date" && (
            <div className="picker-time-panel mt-3 border-t border-primary/15! pt-3">
              {minuteStep === 30 ? (
                <div className="mt-2 grid grid-cols-4 gap-1">
                  {Array.from({ length: 48 }, (_, index) => {
                    const hour = Math.floor(index / 2);
                    const minute = (index % 2) * 30;
                    const selected =
                      hour === time.hour && minute === time.minute;
                    return (
                      <button
                        type="button"
                        key={`${hour}:${minute}`}
                        className={`btn btn-xs ${selected ? "btn-primary" : "btn-ghost"}`}
                        onClick={() => selectTime(hour, minute)}
                      >
                        {String(hour).padStart(2, "0")}:
                        {String(minute).padStart(2, "0")}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="picker-time-selects mt-2 flex items-end gap-2">
                  <label className="flex flex-1 flex-col gap-1 text-[10px] text-base-content/60!">
                    Часы
                    <select
                      className="select select-xs w-full"
                      aria-label={`${label}: часы`}
                      value={time.hour}
                      onChange={(event) =>
                        selectTime(Number(event.target.value), time.minute)
                      }
                    >
                      {Array.from({ length: 24 }, (_, hour) => (
                        <option value={hour} key={hour}>
                          {String(hour).padStart(2, "0")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <b className="pb-1">:</b>
                  <label className="flex flex-1 flex-col gap-1 text-[10px] text-base-content/60!">
                    Минуты
                    <select
                      className="select select-xs w-full"
                      aria-label={`${label}: минуты`}
                      value={time.minute}
                      onChange={(event) =>
                        selectTime(time.hour, Number(event.target.value))
                      }
                    >
                      {Array.from({ length: 60 }, (_, minute) => (
                        <option value={minute} key={minute}>
                          {String(minute).padStart(2, "0")}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
            </div>
          )}
          {mode !== "date" && (
            <button
              type="button"
              className="picker-done btn btn-primary btn-sm mt-2"
              onClick={() => setOpen(false)}
            >
              Готово
            </button>
          )}
        </div>
      )}
    </div>
  );
}
