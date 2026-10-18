import { X } from "lucide-react";

export function PanelHeader({ title, subtitle, onClose }: { title: string; subtitle: string; onClose: () => void }) {
  return <div className="panel-header flex items-start justify-between gap-3 border-b border-primary/15! pb-4"><div><p className="text-xs text-base-content/60!">{subtitle}</p><h2 className="mt-1 text-xl font-bold">{title}</h2></div><button className="icon-button btn btn-ghost btn-circle btn-sm" aria-label={`Закрыть панель «${title}»`} onClick={onClose}><X size={18} /></button></div>;
}
