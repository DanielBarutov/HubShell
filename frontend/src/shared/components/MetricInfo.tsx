import { Info } from "lucide-react";
import { useId, useState, type MouseEventHandler } from "react";

export type MetricInfoData = {
  description: string;
  formula: string;
  source: string;
  emptyState: string;
};

export function MetricInfo({ title, info }: { title: string; info: MetricInfoData }) {
  const tooltipId = useId();
  const [open, setOpen] = useState(false);
  const close: MouseEventHandler<HTMLDivElement> = () => setOpen(false);

  return (
    <div
      className="metric-info"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={close}
    >
      <button
        type="button"
        className="metric-info-button"
        aria-label={`Описание метрики: ${title}`}
        aria-expanded={open}
        aria-describedby={open ? tooltipId : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        <Info size={13} aria-hidden="true" />
      </button>
      {open && (
        <div id={tooltipId} role="tooltip" className="metric-info-tooltip">
          <strong>{info.description}</strong>
          <span><b>Формула:</b> {info.formula}</span>
          <span><b>Источник:</b> {info.source}</span>
          <span><b>Если данных нет:</b> {info.emptyState}</span>
        </div>
      )}
    </div>
  );
}
