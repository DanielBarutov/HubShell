import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";
import { MetricInfo, type MetricInfoData } from "./MetricInfo";

export function MetricCard({
  title,
  value,
  delta,
  positive,
  icon,
  accent,
  info,
  state,
  stateLabel,
}: {
  title: string;
  value: string;
  delta: string;
  positive?: boolean;
  icon: ReactNode;
  accent: string;
  info?: MetricInfoData;
  state?: string;
  stateLabel?: string;
}) {
  const displayDelta = stateLabel && state && state !== "ready" && state !== "available" ? `${stateLabel} · ${delta}` : delta;
  const hasNonReadyState = state !== undefined && state !== "ready" && state !== "available";
  return (
    <div className={`metric-card${hasNonReadyState ? ` metric-card-${state}` : ""}`} data-state={state}>
      <div className={`metric-icon ${accent}`}>{icon}</div>
      <div className="metric-title-row">
        <div className="metric-title">{title}</div>
        {info && <MetricInfo title={title} info={info} />}
      </div>
      <div className="metric-value">{value}</div>
      <div className={`metric-delta ${positive ? "positive" : ""}`}>{positive && <ArrowUpRight size={14} />}{displayDelta}</div>
    </div>
  );
}
