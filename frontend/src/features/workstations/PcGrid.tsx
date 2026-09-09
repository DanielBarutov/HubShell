import { Clock3, Computer, MoreHorizontal } from "lucide-react";
import { statusMeta } from "../../shared/constants";
import type { Workstation } from "../../types";

export function PcGrid({ pcs, onPc, compact = false }: { pcs: Workstation[]; onPc: (pc: Workstation) => void; compact?: boolean }) {
  return <div className={`pc-grid ${compact ? "compact" : ""}`}>{pcs.map((pc) => <button className="pc-card" key={pc.id} onClick={() => onPc(pc)}><div className="pc-card-top"><span className={`pc-status-dot ${pc.status}`} /><span className="pc-name">{pc.name}</span><MoreHorizontal size={16} className="muted" /></div><div className="pc-illustration"><Computer size={compact ? 28 : 34} strokeWidth={1.45} /></div><div className="pc-card-bottom"><span className={statusMeta[pc.status].className}>{statusMeta[pc.status].label}</span>{pc.client ? <span className="pc-client">{pc.client}</span> : <span className="pc-zone">{pc.group}</span>}{pc.tariff && <span className="pc-zone">{pc.tariff}</span>}</div>{pc.session && <div className="session-time"><Clock3 size={12} /> {pc.session}</div>}{pc.status === "offline" && pc.lastSeen && <div className="session-time">Последняя связь: {pc.lastSeen}</div>}</button>)}</div>;
}
