import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  CalendarDays,
  Gamepad2,
  Circle,
  Clock3,
  Edit3,
  LayoutGrid,
  List,
  MoreHorizontal,
  PanelRightClose,
  Plus,
  Receipt,
  Settings,
  ShoppingCart,
  Unplug,
  UserRound,
  Wrench,
} from "lucide-react";
import { ApiError } from "../../api";
import { PcIllustration } from "../../shared/components/PcIllustration";
import { statusMeta } from "../../shared/constants";
import type { Workstation } from "../../types";
import { SessionHoverCard } from "./SessionHoverCard";
import {
  getSessionTooltipDetails,
  SessionEndingProjection,
} from "./sessionTooltip";

const gridSetting = (key: string, fallback: number, max: number) => {
  try {
    const value = Number(window.localStorage.getItem(key));
    return Number.isInteger(value) && value > 0 && value <= max
      ? value
      : fallback;
  } catch {
    return fallback;
  }
};

const saveGridSetting = (key: string, value: number) => {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // Сетка продолжает работать, если браузер запретил постоянное хранилище.
  }
};

export function MapView({
  onPc,
  onSalePc,
  onSellProduct,
  onBookPc,
  onEditPc,
  pcs,
  onNewWorkstation,
  onPositionsChange,
}: {
  onPc: (pc: Workstation) => void;
  onSalePc: (pc: Workstation) => void;
  onSellProduct?: () => void;
  onBookPc: (workstationId?: string) => void;
  onEditPc: (pc: Workstation) => void;
  pcs: Workstation[];
  onNewWorkstation?: () => void;
  onPositionsChange?: (
    changes: Array<{ workstationId: string; position: number }>,
  ) => Promise<void>;
}) {
  const [draggedWorkstationId, setDraggedWorkstationId] = useState<
    string | null
  >(null);
  const [dropTargetSlot, setDropTargetSlot] = useState<number | null>(null);
  const [positionError, setPositionError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [gridColumns, setGridColumns] = useState(() =>
    gridSetting("gameshell.map-grid-columns", 10, 12),
  );
  const [gridRows, setGridRows] = useState(() =>
    gridSetting("gameshell.map-grid-rows", 4, 12),
  );
  const [contextPcId, setContextPcId] = useState<string | null>(null);
  const [sessionTooltip, setSessionTooltip] = useState<{
    workstationId: string;
    left: number;
    top: number;
  } | null>(null);
  const justDraggedRef = useRef(false);
  const endingProjectionsRef = useRef(
    new Map<string, SessionEndingProjection>(),
  );
  const isDemo = pcs.length === 12 && pcs.some((pc) => pc.id === "hall-01");
  const mapPcs = useMemo(() => {
    if (!isDemo) return pcs;
    const normalStatuses: Workstation["status"][] = [
      "online",
      "busy",
      "online",
      "maintenance",
      "online",
      "offline",
      "online",
      "busy",
    ];
    const vipStatuses: Workstation["status"][] = [
      "online",
      "busy",
      "online",
      "offline",
    ];
    const demoNormal = pcs
      .filter((pc) => pc.group !== "VIP-зона")
      .map((pc, index) => ({
        ...pc,
        name: `PC${String(index + 1).padStart(2, "0")}`,
        status: normalStatuses[index] ?? pc.status,
        client:
          index === 1 ? "DanielBarutov" : index === 7 ? "KatanaX" : undefined,
        tariff:
          index === 1
            ? "Тариф Стандарт"
            : index === 7
              ? "Тариф VIP"
              : undefined,
        session:
          index === 1 ? "1 ч 24 мин" : index === 7 ? "2 ч 10 мин" : undefined,
      }));
    const demoExtraNormal: Workstation[] = [
      {
        id: "demo-pc-09",
        name: "PC09",
        group: "Обычный зал",
        status: "offline",
      },
      {
        id: "demo-pc-10",
        name: "PC10",
        group: "Обычный зал",
        status: "online",
      },
      {
        id: "demo-pc-11",
        name: "PC11",
        group: "Обычный зал",
        status: "online",
      },
      {
        id: "demo-pc-12",
        name: "PC12",
        group: "Обычный зал",
        status: "online",
      },
      {
        id: "demo-pc-13",
        name: "PC13",
        group: "Обычный зал",
        status: "online",
      },
      {
        id: "demo-pc-14",
        name: "PC14",
        group: "Обычный зал",
        status: "busy",
        client: "m1rage",
        tariff: "Тариф Ночной",
        session: "45 мин",
      },
      {
        id: "demo-pc-15",
        name: "PC15",
        group: "Обычный зал",
        status: "online",
      },
      {
        id: "demo-pc-16",
        name: "PC16",
        group: "Обычный зал",
        status: "online",
      },
    ];
    const demoVip = pcs
      .filter((pc) => pc.group === "VIP-зона")
      .map((pc, index) => ({
        ...pc,
        name: `VIP${String(index + 1).padStart(2, "0")}`,
        status: vipStatuses[index] ?? pc.status,
        client: index === 1 ? "SilverMoon" : undefined,
        tariff: index === 1 ? "Тариф VIP+" : undefined,
        session: index === 1 ? "3 ч 12 мин" : undefined,
      }));
    return [
      ...demoNormal,
      ...demoExtraNormal,
      ...demoVip,
      {
        id: "demo-vip-05",
        name: "VIP05",
        group: "VIP-зона",
        status: "maintenance" as const,
      },
      {
        id: "demo-vip-06",
        name: "VIP06",
        group: "VIP-зона",
        status: "online" as const,
      },
    ];
  }, [isDemo, pcs]);
  const endingProjectionFor = (workstationId: string) => {
    const existing = endingProjectionsRef.current.get(workstationId);
    if (existing) return existing;
    const created = new SessionEndingProjection();
    endingProjectionsRef.current.set(workstationId, created);
    return created;
  };

  useEffect(() => {
    const activeWorkstationIds = new Set<string>();
    for (const pc of mapPcs) {
      if (!pc.sessionSnapshot || pc.status !== "busy") continue;
      activeWorkstationIds.add(pc.id);
      getSessionTooltipDetails(pc, endingProjectionFor(pc.id));
    }
    for (const workstationId of endingProjectionsRef.current.keys()) {
      if (!activeWorkstationIds.has(workstationId))
        endingProjectionsRef.current.delete(workstationId);
    }
  }, [mapPcs]);
  const positionPcs = (items: Workstation[]) => {
    const occupiedSlots = new Set<number>();
    return [...items]
      .sort((left, right) => (left.position ?? 999) - (right.position ?? 999))
      .map((pc, index) => {
        let slot =
          pc.position != null && pc.position > 0 ? pc.position - 1 : index;
        if (occupiedSlots.has(slot)) {
          slot = 0;
          while (occupiedSlots.has(slot)) slot += 1;
        }
        occupiedSlots.add(slot);
        return { pc, slot };
      });
  };
  const displayPcs = positionPcs(mapPcs);
  const slotByIndex = new Map(displayPcs.map((item) => [item.slot, item]));
  const maxSlot = Math.max(0, ...displayPcs.map(({ slot }) => slot));
  const slotCount = Math.max(gridColumns * gridRows, maxSlot + 1);
  const occupiedCount = isDemo
    ? 6
    : mapPcs.filter((pc) => pc.status === "busy").length;
  const activeSessionCount = isDemo ? 5 : occupiedCount;
  const onlineCount = isDemo
    ? 18
    : mapPcs.filter((pc) => pc.status === "online").length;
  const offlineCount = isDemo
    ? 2
    : mapPcs.filter((pc) => pc.status === "offline").length;
  const maintenanceCount = isDemo
    ? 1
    : mapPcs.filter((pc) => pc.status === "maintenance").length;
  const capacity =
    occupiedCount + onlineCount + offlineCount + maintenanceCount;
  const occupancy = Math.round((occupiedCount / capacity) * 100);
  const seatGridClass =
    viewMode === "grid" ? "grid gap-3" : "grid grid-cols-1 gap-2";
  const seatGridStyle =
    viewMode === "grid"
      ? { gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))` }
      : undefined;

  const renderSlot = (slot: number) => {
    const placed = slotByIndex.get(slot);
    const showContext = placed && contextPcId === placed.pc.id && !editMode;
    return (
      <div
        className={`map-slot relative rounded-xl border border-primary/20! bg-base-100! text-base-content! ${viewMode === "list" ? "flex min-h-16 max-w-[50%] items-stretch gap-2 p-1" : "h-[124px] p-1"} ${placed ? "occupied" : ""} ${placed?.pc.group === "VIP-зона" ? "border-warning/35! bg-warning/5!" : ""} ${placed?.pc.status === "busy" ? "border-error/45! bg-error/5!" : placed?.pc.status === "online" ? "border-success/35!" : placed?.pc.status === "maintenance" ? "border-warning/45! bg-warning/5!" : ""} ${dropTargetSlot === slot ? "border-primary! bg-primary/10!" : ""}`}
        key={slot}
        aria-label={
          placed
            ? `${placed.pc.name}: ${statusMeta[placed.pc.status].label}`
            : `Пустая ячейка ${slot + 1}`
        }
        onDragOver={(event) => {
          if (editMode && onPositionsChange) {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            setDropTargetSlot(slot);
          }
        }}
        onDragLeave={() =>
          setDropTargetSlot((current) => (current === slot ? null : current))
        }
        onDrop={(event) => void handleDrop(event, slot)}
      >
        {!placed && (
          <div
            className={`map-slot-empty h-full rounded-lg border border-dashed border-primary/20! bg-base-200/55! ${viewMode === "list" ? "min-h-16" : "min-h-24"}`}
            aria-hidden="true"
          />
        )}
        {placed && (
          <>
            <button
              className={`map-seat btn btn-ghost relative flex h-full w-full items-stretch justify-between gap-0.5 overflow-hidden rounded-lg p-1 text-left text-base-content! hover:bg-primary/10! ${placed.pc.status === "busy" ? "border-error/55! bg-error/8!" : placed.pc.status === "maintenance" ? "border-warning/45! bg-warning/8!" : placed.pc.status === "offline" ? "border-base-content/15! bg-base-300/55!" : placed.pc.group === "VIP-зона" ? "border-warning/25! bg-base-200/80!" : "border-success/25! bg-base-200/70!"} ${viewMode === "list" ? "min-h-16 flex-row" : "min-h-0 flex-col"} ${placed.pc.status === "online" ? "hover:border-success/50!" : ""} ${draggedWorkstationId === placed.pc.id ? "opacity-50" : ""}`}
              draggable={editMode && Boolean(onPositionsChange)}
              onMouseEnter={(event) =>
                showSessionTooltip(placed.pc, event.currentTarget)
              }
              onMouseLeave={() => setSessionTooltip(null)}
              onFocus={(event) =>
                showSessionTooltip(placed.pc, event.currentTarget)
              }
              onBlur={() => setSessionTooltip(null)}
              onDragStart={(event) => {
                if (!editMode || !onPositionsChange) return;
                justDraggedRef.current = true;
                setPositionError(null);
                setDraggedWorkstationId(placed.pc.id);
                event.dataTransfer.effectAllowed = "move";
                event.dataTransfer.setData("text/plain", placed.pc.id);
              }}
              onDragEnd={() => {
                setDraggedWorkstationId(null);
                setDropTargetSlot(null);
                window.setTimeout(() => {
                  justDraggedRef.current = false;
                }, 0);
              }}
              onClick={(event) => {
                event.stopPropagation();
                if (justDraggedRef.current) {
                  justDraggedRef.current = false;
                  return;
                }
                if (editMode) onEditPc(placed.pc);
                else if (placed.pc.status === "online") onSalePc(placed.pc);
                else onPc(placed.pc);
              }}
              onContextMenu={(event) => {
                event.preventDefault();
                setContextPcId(placed.pc.id);
              }}
              aria-describedby={
                placed.pc.sessionSnapshot && placed.pc.status === "busy"
                  ? `session-tooltip-${placed.pc.id}`
                  : undefined
              }
              aria-label={`${placed.pc.name}: ${statusMeta[placed.pc.status].label}`}
            >
              <div className="map-seat-top flex items-center justify-between gap-2 text-xs font-semibold">
                <span className="min-w-0 truncate">{placed.pc.equipmentType === "xbox" && <Gamepad2 size={12} className="inline mr-1" aria-label="Xbox" />}{placed.pc.name}</span>
                <span className="map-seat-state text-primary!">
                  {placed.pc.status === "busy" ? (
                    <Circle
                      size={12}
                      className="fill-error text-error relative top-4"
                    />
                  ) : placed.pc.status === "maintenance" ? (
                    <Wrench size={12} />
                  ) : placed.pc.status === "offline" ? (
                    <Unplug size={12} className="relative top-4" />
                  ) : (
                    <Circle size={12} className="relative top-4" />
                  )}
                </span>
              </div>
              <span
                className={`badge badge-xs text-[8px] absolute top-[18%] left-[2%] font-semibold self-start ${placed.pc.status === "busy" ? "badge-error" : placed.pc.status === "maintenance" ? "badge-warning" : placed.pc.status === "offline" ? "badge-neutral" : placed.pc.group === "VIP-зона" ? "badge-warning" : "badge-success"}`}
              >
                {statusMeta[placed.pc.status].label}
              </span>
              <div
                className={`map-seat-screen flex mt-3 items-center justify-center ${viewMode === "list" ? "min-h-10 w-20 shrink-0" : "min-h-6"}`}
              >
                {placed.pc.status === "busy" ? (
                  <span className="grid size-8 mt-[5%] place-items-center rounded-full border border-primary/40 bg-primary/25 text-sm font-bold text-primary">
                    {placed.pc.client?.slice(0, 2).toUpperCase() ?? (
                      <UserRound size={18} />
                    )}
                  </span>
                ) : placed.pc.status === "maintenance" ? (
                  <Wrench size={28} className="text-warning mb-[15%]" />
                ) : placed.pc.status === "offline" ? (
                  <Unplug size={28} className="text-base-content/45 mb-[15%]" />
                ) : (
                  <PcIllustration tiny vip={placed.pc.group === "VIP-зона"} />
                )}
              </div>
              <div
                className={`map-seat-bottom flex gap-0.5 text-[9px] leading-tight text-base-content/65! ${viewMode === "list" ? "min-w-0 flex-1 flex-row flex-wrap items-center" : "flex-col"}`}
              >
                <small>
                  {placed.pc.client || statusMeta[placed.pc.status].label}
                </small>
                {placed.pc.tariff && <small>{placed.pc.tariff}</small>}
                {placed.pc.session && (
                  <small className="flex items-center gap-1">
                    <Clock3 size={10} /> {placed.pc.session}
                  </small>
                )}
                {placed.pc.status === "offline" && placed.pc.lastSeen && (
                  <small>HB: {placed.pc.lastSeen}</small>
                )}
              </div>
            </button>

            {showContext && (
              <div
                className="map-context-menu menu menu-sm absolute left-2 top-10 z-20 w-48 rounded-xl border border-primary/25! bg-base-100! p-2 shadow-2xl"
                role="menu"
                onClick={(event) => event.stopPropagation()}
              >
                <strong>{placed.pc.name}</strong>
                <button
                  className="btn btn-ghost btn-sm justify-start"
                  role="menuitem"
                  disabled={placed.pc.status !== "online" && !(placed.pc.equipmentType === "xbox" && placed.pc.status === "busy")}
                  onClick={() => {
                    setContextPcId(null);
                    onSalePc(placed.pc);
                  }}
                >
                  <Receipt size={13} /> Оформить продажу
                </button>
                <button
                  className="btn btn-ghost btn-sm justify-start"
                  role="menuitem"
                  onClick={() => {
                    setContextPcId(null);
                    onPc(placed.pc);
                  }}
                >
                  <PanelRightClose size={13} /> Открыть карточку
                </button>
                {placed.pc.equipmentType !== "xbox" && <button
                  className="btn btn-ghost btn-sm justify-start"
                  role="menuitem"
                  disabled={placed.pc.status !== "online"}
                  onClick={() => {
                    setContextPcId(null);
                    onBookPc(placed.pc.id);
                  }}
                >
                  <CalendarDays size={13} /> Забронировать
                </button>}
                <button
                  className="btn btn-ghost btn-sm justify-start"
                  role="menuitem"
                  onClick={() => {
                    setContextPcId(null);
                    onEditPc(placed.pc);
                  }}
                >
                  <Settings size={13} /> Настройки места
                </button>
              </div>
            )}
          </>
        )}
      </div>
    );
  };

  const handleDrop = async (
    event: React.DragEvent<HTMLDivElement>,
    targetSlot: number,
  ) => {
    event.preventDefault();
    setDropTargetSlot(null);
    const sourceId =
      event.dataTransfer.getData("text/plain") || draggedWorkstationId;
    const source = displayPcs.find((item) => item.pc.id === sourceId);
    if (
      !editMode ||
      !source ||
      !onPositionsChange ||
      source.slot === targetSlot
    ) {
      setDraggedWorkstationId(null);
      return;
    }
    const target = slotByIndex.get(targetSlot);
    const changes = [{ workstationId: source.pc.id, position: targetSlot + 1 }];
    if (target)
      changes.push({
        workstationId: target.pc.id,
        position: source.slot + 1,
      });
    setPositionError(null);
    setDraggedWorkstationId(null);
    try {
      await onPositionsChange(changes);
    } catch (error) {
      setPositionError(
        error instanceof ApiError
          ? error.message
          : "Не удалось сохранить расстановку мест",
      );
    }
  };

  const showSessionTooltip = (pc: Workstation, target: HTMLButtonElement) => {
    if (!pc.sessionSnapshot || pc.status !== "busy") return;
    const rect = target.getBoundingClientRect();
    const tooltipWidth = 320;
    const tooltipHeight = 360;
    const left =
      rect.right + tooltipWidth + 12 <= window.innerWidth
        ? rect.right + 12
        : Math.max(12, rect.left - tooltipWidth - 12);
    const top = Math.max(
      12,
      Math.min(rect.top, window.innerHeight - tooltipHeight - 12),
    );
    setSessionTooltip({ workstationId: pc.id, left, top });
  };

  return (
    <>
      <div className="mb-5 mt-7 flex flex-wrap items-start justify-between gap-4 lg:flex-nowrap">
        <div className="flex min-w-0 grow items-start gap-4">
          <div>
            <p className="mb-1 text-sm text-base-content/65!">
              Оборудование · Рабочая карта
            </p>
            <h1 className="text-3xl font-bold tracking-tight">Карта клуба</h1>
            <p className="mt-1 text-xs text-base-content/70!">
              {editMode
                ? "Перетащите места в нужные ячейки и сохраните планировку."
                : "Управление оборудованием и свободными местами. Нажмите на место, чтобы оформить продажу, начать сессию или изменить настройки."}
            </p>
          </div>
        </div>
        <div className="heading-actions flex shrink-0 flex-wrap items-center gap-2">
          <button
            className={`secondary-button btn btn-outline btn-sm map-edit-toggle ${editMode ? "active border-primary! bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : ""}`}
            aria-pressed={editMode}
            onClick={() => {
              setEditMode((value) => !value);
              setContextPcId(null);
            }}
          >
            <Edit3 size={15} />{" "}
            {editMode ? "Завершить редактирование" : "Редактировать карту"}
          </button>
          <button
            className="secondary-button btn btn-outline btn-sm"
            onClick={onSellProduct}
          >
            <ShoppingCart size={16} /> Продать товар
          </button>
          <button
            className="primary-button btn btn-primary btn-sm"
            onClick={onNewWorkstation ?? (() => undefined)}
          >
            <Plus size={17} /> Добавить место
          </button>
        </div>
      </div>
      <div className="map-toolbar mb-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          {editMode && onPositionsChange && (
            <span className="map-arrange-hint">
              Перетащите карточку на нужное место
            </span>
          )}
          <div className="legend flex flex-wrap items-center gap-3 text-xs text-base-content/70!">
            <span>
              <i className="legend-dot online mr-1 inline-block h-2 w-2 rounded-full bg-success" />{" "}
              Свободен
            </span>
            <span>
              <i className="legend-dot busy mr-1 inline-block h-2 w-2 rounded-full bg-error" />{" "}
              Занят
            </span>
            <span>
              <i className="legend-dot offline mr-1 inline-block h-2 w-2 rounded-full bg-neutral-content/40" />{" "}
              Не в сети
            </span>
            <span>
              <i className="legend-dot maintenance mr-1 inline-block h-2 w-2 rounded-full bg-warning" />{" "}
              Сервис
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs text-base-content/70!">
            Столбцы
            <select
              className="select select-bordered select-sm w-16"
              aria-label="Столбцы карты"
              value={gridColumns}
              onChange={(event) => {
                const value = Number(event.target.value);
                setGridColumns(value);
                saveGridSetting("gameshell.map-grid-columns", value);
              }}
            >
              {[3, 4, 5, 6, 8, 10, 12].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1 text-xs text-base-content/70!">
            Ряды
            <select
              className="select select-bordered select-sm w-16"
              aria-label="Ряды карты"
              value={gridRows}
              onChange={(event) => {
                const value = Number(event.target.value);
                setGridRows(value);
                saveGridSetting("gameshell.map-grid-rows", value);
              }}
            >
              {[2, 3, 4, 5, 6, 8, 10, 12].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <div className="join border rounded-xl border-primary/20! bg-base-100/55! p-0.5 shadow-[inset_0_0_16px_rgba(49,217,120,0.04)]">
            <button
              className={`btn btn-square btn-sm join-item ${viewMode === "grid" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost"}`}
              aria-label="Показать сеткой"
              aria-pressed={viewMode === "grid"}
              onClick={() => setViewMode("grid")}
            >
              <LayoutGrid size={15} />
            </button>
            <button
              className={`btn btn-square btn-sm join-item ${viewMode === "list" ? "bg-primary! text-primary-content! hover:bg-primary! hover:text-primary-content!" : "btn-ghost"}`}
              aria-label="Показать списком"
              aria-pressed={viewMode === "list"}
              onClick={() => setViewMode("list")}
            >
              <List size={15} />
            </button>
          </div>
        </div>
      </div>
      {positionError && (
        <div
          className="form-error map-error rounded-lg border border-error/40! bg-error/10! p-3 text-sm text-error-content!"
          role="alert"
        >
          {positionError}
        </div>
      )}
      <div className="map-stage grid grid-cols-1 gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <aside className="map-legend-panel card h-fit gap-2 border border-primary/25! bg-base-100/85! p-4 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2),0_0_24px_rgba(49,217,120,0.1)] backdrop-blur-md">
          <div className="map-panel-title mb-2 flex items-center justify-between border-b border-primary/20! pb-3">
            <strong>Состояние мест</strong>
          </div>
          <div className="map-occupancy mb-2 flex flex-col items-center gap-0 rounded-xl border border-primary/20 bg-primary/5 p-3 text-center">
            <div
              className="radial-progress bg-base-300/35 text-primary border-primary/20 border-x outline-3 outline-offset-2"
              style={
                {
                  "--value": occupancy,
                  "--size": "7.5rem",
                  "--thickness": "0.4rem",
                } as CSSProperties
              }
              role="progressbar"
              aria-label="Занятость мест"
            >
              <span className="flex flex-col items-center leading-tight">
                <strong className="text-2xl font-semibold text-base-content!">
                  {occupiedCount}
                </strong>
                <small className="text-xs text-base-content/65!">
                  из {capacity}
                </small>
                <small className="text-xs text-base-content/65!">занято</small>
              </span>
            </div>
          </div>
          <div className="map-legend-item flex items-center gap-2 border-b border-primary/15! py-2 text-sm">
            <i className="legend-square border border-base-content/25! bg-base-content/10!" />
            <span>Всего мест</span>
            <b className="ml-auto">{capacity}</b>
          </div>
          <div className="map-legend-item flex items-center gap-2 border-b border-primary/15! py-2 text-sm">
            <i className="legend-square online" />
            <span>Свободны</span>
            <b className="ml-auto">{onlineCount}</b>
          </div>
          <div className="map-legend-item flex items-center gap-2 border-b border-primary/15! py-2 text-sm">
            <i className="legend-square busy" />
            <span>Активная сессия</span>
            <b className="ml-auto">{activeSessionCount}</b>
          </div>
          <div className="map-legend-item flex items-center gap-2 border-b border-primary/15! py-2 text-sm">
            <i className="legend-square offline" />
            <span>Нет связи</span>
            <b className="ml-auto">{offlineCount}</b>
          </div>
          <div className="map-legend-item flex items-center gap-2 border-b border-primary/15! py-2 text-sm">
            <i className="legend-square maintenance" />
            <span>Сервис</span>
            <b className="ml-auto">{maintenanceCount}</b>
          </div>
        </aside>
        <div
          className="map-canvas flex flex-col gap-5 rounded-xl border border-primary/20! bg-base-100/55! p-4 shadow-[0_0_24px_rgba(49,217,120,0.06)] backdrop-blur-md"
          aria-label="Карта игровых мест"
        >
          {mapPcs.length ? (
            <div className={seatGridClass} style={seatGridStyle}>
              {Array.from({ length: slotCount }, (_, slot) => renderSlot(slot))}
            </div>
          ) : (
            <div className="map-empty p-8 text-center text-sm text-base-content/60!">
              Зарегистрированных мест пока нет
            </div>
          )}
        </div>
      </div>
      {sessionTooltip &&
        (() => {
          const tooltipPc = mapPcs.find(
            (pc) => pc.id === sessionTooltip.workstationId,
          );
          return tooltipPc ? (
            <SessionHoverCard
              pc={tooltipPc}
              id={`session-tooltip-${tooltipPc.id}`}
              style={{ left: sessionTooltip.left, top: sessionTooltip.top }}
              endingProjection={endingProjectionFor(tooltipPc.id)}
            />
          ) : null;
        })()}
    </>
  );
}
