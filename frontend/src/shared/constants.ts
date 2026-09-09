import { BarChart3, Banknote, CalendarDays, LayoutDashboard, LayoutGrid, Settings, Users, WalletCards, type LucideIcon } from "lucide-react";
import type { BackendCashMovement, BackendWorkstationGroup } from "../api";
import type { PcStatus, Section } from "../types";

export const navItems: { id: Section; label: string; icon: LucideIcon }[] = [
  { id: "dashboard", label: "Дашборд", icon: LayoutDashboard },
  { id: "map", label: "Карта мест", icon: LayoutGrid },
  { id: "bookings", label: "Бронирования", icon: CalendarDays },
  { id: "clients", label: "Клиенты", icon: Users },
  { id: "catalog", label: "Каталог и тарифы", icon: WalletCards },
  { id: "analytics", label: "Аналитика", icon: BarChart3 },
  { id: "cash", label: "Касса", icon: Banknote },
];

export const statusMeta: Record<PcStatus, { label: string; className: string }> = {
  online: { label: "Свободен", className: "status-online" },
  busy: { label: "Занят", className: "status-busy" },
  stale: { label: "Связь нестабильна", className: "status-stale" },
  offline: { label: "Не в сети", className: "status-offline" },
  maintenance: { label: "Сервис", className: "status-maintenance" },
};

export const themeLabels: Record<BackendWorkstationGroup["theme"], string> = {
  standard: "Стандартная",
  vip: "VIP",
  neon: "Neon",
  minimal: "Минималистичная",
};

export const cashDirectionLabels: Record<BackendCashMovement["direction"], string> = {
  cash_in: "Приход",
  cash_out: "Расход",
  correction: "Коррекция",
};

export { Settings };
