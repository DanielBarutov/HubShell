import { useEffect, useRef } from "react";
import { MoreHorizontal } from "lucide-react";
import { statusMeta } from "../../shared/constants";
import { PcIllustration } from "../../shared/components/PcIllustration";
import type { Workstation } from "../../types";
import { SessionEndingProjection, sessionTooltip } from "./sessionTooltip";

const statusBadgeClass = (status: Workstation["status"]) =>
  ({
    online: "border-success/30! bg-success/20! text-success!",
    busy: "border-error/35! bg-error/20! text-error!",
    stale: "border-warning/35! bg-warning/20! text-warning!",
    offline:
      "border-base-content/20! bg-base-content/10! text-base-content/70!",
    maintenance: "border-warning/35! bg-warning/20! text-warning!",
  })[status];

export function PcGrid({
  pcs,
  onPc,
  compact = false,
  regularIllustrations = false,
}: {
  pcs: Workstation[];
  onPc: (pc: Workstation) => void;
  compact?: boolean;
  regularIllustrations?: boolean;
}) {
  const endingProjections = useRef(new Map<string, SessionEndingProjection>());
  const endingProjectionFor = (workstationId: string) => {
    let projection = endingProjections.current.get(workstationId);
    if (!projection) {
      projection = new SessionEndingProjection();
      endingProjections.current.set(workstationId, projection);
    }
    return projection;
  };

  useEffect(() => {
    const activeWorkstations = new Set(
      pcs.filter((pc) => pc.status === "busy").map((pc) => pc.id),
    );
    for (const workstationId of endingProjections.current.keys()) {
      if (!activeWorkstations.has(workstationId)) {
        endingProjections.current.delete(workstationId);
      }
    }
  }, [pcs]);

  return (
    <div
      className={`pc-grid grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 ${compact ? "compact" : ""}`}
    >
      {pcs.map((pc) => (
        <button
          className={`pc-card card relative ${compact ? "min-h-48" : "min-h-36"} items-stretch justify-start gap-3 overflow-hidden border bg-base-100/80! bg-none! p-3 text-left text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_18px_rgba(49,217,120,0.06)] backdrop-blur-md hover:bg-base-200! ${pc.status === "busy" ? "border-primary/70! bg-primary/10! shadow-[0_0_18px_rgba(168,255,77,0.14)]" : pc.status === "online" ? "border-primary/30!" : "border-primary/15!"}`}
          key={pc.id}
          onClick={() => onPc(pc)}
          title={sessionTooltip(pc, endingProjectionFor(pc.id))}
        >
          <div
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 opacity-20"
            aria-hidden="true"
          ></div>
          <div className="pc-card-top relative z-10 flex items-center gap-2">
            <span
              className={`pc-status-dot h-2 w-2 shrink-0 rounded-full ${pc.status === "online" ? "bg-success" : pc.status === "busy" ? "bg-primary" : pc.status === "stale" || pc.status === "maintenance" ? "bg-warning" : "bg-neutral-content/40"}`}
            />
            <span className="pc-name grow truncate text-sm font-semibold">
              {pc.name}
            </span>
            <MoreHorizontal size={16} className="text-base-content/50!" />
          </div>
          <div className="pc-illustration relative z-10 flex min-h-14 items-center justify-center">
            <PcIllustration
              compact={compact}
              vip={!regularIllustrations && pc.group === "VIP-зона"}
            />
          </div>
          <div className="pc-card-bottom relative z-10 flex flex-wrap items-center gap-1">
            <span
              className={`badge badge-soft badge-xs ${pc.status === "busy" ? "border-primary/35! bg-primary/20! text-primary!" : statusBadgeClass(pc.status)}`}
            >
              {pc.status === "busy" ? "Занят" : statusMeta[pc.status].label}
            </span>
            {pc.client ? (
              <span className="pc-client flex min-w-0 items-center gap-1 truncate text-xs text-base-content/75!">
                {compact && (
                  <span className="grid size-4 shrink-0 place-items-center rounded-full bg-base-content/20! text-[8px] font-bold text-base-content!">
                    {pc.client.slice(0, 2).toUpperCase()}
                  </span>
                )}
                <span className="truncate">{pc.client}</span>
              </span>
            ) : (
              <span className="pc-zone truncate text-xs text-base-content/60!">
                {pc.group}
              </span>
            )}
            {pc.tariff && (
              <span className="pc-zone truncate text-xs text-base-content/60!">
                {pc.tariff}
              </span>
            )}
          </div>
          {pc.session && (
            <div className="session-time relative z-10 text-xs text-base-content/60!">
              {pc.session}
            </div>
          )}
          {pc.status === "offline" && pc.lastSeen && (
            <div className="session-time relative z-10 text-xs text-base-content/60!">
              Последняя связь: {pc.lastSeen}
            </div>
          )}
        </button>
      ))}
    </div>
  );
}
