import { useEffect } from "react";
import { ChevronDown, ChevronRight, CircleHelp, Command, MoreHorizontal, Plus, Search, Settings } from "lucide-react";
import { useAppDispatch, useAppSelector } from "./hooks";
import { useReduxApi } from "./reduxApi";
import { LIVE_MODE } from "./config";
import { selectAuth } from "../features/auth/authSlice";
import { refreshWorkspace, persistWorkstationPositions, selectWorkspace } from "../features/workspace/workspaceSlice";
import {
  openBooking, openBookingEdit, openCashClose, openCashMovement, openClient, openDeposit, openNewClient, openNewWorkstation, openPanel, openPc, openSale, openWorkstationEditor,
  selectGroup, selectPaymentMethod, selectProduct, setGroup, setSearch, setSection, selectUi,
} from "../features/workspace/uiSlice";
import { navItems } from "../shared/constants";
import { AnalyticsView, Dashboard } from "../features/dashboard/DashboardScreen";
import { BookingsView } from "../features/bookings/BookingsScreen";
import { ClientsView } from "../features/clients/ClientsScreen";
import { CatalogView } from "../features/catalog/CatalogScreen";
import { CashView } from "../features/cash/CashScreen";
import { SettingsView } from "../features/settings/SettingsScreen";
import { MapView } from "../features/workstations/MapScreen";
import { PanelHost } from "./PanelHost";
import type { Client, Workstation } from "../types";
import type { BackendProduct } from "../api";
import { LoginScreen } from "../features/auth/LoginScreen";

