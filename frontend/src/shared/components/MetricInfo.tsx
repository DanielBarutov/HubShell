import { Info } from "lucide-react";
import { useId, useState, type MouseEventHandler } from "react";

export type MetricInfoData = {
  description: string;
  formula: string;
  source: string;
  emptyState: string;
};

export function MetricInfo({
  title,
  info,
}: {
  title: string;
  info: MetricInfoData;
}) {
  const tooltipId = useId();
  const [open, setOpen] = useState(false);
  const close: MouseEventHandler<HTMLDivElement> = () => setOpen(false);

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={close}
    >
      <button
        type="button"
        className="btn btn-ghost btn-circle btn-xs text-base-content/55!"
        aria-label={`Описание метрики: ${title}`}
        aria-expanded={open}
        aria-describedby={open ? tooltipId : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <Info size={13} aria-hidden="true" />
      </button>
      {open && (
        <div
          id={tooltipId}
          role="tooltip"
          className="absolute right-0 top-7 z-50 flex w-64 flex-col gap-2 rounded-xl border border-primary/25! bg-base-100/95! p-3 text-left text-xs text-base-content! shadow-xl backdrop-blur-xl"
        >
          <strong>{info.description}</strong>
          <span>
            <b>Формула:</b> {info.formula}
          </span>
          <span>
            <b>Источник:</b> {info.source}
          </span>
          <span>
            <b>Если данных нет:</b> {info.emptyState}
          </span>
        </div>
      )}
    </div>
  );
}
