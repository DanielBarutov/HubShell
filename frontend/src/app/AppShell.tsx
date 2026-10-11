import { useEffect } from "react";
import {
  Bell,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
} from "lucide-react";
import { useAppDispatch, useAppSelector } from "./hooks";
import { useReduxApi } from "./reduxApi";
import { LIVE_MODE } from "./config";
import { selectAuth } from "../features/auth/authSlice";
import {
  refreshWorkspace,
  persistWorkstationPositions,
  selectWorkspace,
} from "../features/workspace/workspaceSlice";
import {
  openBooking,
  openBookingEdit,
  openCashClose,
  openCashMovement,
  openClient,
  openDeposit,
  openNewClient,
  openNewWorkstation,
  openPanel,
  openPc,
  openSale,
  openWorkstationEditor,
  closePanel,
  selectGroup,
  selectPaymentMethod,
  selectProduct,
  setGroup,
  setSearch,
  setSection,
  selectUi,
} from "../features/workspace/uiSlice";
import { navItems } from "../shared/constants";
import {
  AnalyticsView,
  Dashboard,
} from "../features/dashboard/DashboardScreen";
import { BookingsView } from "../features/bookings/BookingsScreen";
import { ClientsView } from "../features/clients/ClientsScreen";
import { CatalogView } from "../features/catalog/CatalogScreen";
import { CashView } from "../features/cash/CashScreen";
import { SettingsView } from "../features/settings/SettingsScreen";
import { MapView } from "../features/workstations/MapScreen";
import { PanelHost } from "./PanelHost";
import type { Client, Section, Workstation } from "../types";
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
      void dispatch(refreshWorkspace()).finally(() => {
        inFlight = false;
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 5_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [auth.isAuthenticated, dispatch]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [ui.section]);

  if (LIVE_MODE && (!auth.isAuthenticated || auth.isRestoring))
    return <LoginScreen />;
  if (LIVE_MODE && workspace.loading && !workspace.lastUpdatedAt)
    return (
      <div className="app-shell relative min-h-screen overflow-x-hidden bg-base-100! text-base-content!">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-[28rem] bg-[linear-gradient(180deg,rgba(4,20,20,0.18),var(--color-base-100)_92%),url('/neon-club-room.png')] bg-cover bg-top bg-no-repeat opacity-70" />
        <main className="main-content relative z-10 min-w-0 flex-1">
          <div className="content-wrap p-6">
            <div
              className="card border border-primary/20! bg-base-200/55! p-6 text-base-content! shadow-[0_14px_38px_rgba(0,0,0,0.2)] backdrop-blur-md"
              role="status"
            >
              Загружаем игровые места…
            </div>
          </div>
        </main>
      </div>
    );

  const currentPcs = workspace.workstations;
  const currentClients = workspace.clients;
  const zoneOptions = [
    "Все зоны",
    ...Array.from(new Set(currentPcs.map((pc) => pc.group).filter(Boolean))),
  ];
  const compactShell = ui.section === "catalog" || ui.section === "analytics";
  const mediumShell =
    !compactShell && ui.section !== "dashboard" && ui.section !== "clients";
  const useRoomBackdrop = true;
  const openPcPanel = (pc: Workstation) => dispatch(openPc(pc.id));
  const openClientPanel = (client: Client) => dispatch(openClient(client.id));
  const openDepositPanel = (client?: Client, bonusOnly = false) =>
    dispatch(openDeposit({ clientId: client?.id, bonusOnly }));
  const openSalePanel = (pc?: Workstation, product?: BackendProduct | null) =>
    dispatch(openSale({ pcId: pc?.id, clientId: pc?.clientId, product }));
  const refreshAfterMutation = () => {
    void dispatch(refreshWorkspace());
  };
  const navigate = (section: Section) => {
    dispatch(closePanel());
    dispatch(setSection(section));
  };

  return (
    <div className="app-shell relative flex min-h-screen overflow-x-hidden bg-base-100! text-base-content!">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_74%_8%,rgba(49,217,120,0.08),transparent_24%),linear-gradient(180deg,var(--color-base-200),var(--color-base-100)_82%)]" />
      <div
        className={`pointer-events-none absolute inset-x-0 top-0 h-[18rem] bg-no-repeat opacity-70 mix-blend-screen ${useRoomBackdrop ? "bg-[linear-gradient(90deg,rgba(4,18,20,.78)_0%,rgba(4,18,20,0.54)_24%,rgba(4,18,20,0.18)_60%,rgba(4,18,20,0.42)_100%),url('/neon-club-room.png')] bg-cover bg-top" : "bg-[radial-gradient(ellipse_at_72%_8%,rgba(49,217,120,.14),transparent_34%),linear-gradient(180deg,rgba(18,52,60,.45),transparent 70%)]"}`}
      />
      <aside
        className={`sidebar sticky top-0 z-10 isolate flex h-screen shrink-0 flex-col overflow-x-hidden overflow-y-auto border-r border-primary/15! bg-no-repeat text-neutral-content! backdrop-blur-xl ${useRoomBackdrop ? "bg-[linear-gradient(180deg,rgba(6,28,32,.68),rgba(6,28,32,.28) 64%,rgba(6,28,32,.12)),url('/neon-club-room.png')] bg-cover bg-right" : "bg-[linear-gradient(180deg,rgba(6,28,32,.78),rgba(6,28,32,.42) 64%,rgba(6,28,32,.2)),radial-gradient(ellipse_at_18%_78%,rgba(49,217,120,.22),transparent 50%)] w-52 p-3"}`}
        aria-label="Основная навигация"
      >
        <div
          className={`pointer-events-none absolute inset-x-0 bottom-0 top-1/3 z-0 bg-[url('/neon-club-room.png')] bg-cover bg-no-repeat mix-blend-screen ${useRoomBackdrop ? "bg-right opacity-45" : "bg-left-bottom opacity-20"}`}
        />
        <div className="pointer-events-none absolute inset-0 z-0 bg-[linear-gradient(180deg,rgba(4,20,24,.24),rgba(4,20,24,.54)_54%,rgba(4,20,24,.78)),radial-gradient(ellipse_at_18%_78%,rgba(49,217,120,.22),transparent_50%)]" />
        <div className="relative z-10 flex min-h-full flex-col">
          <div className="brand flex items-center gap-2 px-1 mt-5 mr-2 ml-2 pb-6 text-2xl font-extrabold tracking-wide text-neutral-content!">
            <div className="brand-mark grid h-11 w-11 shrink-0 place-items-center text-primary!">
              <span className="relative block h-8 w-8" aria-hidden="true">
                <i className="absolute left-0 top-0 h-4 w-4 rounded-full border-[3px] border-primary" />
                <i className="absolute right-0 top-0 h-4 w-4 rounded-full border-[3px] border-primary" />
                <i className="absolute bottom-0 left-0 h-4 w-4 rounded-full border-[3px] border-primary" />
                <i className="absolute bottom-0 right-0 h-4 w-4 rounded-full border-[3px] border-primary" />
                <i className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary" />
              </span>
            </div>
            <div className="min-w-0 leading-none">
              <span className="block">HUBSHELL</span>
              <small className="mt-1 block text-[9px] font-semibold tracking-[0.16em] text-base-content/55!">
                GAME-CLUB · ПАНЕЛЬ
              </small>
            </div>
          </div>

          <div className="sidebar-label px-2 pb-2 text-[10px] font-bold uppercase tracking-widest text-base-content/50!">
            {ui.section === "map" ? "Разделы" : "Разделы"}
          </div>
          <nav
            className="menu menu-vertical w-full gap-1 p-0"
            aria-label="Разделы"
          >
            <ul className="m-0 w-full p-0">
              {navItems.map(({ id, label, icon: Icon }) => (
                <li key={id}>
                  <button
                    className={`nav-item btn mt-1 mr-2 ml-2 btn-md min-h-9 justify-start font-semibold text-xs ${ui.section === id ? "current border-primary! bg-primary! font-extrabold text-primary-content! opacity-100 hover:bg-primary! hover:text-primary-content!" : "btn-ghost border-transparent! bg-transparent! text-base-content/90! hover:bg-base-300/40! hover:text-base-content!"}`}
                    aria-current={ui.section === id ? "page" : undefined}
                    onClick={() => navigate(id)}
                  >
                    <Icon
                      size={20}
                      className={
                        ui.section === id ? "text-primary-content!" : undefined
                      }
                    />
                    <span
                      className={`grow whitespace-nowrap text-left ${ui.section === id ? "text-primary-content!" : ""}`}
                    >
                      {label}
                    </span>
                    {id === "bookings" && (
                      <span className="nav-count badge badge-primary badge-sm">
                        {LIVE_MODE ? workspace.reservations.length : 0}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
          <div className="sidebar-spacer min-h-24 grow" />
          <div className="sidebar-label px-2 pb-2 text-[10px] font-bold uppercase tracking-widest text-base-content/50!">
            Система
          </div>
          <nav
            className="menu menu-vertical w-full gap-1 p-0"
            aria-label="Система"
          >
            <ul className="m-0 w-full p-0">
              <li>
                <button
                  className={`nav-item btn mt-1 mr-2 ml-2 btn-md min-h-9 justify-start font-semibold text-sm ${ui.section === "settings" ? "current border-primary! bg-primary! font-extrabold text-primary-content! opacity-100 hover:bg-primary! hover:text-primary-content!" : "btn-ghost border-transparent! bg-transparent! text-base-content/90! hover:bg-base-300/40! hover:text-base-content!"}`}
                  aria-current={ui.section === "settings" ? "page" : undefined}
                  onClick={() => navigate("settings")}
                >
                  <Settings
                    size={18}
                    className={
                      ui.section === "settings"
                        ? "text-primary-content!"
                        : undefined
                    }
                  />
                  <span
                    className={`grow whitespace-nowrap text-left ${ui.section === "settings" ? "text-primary-content!" : ""}`}
                  >
                    Настройки
                  </span>
                </button>
              </li>
              <li>
                <button className="nav-item btn mt-1 mr-2 ml-2 btn-md min-h-9 !border-transparent bg-transparent! justify-start text-sm text-base-content/90! hover:bg-base-300/70! hover:text-base-content!">
                  <CircleHelp size={18} />
                  <span className="grow text-left">Помощь</span>
                </button>
              </li>
            </ul>
          </nav>
          <div className="operator-card mt-3 flex items-center gap-2 rounded-xl border border-primary/15! bg-base-100/35! p-3 shadow-[inset_0_0_18px_rgba(49,217,120,0.04)]">
            <div className="operator-avatar grid h-9 w-9 shrink-0 place-items-center rounded-full bg-secondary! text-xs font-bold text-secondary-content!">
              AK
            </div>
            <div className="min-w-0 grow">
              <strong className="block truncate text-xs text-base-content!">
                Админский
              </strong>
              <span className="block text-[11px] text-base-content/60!">
                Админ
              </span>
            </div>
            <MoreHorizontal size={17} className="text-base-content/60!" />
          </div>
        </div>
      </aside>
      <main className="main-content relative z-10 min-w-0 flex-1 overflow-x-hidden text-base-content!">
        <header
          className={`topbar navbar flex min-h-0! items-center justify-between border-b border-primary/15! bg-base-100/65! px-8 backdrop-blur-xl ${compactShell ? "h-16" : "h-16"}`}
        >
          <div className="breadcrumb navbar-start flex items-center gap-2 text-xs text-base-content/60!">
            <span>HUBSHELL</span>
            <ChevronRight size={14} />
            <strong className="text-base-content!">
              {navItems.find((item) => item.id === ui.section)?.label ??
                (ui.section === "settings" ? "Настройки" : "")}
            </strong>
          </div>
          <div className="topbar-actions navbar-end flex min-w-0 items-center gap-2">
            <button
              className="topbar-quick-add btn btn-outline btn-square btn-sm border-primary/40! text-primary!"
              aria-label="Пополнить депозит"
              onClick={() => openDepositPanel()}
            >
              <Plus size={17} />
            </button>
            <label className="global-search input input-sm flex w-56 items-center gap-2 border-primary/20! bg-base-200/75! text-base-content!">
              <Search size={16} />
              <input
                className="grow bg-transparent text-sm outline-none"
                aria-label="Найти клиента"
                value={ui.search}
                onChange={(event) => dispatch(setSearch(event.target.value))}
                onKeyDown={(event) => {
                  if (event.key === "Enter") dispatch(setSection("clients"));
                }}
                placeholder="Найти клиента"
              />
              <kbd className="kbd kbd-xs hidden border-primary/20! bg-base-100/50! text-base-content/55! lg:inline-flex">
                ⌘ K
              </kbd>
            </label>
            <span
              className={`live-indicator badge badge-sm gap-1 border-0! bg-transparent! text-primary! ${workspace.error || workspace.reviewSales.length ? "text-warning!" : ""}`}
            >
              <i className="h-1.5 w-1.5 rounded-full bg-current" />{" "}
              {workspace.error
                ? "Нет связи с сервером"
                : workspace.reviewSales.length
                  ? `Нужна проверка: ${workspace.reviewSales.length}`
                  : LIVE_MODE
                    ? "Сервер подключён"
                    : "Тестовый режим"}
            </span>
            <button
              className="btn btn-ghost btn-square btn-sm border border-primary/20! text-base-content/70!"
              aria-label="Уведомления"
            >
              <Bell size={17} />
            </button>
          </div>
        </header>
        <div
          className={`content-wrap pr-6 pb-6 pt-0 ${compactShell ? "pl-7" : mediumShell ? "pl-6" : "pl-8"}`}
        >
          {ui.section === "dashboard" && (
            <Dashboard
              onDeposit={() => openDepositPanel()}
              onOpenCash={() => dispatch(setSection("cash"))}
              onOpenMap={() => dispatch(setSection("map"))}
              onOpenBookings={() => dispatch(setSection("bookings"))}
              onPc={openPcPanel}
              pcs={currentPcs}
              clients={currentClients}
              reservations={workspace.reservations}
              auditEvents={workspace.auditEvents}
              liveMode={LIVE_MODE}
              revenueCents={workspace.revenueCents}
              revenueChargeCount={workspace.revenueChargeCount}
              group={ui.group}
              setGroup={(value) => dispatch(setGroup(value))}
              zoneOptions={zoneOptions}
            />
          )}
          {ui.section === "map" && (
            <MapView
              onPc={openPcPanel}
              onSalePc={(pc) => openSalePanel(pc)}
              onSellProduct={() =>
                dispatch(openSale({ initialTab: "products" }))
              }
              onBookPc={(id) => dispatch(openBooking(id))}
              onEditPc={(pc) => {
                dispatch(openPc(pc.id));
                dispatch(openWorkstationEditor());
              }}
              pcs={currentPcs}
              onNewWorkstation={
                LIVE_MODE ? () => dispatch(openNewWorkstation()) : undefined
              }
              onPositionsChange={
                LIVE_MODE
                  ? async (changes) => {
                      await dispatch(
                        persistWorkstationPositions(changes),
                      ).unwrap();
                      refreshAfterMutation();
                    }
                  : undefined
              }
            />
          )}
          {ui.section === "bookings" && (
            <BookingsView
              api={LIVE_MODE ? api : undefined}
              pcs={currentPcs}
              clients={currentClients}
              zoneOptions={zoneOptions}
              reservations={workspace.bookingReservations}
              bookingLoading={workspace.bookingLoading}
              bookingError={workspace.bookingError}
              onNewBooking={() => dispatch(openBooking(undefined))}
              onEditBooking={(reservation) =>
                dispatch(openBookingEdit(reservation))
              }
              refreshKey={ui.bookingRefreshKey}
            />
          )}
          {ui.section === "clients" && (
            <ClientsView
              search={ui.search}
              setSearch={(value) => dispatch(setSearch(value))}
              onDeposit={() => openDepositPanel()}
              onNewClient={
                LIVE_MODE ? () => dispatch(openNewClient()) : undefined
              }
              onClient={openClientPanel}
              clients={currentClients}
              api={LIVE_MODE ? api : undefined}
            />
          )}
          {ui.section === "catalog" && (
            <CatalogView
              api={LIVE_MODE ? api : undefined}
              groups={workspace.groups}
              tariffs={workspace.tariffs}
              discountRules={workspace.discountRules}
              products={workspace.products}
              categories={workspace.productCategories}
              onRefresh={refreshAfterMutation}
              onNewTariff={
                LIVE_MODE ? () => dispatch(openPanel("tariff")) : undefined
              }
              onNewProduct={
                LIVE_MODE
                  ? () => {
                      dispatch(selectProduct(null));
                      dispatch(openPanel("product"));
                    }
                  : undefined
              }
              onEditProduct={
                LIVE_MODE
                  ? (product) => {
                      dispatch(selectProduct(product));
                    }
                  : undefined
              }
              onSellProduct={
                LIVE_MODE
                  ? (product) => openSalePanel(undefined, product)
                  : undefined
              }
              onNewDiscount={
                LIVE_MODE ? () => dispatch(openPanel("discount")) : undefined
              }
            />
          )}
          {ui.section === "analytics" && (
            <AnalyticsView
              api={LIVE_MODE ? api : undefined}
              clients={currentClients}
              onClient={openClientPanel}
              workstations={currentPcs}
              groups={workspace.groups}
              tariffs={workspace.tariffs}
              clientGroups={workspace.clientGroups}
              paymentMethods={workspace.paymentMethods}
              productCategories={workspace.productCategories}
              products={workspace.products}
            />
          )}
          {ui.section === "cash" && (
            <CashView
              api={LIVE_MODE ? api : undefined}
              shifts={workspace.cashShifts}
              cashShiftSchedules={workspace.cashShiftSchedules}
              cashMovements={workspace.cashMovements}
              onRefresh={refreshAfterMutation}
              onOpenShift={
                LIVE_MODE ? () => dispatch(openPanel("cash-open")) : undefined
              }
              onRecordMovement={
                LIVE_MODE
                  ? (shift) => dispatch(openCashMovement(shift))
                  : undefined
              }
              onCloseShift={
                LIVE_MODE
                  ? (shift) => dispatch(openCashClose(shift))
                  : undefined
              }
            />
          )}
          {ui.section === "settings" && (
            <SettingsView
              api={LIVE_MODE ? api : undefined}
              pcs={currentPcs}
              groups={workspace.groups}
              paymentMethods={workspace.paymentMethods}
              clientGroups={workspace.clientGroups}
              notificationRules={workspace.notificationRules}
              error={workspace.error}
              onRefresh={refreshAfterMutation}
              onNewGroup={
                LIVE_MODE ? () => dispatch(selectGroup(null)) : undefined
              }
              onEditGroup={
                LIVE_MODE ? (group) => dispatch(selectGroup(group)) : undefined
              }
              onNewPaymentMethod={
                LIVE_MODE
                  ? () => dispatch(selectPaymentMethod(null))
                  : undefined
              }
              onEditPaymentMethod={
                LIVE_MODE
                  ? (method) => dispatch(selectPaymentMethod(method))
                  : undefined
              }
            />
          )}
        </div>
      </main>
      <PanelHost />
    </div>
  );
}