export function AppShell() {
  const dispatch = useAppDispatch();
  const auth = useAppSelector(selectAuth);
  const workspace = useAppSelector(selectWorkspace);
  const ui = useAppSelector(selectUi);
  const api = useReduxApi();

  useEffect(() => {
    if (!LIVE_MODE || !auth.isAuthenticated) return undefined;
    let active = true;
    let inFlight = false;
    const refresh = () => {
      if (!active || inFlight) return;
      inFlight = true;
      void dispatch(refreshWorkspace()).finally(() => { inFlight = false; });
    };
    refresh();
    const timer = window.setInterval(refresh, 5_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [auth.isAuthenticated, dispatch]);

  if (LIVE_MODE && (!auth.isAuthenticated || auth.isRestoring)) return <LoginScreen />;
  if (LIVE_MODE && workspace.loading && !workspace.lastUpdatedAt) return <div className="app-shell"><main className="main-content"><div className="content-wrap"><div className="empty-state-card live-loading-state" role="status">Подключаемся к серверу и загружаем рабочие места…</div></div></main></div>;

  const currentPcs = workspace.workstations;
  const currentClients = workspace.clients;
  const zoneOptions = ["Все зоны", ...Array.from(new Set(currentPcs.map((pc) => pc.group).filter(Boolean)))];
  const visiblePcs = currentPcs.filter((pc) => ui.group === "Все зоны" || pc.group === ui.group);
  const openPcPanel = (pc: Workstation) => dispatch(openPc(pc.id));
  const openClientPanel = (client: Client) => dispatch(openClient(client.id));
  const openDepositPanel = (client?: Client, bonusOnly = false) => dispatch(openDeposit({ clientId: client?.id, bonusOnly }));
  const openSalePanel = (pc?: Workstation, product?: BackendProduct | null) => dispatch(openSale({ pcId: pc?.id, product }));
  const refreshAfterMutation = () => { void dispatch(refreshWorkspace()); };

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark"><Command size={19} strokeWidth={2.6} /></div><span>HUBSHELL</span><span className="brand-dot">·</span></div>
      <div className="club-select"><div className="club-avatar">H</div><div><strong>Главный клуб</strong><span>Операторская</span></div><ChevronDown size={15} className="muted" /></div>
      <div className="sidebar-label">Рабочее пространство</div>
      <nav>{navItems.map(({ id, label, icon: Icon }) => <button className={`nav-item ${ui.section === id ? "active" : ""}`} key={id} aria-current={ui.section === id ? "page" : undefined} onClick={() => dispatch(setSection(id))}><Icon size={18} /><span>{label}</span>{id === "bookings" && <span className="nav-count">{LIVE_MODE ? workspace.reservations.length : 4}</span>}</button>)}</nav>
      <div className="sidebar-spacer" /><div className="sidebar-label">Система</div>
      <button className={`nav-item ${ui.section === "settings" ? "active" : ""}`} aria-current={ui.section === "settings" ? "page" : undefined} onClick={() => dispatch(setSection("settings"))}><Settings size={18} /><span>Настройки</span></button>
      <button className="nav-item"><CircleHelp size={18} /><span>Помощь</span></button>
      <div className="operator-card"><div className="operator-avatar">AK</div><div><strong>Алексей К.</strong><span>Оператор</span></div><MoreHorizontal size={17} className="muted" /></div>
    </aside>
    <main className="main-content">
      <header className="topbar"><div className="breadcrumb"><span>HUBSHELL</span><ChevronRight size={14} /><strong>{navItems.find((item) => item.id === ui.section)?.label ?? (ui.section === "settings" ? "Настройки" : "")}</strong></div><div className="topbar-actions"><button className="topbar-quick-add" aria-label="Быстрое пополнение" onClick={() => openDepositPanel()}><Plus size={17} /></button><label className="global-search"><Search size={16} /><input aria-label="Быстрый поиск клиента" value={ui.search} onChange={(event) => dispatch(setSearch(event.target.value))} onKeyDown={(event) => { if (event.key === "Enter") dispatch(setSection("clients")); }} placeholder="Найти клиента" /></label><span className={`live-indicator ${workspace.error || workspace.reviewSales.length ? "warning" : ""}`}><i /> {workspace.error ? "Нет обновления" : workspace.reviewSales.length ? `Нужна проверка: ${workspace.reviewSales.length}` : LIVE_MODE ? "Связь стабильна" : "Демо-режим"}</span></div></header>
      <div className="content-wrap">
        {ui.section === "dashboard" && <Dashboard onDeposit={() => openDepositPanel()} onOpenCash={() => dispatch(setSection("cash"))} onOpenMap={() => dispatch(setSection("map"))} onOpenBookings={() => dispatch(setSection("bookings"))} onPc={openPcPanel} pcs={currentPcs} clients={currentClients} reservations={workspace.reservations} auditEvents={workspace.auditEvents} liveMode={LIVE_MODE} revenueCents={workspace.revenueCents} revenueChargeCount={workspace.revenueChargeCount} group={ui.group} setGroup={(value) => dispatch(setGroup(value))} zoneOptions={zoneOptions} />}
        {ui.section === "map" && <MapView onPc={openPcPanel} onSalePc={(pc) => openSalePanel(pc)} onBookPc={(id) => dispatch(openBooking(id))} onEditPc={(pc) => { dispatch(openPc(pc.id)); dispatch(openWorkstationEditor()); }} pcs={visiblePcs} group={ui.group} setGroup={(value: string) => dispatch(setGroup(value))} zoneOptions={zoneOptions} onNewWorkstation={LIVE_MODE ? () => dispatch(openNewWorkstation()) : undefined} onPositionsChange={LIVE_MODE ? async (changes) => { await dispatch(persistWorkstationPositions(changes)).unwrap(); refreshAfterMutation(); } : undefined} />}
        {ui.section === "bookings" && <BookingsView api={LIVE_MODE ? api : undefined} pcs={currentPcs} clients={currentClients} zoneOptions={zoneOptions} reservations={workspace.bookingReservations} bookingLoading={workspace.bookingLoading} bookingError={workspace.bookingError} onNewBooking={() => dispatch(openBooking(undefined))} onEditBooking={(reservation) => dispatch(openBookingEdit(reservation))} refreshKey={ui.bookingRefreshKey} />}
        {ui.section === "clients" && <ClientsView search={ui.search} setSearch={(value) => dispatch(setSearch(value))} onDeposit={() => openDepositPanel()} onNewClient={LIVE_MODE ? () => dispatch(openNewClient()) : undefined} onClient={openClientPanel} clients={currentClients} api={LIVE_MODE ? api : undefined} />}
        {ui.section === "catalog" && <CatalogView api={LIVE_MODE ? api : undefined} groups={workspace.groups} tariffs={workspace.tariffs} discountRules={workspace.discountRules} products={workspace.products} categories={workspace.productCategories} onRefresh={refreshAfterMutation} onNewTariff={LIVE_MODE ? () => dispatch(openPanel("tariff")) : undefined} onNewProduct={LIVE_MODE ? () => { dispatch(selectProduct(null)); dispatch(openPanel("product")); } : undefined} onEditProduct={LIVE_MODE ? (product) => { dispatch(selectProduct(product)); } : undefined} onSellProduct={LIVE_MODE ? (product) => openSalePanel(undefined, product) : undefined} onNewDiscount={LIVE_MODE ? () => dispatch(openPanel("discount")) : undefined} />}
        {ui.section === "analytics" && <AnalyticsView api={LIVE_MODE ? api : undefined} clients={currentClients} onClient={openClientPanel} />}
        {ui.section === "cash" && <CashView api={LIVE_MODE ? api : undefined} shifts={workspace.cashShifts} cashShiftSchedules={workspace.cashShiftSchedules} cashMovements={workspace.cashMovements} onRefresh={refreshAfterMutation} onOpenShift={LIVE_MODE ? () => dispatch(openPanel("cash-open")) : undefined} onRecordMovement={LIVE_MODE ? (shift) => dispatch(openCashMovement(shift)) : undefined} onCloseShift={LIVE_MODE ? (shift) => dispatch(openCashClose(shift)) : undefined} />}
        {ui.section === "settings" && <SettingsView api={LIVE_MODE ? api : undefined} pcs={currentPcs} groups={workspace.groups} paymentMethods={workspace.paymentMethods} error={workspace.error} onNewGroup={LIVE_MODE ? () => dispatch(selectGroup(null)) : undefined} onEditGroup={LIVE_MODE ? (group) => dispatch(selectGroup(group)) : undefined} onNewPaymentMethod={LIVE_MODE ? () => dispatch(selectPaymentMethod(null)) : undefined} onEditPaymentMethod={LIVE_MODE ? (method) => dispatch(selectPaymentMethod(method)) : undefined} />}
      </div>
    </main>
    <PanelHost />
  </div>;
}
