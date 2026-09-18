import { useRef, useState } from "react";
import { CalendarDays, Check, Clock3, Computer, Edit3, PanelRightClose, Plus, Receipt, Settings, Wifi, X } from "lucide-react";
import { ApiError } from "../../api";
import { Segmented } from "../../shared/components/Segmented";
import { statusMeta } from "../../shared/constants";
import type { Workstation } from "../../types";
import { SessionHoverCard } from "./SessionHoverCard";

export function MapView({ onPc, onSalePc, onBookPc, onEditPc, pcs, group, setGroup, zoneOptions, onNewWorkstation, onPositionsChange }: { onPc: (pc: Workstation) => void; onSalePc: (pc: Workstation) => void; onBookPc: (workstationId?: string) => void; onEditPc: (pc: Workstation) => void; pcs: Workstation[]; group: string; setGroup: (group: string) => void; zoneOptions: string[]; onNewWorkstation?: () => void; onPositionsChange?: (changes: Array<{ workstationId: string; position: number }>) => Promise<void> }) {
  const [draggedWorkstationId, setDraggedWorkstationId] = useState<string | null>(null);
  const [dropTargetSlot, setDropTargetSlot] = useState<number | null>(null);
  const [positionError, setPositionError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [contextPcId, setContextPcId] = useState<string | null>(null);
  const [sessionTooltip, setSessionTooltip] = useState<{ pc: Workstation; left: number; top: number } | null>(null);
  const justDraggedRef = useRef(false);
  const sortedPcs = [...pcs].sort((left, right) => (left.position ?? 999) - (right.position ?? 999));
  const occupiedSlots = new Set<number>();
  const positionedPcs = sortedPcs.map((pc, index) => {
    let slot = pc.position != null && pc.position > 0 ? pc.position - 1 : index;
    if (occupiedSlots.has(slot)) {
      slot = 0;
      while (occupiedSlots.has(slot)) {
        slot += 1;
      }
    }
    occupiedSlots.add(slot);
    return { pc, slot };
  });
  const slotByIndex = new Map(positionedPcs.map((item) => [item.slot, item]));
  const maxSlot = Math.max(23, ...positionedPcs.map(({ slot }) => slot));
  const slotCount = Math.ceil((maxSlot + 1) / 6) * 6;

  const handleDrop = async (event: React.DragEvent<HTMLDivElement>, targetSlot: number) => {
    event.preventDefault();
    setDropTargetSlot(null);
    const sourceId = event.dataTransfer.getData("text/plain") || draggedWorkstationId;
    const source = positionedPcs.find((item) => item.pc.id === sourceId);
    if (!editMode || !source || !onPositionsChange || source.slot === targetSlot) {
      setDraggedWorkstationId(null);
      return;
    }
    const target = slotByIndex.get(targetSlot);
    const changes = [{ workstationId: source.pc.id, position: targetSlot + 1 }];
    if (target) {
      changes.push({ workstationId: target.pc.id, position: source.slot + 1 });
    }
    setPositionError(null);
    setDraggedWorkstationId(null);
    try {
      await onPositionsChange(changes);
    } catch (error) {
      setPositionError(error instanceof ApiError ? error.message : "Не удалось сохранить расстановку мест");
    }
  };

  const showSessionTooltip = (pc: Workstation, target: HTMLButtonElement) => {
    if (!pc.sessionSnapshot || pc.status !== "busy") return;
    const rect = target.getBoundingClientRect();
    const tooltipWidth = 320;
    const tooltipHeight = 360;
    const left = rect.right + tooltipWidth + 12 <= window.innerWidth
      ? rect.right + 12
      : Math.max(12, rect.left - tooltipWidth - 12);
    const top = Math.max(12, Math.min(rect.top, window.innerHeight - tooltipHeight - 12));
    setSessionTooltip({ pc, left, top });
  };

  return <><div className="page-heading"><div><p className="eyebrow">Оборудование · Рабочая карта</p><h1>Карта клуба</h1><p className="subheading">{editMode ? "Перетащите места в нужные ячейки и сохраните планировку." : "Нажмите на свободное место, чтобы оформить продажу; управление ПК — через кнопку ⋯."}</p></div><div className="heading-actions"><button className={`secondary-button map-edit-toggle ${editMode ? "active" : ""}`} aria-pressed={editMode} onClick={() => { setEditMode((value) => !value); setContextPcId(null); }}><Edit3 size={15} /> {editMode ? "Завершить редактирование" : "Редактировать карту"}</button><button className="primary-button" disabled={!onNewWorkstation} onClick={onNewWorkstation}><Plus size={17} /> Добавить место</button></div></div><div className="map-toolbar"><Segmented value={group} onChange={setGroup} options={zoneOptions} />{editMode && onPositionsChange && <span className="map-arrange-hint">Перетащите карточку на нужное место</span>}<div className="legend"><span><i className="legend-dot online" /> Свободен</span><span><i className="legend-dot busy" /> Занят</span><span><i className="legend-dot offline" /> Не в сети</span><span><i className="legend-dot maintenance" /> Сервис</span></div></div>{positionError && <div className="form-error map-error" role="alert">{positionError}</div>}<div className="map-stage"><aside className="map-legend-panel"><div className="map-panel-title"><strong>Состояние мест</strong><span>{pcs.length}</span></div><div className="map-legend-item"><i className="legend-square online" /><span>Свободны</span><b>{pcs.filter((pc) => pc.status === "online").length}</b></div><div className="map-legend-item"><i className="legend-square busy" /><span>Активная сессия</span><b>{pcs.filter((pc) => pc.status === "busy").length}</b></div><div className="map-legend-item"><i className="legend-square offline" /><span>Нет связи</span><b>{pcs.filter((pc) => pc.status === "offline").length}</b></div><div className="map-legend-item"><i className="legend-square maintenance" /><span>Сервис</span><b>{pcs.filter((pc) => pc.status === "maintenance").length}</b></div><div className="map-panel-zone">{group === "Все зоны" ? "Все зоны" : group}</div></aside><div className="map-canvas" aria-label="Карта игровых мест">{pcs.length ? Array.from({ length: slotCount }, (_, slot) => { const placed = slotByIndex.get(slot); const showContext = placed && contextPcId === placed.pc.id && !editMode; return <div className={`map-slot ${placed ? "occupied" : ""} ${dropTargetSlot === slot ? "drop-target" : ""}`} key={slot} aria-label={`Место ${slot + 1}${placed ? `: ${placed.pc.name}` : ": свободно"}`} onDragOver={(event) => { if (editMode && onPositionsChange) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTargetSlot(slot); } }} onDragLeave={() => setDropTargetSlot((current) => current === slot ? null : current)} onDrop={(event) => void handleDrop(event, slot)}>{!placed && <span className="map-slot-number">#{slot + 1}</span>}{placed && <><button className={`map-seat ${placed.pc.status} ${draggedWorkstationId === placed.pc.id ? "is-dragging" : ""}`} draggable={editMode && Boolean(onPositionsChange)} onMouseEnter={(event) => showSessionTooltip(placed.pc, event.currentTarget)} onMouseLeave={() => setSessionTooltip(null)} onFocus={(event) => showSessionTooltip(placed.pc, event.currentTarget)} onBlur={() => setSessionTooltip(null)} onDragStart={(event) => { if (!editMode || !onPositionsChange) return; justDraggedRef.current = true; setPositionError(null); setDraggedWorkstationId(placed.pc.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", placed.pc.id); }} onDragEnd={() => { setDraggedWorkstationId(null); setDropTargetSlot(null); window.setTimeout(() => { justDraggedRef.current = false; }, 0); }} onClick={(event) => { event.stopPropagation(); if (justDraggedRef.current) { justDraggedRef.current = false; return; } if (editMode) { onEditPc(placed.pc); } else if (placed.pc.status === "online") { onSalePc(placed.pc); } else { onPc(placed.pc); } }} onContextMenu={(event) => { event.preventDefault(); setContextPcId(placed.pc.id); }} aria-describedby={placed.pc.sessionSnapshot && placed.pc.status === "busy" ? `session-tooltip-${placed.pc.id}` : undefined} aria-label={`${placed.pc.name}: ${statusMeta[placed.pc.status].label}`}><div className="map-seat-top"><span>{placed.pc.name}</span><span className="map-seat-state">{placed.pc.status === "busy" ? <Wifi size={12} /> : placed.pc.status === "maintenance" ? <Settings size={12} /> : placed.pc.status === "offline" ? <X size={12} /> : <Check size={12} />}</span></div><div className="map-seat-screen"><Computer size={20} /></div><div className="map-seat-bottom"><small>{placed.pc.client || statusMeta[placed.pc.status].label}</small>{placed.pc.tariff && <small>{placed.pc.tariff}</small>}{placed.pc.session && <small><Clock3 size={10} /> {placed.pc.session}</small>}{placed.pc.status === "offline" && placed.pc.lastSeen && <small>HB: {placed.pc.lastSeen}</small>}</div></button><button type="button" className="map-seat-manage" title="Открыть карточку места" aria-label={`Открыть карточку ${placed.pc.name}`} onClick={(event) => { event.stopPropagation(); onPc(placed.pc); }}><PanelRightClose size={12} /></button>{showContext && <div className="map-context-menu" role="menu" onClick={(event) => event.stopPropagation()}><strong>{placed.pc.name}</strong><button role="menuitem" disabled={placed.pc.status !== "online"} onClick={() => { setContextPcId(null); onSalePc(placed.pc); }}><Receipt size={13} /> Оформить продажу</button><button role="menuitem" onClick={() => { setContextPcId(null); onPc(placed.pc); }}><PanelRightClose size={13} /> Открыть карточку</button><button role="menuitem" disabled={placed.pc.status !== "online"} onClick={() => { setContextPcId(null); onBookPc(placed.pc.id); }}><CalendarDays size={13} /> Забронировать</button><button role="menuitem" onClick={() => { setContextPcId(null); onEditPc(placed.pc); }}><Settings size={13} /> Настройки места</button></div>}</>}</div>; }) : <div className="map-empty">Зарегистрированных мест пока нет</div>}</div></div>{sessionTooltip && <SessionHoverCard pc={sessionTooltip.pc} id={`session-tooltip-${sessionTooltip.pc.id}`} style={{ left: sessionTooltip.left, top: sessionTooltip.top }} />}</>;
}
