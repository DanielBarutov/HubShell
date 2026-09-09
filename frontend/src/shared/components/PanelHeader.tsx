import { X } from "lucide-react";

export function PanelHeader({ title, subtitle, onClose }: { title: string; subtitle: string; onClose: () => void }) {
  return <div className="panel-header"><div><p>{subtitle}</p><h2>{title}</h2></div><button className="icon-button" aria-label={`Закрыть панель «${title}»`} onClick={onClose}><X size={18} /></button></div>;
}
