import type { ReactNode } from "react";
import { ArrowUpRight } from "lucide-react";

export function MetricCard({ title, value, delta, positive, icon, accent }: { title: string; value: string; delta: string; positive?: boolean; icon: ReactNode; accent: string }) {
  return <div className="metric-card"><div className={`metric-icon ${accent}`}>{icon}</div><div className="metric-title">{title}</div><div className="metric-value">{value}</div><div className={`metric-delta ${positive ? "positive" : ""}`}>{positive && <ArrowUpRight size={14} />}{delta}</div></div>;
}
