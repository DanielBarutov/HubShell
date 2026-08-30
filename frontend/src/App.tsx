import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  BarChart3,
  Banknote,
  CalendarDays,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Command,
  Computer,
  CreditCard,
  Download,
  Edit3,
  Gamepad2,
  LayoutDashboard,
  LayoutGrid,
  Minus,
  MoreHorizontal,
  PanelRightClose,
  Plus,
  Play,
  Receipt,
  Search,
  ShoppingCart,
  Settings,
  ShieldCheck,
  Sparkles,
  Tags,
  TrendingUp,
  UserRound,
  Users,
  WalletCards,
  Wifi,
  X,
  UserX,
} from "lucide-react";
import { bookings, clients, workstations } from "./data";
import { ApiError, GameClubApi, normalizePhoneQuery } from "./api";
import type {
  BackendAuditEvent,
  BackendBalanceOperation,
  BackendCashMovement,
  BackendCashShift,
  BackendCashShiftSchedule,
  BackendClientAnalytics,
  BackendAnalyticsOverview,
  BackendLockdownPolicy,
  BackendPaymentMethod,
  BackendProduct,
  BackendProductCategory,
  BackendTariff,
  BackendSessionMeter,
  BackendWorkstationGroup,
  Reservation,
} from "./api";
import { toUiClient, toUiWorkstation } from "./adapters";
import type { Client, PcStatus, Section, Workstation } from "./types";

const LIVE_MODE = import.meta.env.VITE_GAMECLUB_DATA_MODE !== "mock";

const navItems: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "Дашборд", icon: LayoutDashboard },
  { id: "map", label: "Карта мест", icon: LayoutGrid },
  { id: "bookings", label: "Бронирования", icon: CalendarDays },
  { id: "clients", label: "Клиенты", icon: Users },
  { id: "catalog", label: "Каталог и тарифы", icon: WalletCards },
  { id: "analytics", label: "Аналитика", icon: BarChart3 },
  { id: "cash", label: "Касса", icon: Banknote },
];

const statusMeta: Record<PcStatus, { label: string; className: string }> = {
  online: { label: "Свободен", className: "status-online" },
  busy: { label: "Занят", className: "status-busy" },
  offline: { label: "Не в сети", className: "status-offline" },
  maintenance: { label: "Сервис", className: "status-maintenance" },
};

function getSearchField(value: string): "nickname" | "phone" | null {
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }
  const digits = normalized.replace(/\D/g, "");
  const phoneLike = /^[+\d\s()-]+$/.test(normalized);
  if (phoneLike) {
    return digits.length >= 4 ? "phone" : null;
  }
  return normalized.length >= 3 ? "nickname" : null;
}

function formatRussianPhone(value: string): string {
  let digits = value.replace(/\D/g, "").slice(0, 11);
  if (digits.startsWith("8")) {
    digits = `7${digits.slice(1)}`;
  }
  if (digits.length === 10 && !digits.startsWith("7")) {
    digits = `7${digits}`;
  }
  if (digits.startsWith("7")) {
    const local = digits.slice(1);
    if (!local) return "+7";
    if (local.length <= 3) return `+7 (${local}`;
    if (local.length <= 6) return `+7 (${local.slice(0, 3)}) ${local.slice(3)}`;
    if (local.length <= 8) return `+7 (${local.slice(0, 3)}) ${local.slice(3, 6)}-${local.slice(6)}`;
    return `+7 (${local.slice(0, 3)}) ${local.slice(3, 6)}-${local.slice(6, 8)}-${local.slice(8)}`;
  }
  return digits ? `+${digits}` : "";
}

function App() {
  const api = useMemo(() => new GameClubApi(), []);
  const [isAuthenticated, setIsAuthenticated] = useState(!LIVE_MODE);
  const [isRestoringSession, setIsRestoringSession] = useState(LIVE_MODE);
  const [livePcs, setLivePcs] = useState<Workstation[]>(workstations);
  const [liveGroups, setLiveGroups] = useState<BackendWorkstationGroup[]>([]);
  const [liveClients, setLiveClients] = useState<Client[]>([]);
  const [liveReservations, setLiveReservations] = useState<Reservation[]>([]);
  const [liveAuditEvents, setLiveAuditEvents] = useState<BackendAuditEvent[]>([]);
  const [liveRevenueCents, setLiveRevenueCents] = useState<number | null>(null);
  const [liveRevenueChargeCount, setLiveRevenueChargeCount] = useState(0);
  const [liveCashShifts, setLiveCashShifts] = useState<BackendCashShift[]>([]);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [bookingRefreshKey, setBookingRefreshKey] = useState(0);
  const [liveRefreshKey, setLiveRefreshKey] = useState(0);
  const [section, setSection] = useState<Section>("dashboard");
  const [group, setGroup] = useState("Все зоны");
  const [selectedPc, setSelectedPc] = useState<Workstation | null>(null);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<BackendWorkstationGroup | undefined>();
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<BackendPaymentMethod | undefined>();
  const [selectedBooking, setSelectedBooking] = useState<Reservation | null>(null);
  const [selectedCashShift, setSelectedCashShift] = useState<BackendCashShift | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<BackendProduct | null>(null);
  const [saleInitialProduct, setSaleInitialProduct] = useState<BackendProduct | null>(null);
  const [panel, setPanel] = useState<"pc" | "client" | "new-client" | "deposit" | "booking" | "booking-edit" | "tariff" | "product" | "sale" | "discount" | "workstation" | "group" | "payment-method" | "cash-open" | "cash-movement" | "cash-close" | null>(null);
  const [bookingWorkstationId, setBookingWorkstationId] = useState<string | undefined>();
  const [depositBonusOnly, setDepositBonusOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [catalogRefreshKey, setCatalogRefreshKey] = useState(0);
  const [settingsRefreshKey, setSettingsRefreshKey] = useState(0);

  useEffect(() => {
    if (!LIVE_MODE) {
      return undefined;
    }
    let active = true;
    void api.restoreSession().then((restored) => {
      if (active && restored) {
        setIsAuthenticated(true);
      }
    }).finally(() => {
      if (active) {
        setIsRestoringSession(false);
      }
    });
    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => {
    if (!panel) {
      return undefined;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPanel(null);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [panel]);

  useEffect(() => {
    if (!LIVE_MODE || !isAuthenticated) {
      return undefined;
    }
    let active = true;
    const refresh = async () => {
      try {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const [backendPcs, backendClients, activeSessions, todayReservations, auditEvents, revenue, cashShifts, backendGroups] = await Promise.all([
          api.listWorkstations(),
          api.listClients(),
          api.listSessions(true),
          api.listReservations(today.toISOString(), tomorrow.toISOString()),
          api.listAuditEvents(),
          api.getRevenue(today.toISOString(), tomorrow.toISOString()),
          api.listCashShifts(),
          api.listWorkstationGroups(),
        ]);
        if (!active) {
          return;
        }
        const sessionsByWorkstation = new Map(
          activeSessions.map((session) => [session.workstation_id, session]),
        );
        const groupNames = new Map(backendGroups.map((group) => [group.id, group.name]));
        const clientNames = new Map(backendClients.map((client) => [client.id, client.nickname]));
        setLiveGroups(backendGroups);
        setLivePcs(backendPcs.map((pc) => {
          const session = sessionsByWorkstation.get(pc.id);
          return toUiWorkstation(pc, session, pc.group_id ? groupNames.get(pc.group_id) : undefined, session?.client_id ? clientNames.get(session.client_id) : undefined);
        }));
        setLiveClients(backendClients.map(toUiClient));
        setLiveReservations(todayReservations);
        setLiveAuditEvents(auditEvents);
        setLiveRevenueCents(revenue.amount_cents);
        setLiveRevenueChargeCount(revenue.charge_count);
        setLiveCashShifts(cashShifts);
        setLiveError(null);
      } catch (error) {
        if (active) {
          setLiveError(error instanceof ApiError ? error.message : "Не удалось обновить данные");
        }
      }
    };
    void refresh();
    const timer = window.setInterval(() => void refresh(), 20_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, isAuthenticated, liveRefreshKey]);

  const currentPcs = LIVE_MODE ? livePcs : workstations;
  const currentClients = LIVE_MODE ? liveClients : clients;
  const currentReservations = LIVE_MODE ? liveReservations : [];
  const zoneOptions = useMemo(
    () => ["Все зоны", ...Array.from(new Set(currentPcs.map((pc) => pc.group).filter(Boolean)))],
    [currentPcs],
  );

  useEffect(() => {
    if (!zoneOptions.includes(group)) {
      setGroup("Все зоны");
    }
  }, [group, zoneOptions]);
  const visiblePcs = useMemo(
    () => currentPcs.filter((pc) => group === "Все зоны" || pc.group === group),
    [currentPcs, group],
  );

  if (LIVE_MODE && (!isAuthenticated || isRestoringSession)) {
    return <LoginView api={api} onAuthenticated={() => setIsAuthenticated(true)} restoring={isRestoringSession} />;
  }
  const openPc = (pc: Workstation) => {
    setSelectedPc(pc);
    setSelectedClient(null);
    setPanel("pc");
  };
  const openClient = (client: Client) => {
    setSelectedClient(client);
    setSelectedPc(null);
    setSelectedBooking(null);
    setPanel("client");
  };
  const openNewClient = () => {
    setSelectedClient(null);
    setSelectedPc(null);
    setSelectedBooking(null);
    setPanel("new-client");
  };
  const openDeposit = (client?: Client, bonusOnly = false) => {
    setPanel("deposit");
    setSelectedPc(null);
    setSelectedClient(client ?? null);
    setDepositBonusOnly(bonusOnly);
  };
  const openBooking = (workstationId?: string) => {
    setPanel("booking");
    setSelectedPc(null);
    setSelectedClient(null);
    setSelectedBooking(null);
    setBookingWorkstationId(workstationId);
  };
  const openSale = (pc?: Workstation, initialProduct?: BackendProduct) => {
    setSelectedPc(pc ?? null);
    setSelectedClient(null);
    setSaleInitialProduct(initialProduct ?? null);
    setPanel("sale");
  };
  const openProductSale = (product: BackendProduct) => openSale(undefined, product);
  const saveWorkstationPositions = async (changes: Array<{ workstationId: string; position: number }>) => {
    if (!LIVE_MODE || !changes.length) {
      return;
    }
    const currentById = new Map(livePcs.map((pc) => [pc.id, pc]));
    const validChanges = changes.filter(
      (change) => currentById.has(change.workstationId) && Number.isInteger(change.position) && change.position > 0,
    );
    if (!validChanges.length) {
      return;
    }
    const positionById = new Map(validChanges.map((change) => [change.workstationId, change.position]));
    const previousPcs = livePcs;
    setLivePcs((items) => items.map((pc) => {
      const position = positionById.get(pc.id);
      return position === undefined ? pc : { ...pc, position };
    }));
    try {
      await Promise.all(validChanges.map((change) => {
        const pc = currentById.get(change.workstationId);
        if (!pc) {
          return Promise.resolve();
        }
        return api.updateWorkstation(pc.id, {
          name: pc.name,
          group_id: pc.groupId ?? null,
          position: change.position,
        });
      }));
      setLiveRefreshKey((value) => value + 1);
    } catch (error) {
      setLivePcs(previousPcs);
      setLiveError(error instanceof ApiError ? error.message : "Не удалось сохранить расстановку мест");
      throw error;
    }
  };
  const openBookingEdit = (reservation: Reservation) => {
    setPanel("booking-edit");
    setSelectedPc(null);
    setSelectedClient(null);
    setSelectedBooking(reservation);
  };
  const openCashShiftPanel = () => {
    setSelectedCashShift(null);
    setPanel("cash-open");
  };
  const openCashMovementPanel = (shift: BackendCashShift) => {
    setSelectedCashShift(shift);
    setPanel("cash-movement");
  };
  const openCashClosePanel = (shift: BackendCashShift) => {
    setSelectedCashShift(shift);
    setPanel("cash-close");
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Command size={19} strokeWidth={2.6} /></div>
          <span>gameshell</span>
          <span className="brand-dot">·</span>
        </div>
        <div className="club-select">
          <div className="club-avatar">G</div>
          <div><strong>GameClub Alpha</strong><span>Главный клуб</span></div>
          <ChevronDown size={15} className="muted" />
        </div>
        <div className="sidebar-label">Рабочее пространство</div>
        <nav>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button className={`nav-item ${section === id ? "active" : ""}`} key={id} aria-current={section === id ? "page" : undefined} onClick={() => setSection(id)}>
              <Icon size={18} /> <span>{label}</span>
              {id === "bookings" && <span className="nav-count">{LIVE_MODE ? liveReservations.length : 4}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-label">Система</div>
        <button className={`nav-item ${section === "settings" ? "active" : ""}`} aria-current={section === "settings" ? "page" : undefined} onClick={() => setSection("settings")}><Settings size={18} /><span>Настройки</span></button>
        <button className="nav-item"><CircleHelp size={18} /><span>Помощь</span></button>
        <div className="operator-card">
          <div className="operator-avatar">AK</div>
          <div><strong>Алексей К.</strong><span>Оператор</span></div>
          <MoreHorizontal size={17} className="muted" />
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb"><span>GameClub Alpha</span><ChevronRight size={14} /><strong>{navItems.find((item) => item.id === section)?.label ?? (section === "settings" ? "Настройки" : "")}</strong></div>
          <div className="topbar-actions">
            <button className="topbar-quick-add" aria-label="Быстрое пополнение" onClick={() => openDeposit()}><Plus size={17} /></button>
            <label className="global-search"><Search size={16} /><input aria-label="Быстрый поиск клиента" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") setSection("clients"); }} placeholder="Найти клиента" /></label>
            <span className={`live-indicator ${liveError ? "warning" : ""}`}><i /> {liveError ? "Нет обновления" : LIVE_MODE ? "Система подключена" : "Система работает"}</span>
          </div>
        </header>

        <div className="content-wrap">
          {section === "dashboard" && <Dashboard onDeposit={openDeposit} onOpenCash={() => setSection("cash")} onOpenMap={() => setSection("map")} onOpenBookings={() => setSection("bookings")} onPc={openPc} pcs={currentPcs} clients={currentClients} reservations={currentReservations} auditEvents={liveAuditEvents} liveMode={LIVE_MODE} revenueCents={liveRevenueCents} revenueChargeCount={liveRevenueChargeCount} group={group} setGroup={setGroup} zoneOptions={zoneOptions} />}
          {section === "map" && <MapView onPc={openPc} onSalePc={openSale} onBookPc={openBooking} onEditPc={(pc) => { setSelectedPc(pc); setPanel("workstation"); }} pcs={visiblePcs} group={group} setGroup={setGroup} zoneOptions={zoneOptions} onNewWorkstation={LIVE_MODE ? () => setPanel("workstation") : undefined} onPositionsChange={LIVE_MODE ? saveWorkstationPositions : undefined} />}
          {section === "bookings" && <BookingsView api={LIVE_MODE ? api : undefined} pcs={currentPcs} clients={currentClients} zoneOptions={zoneOptions} onNewBooking={() => openBooking()} onEditBooking={openBookingEdit} refreshKey={bookingRefreshKey} />}
          {section === "clients" && <ClientsView search={search} setSearch={setSearch} onDeposit={() => openDeposit()} onNewClient={LIVE_MODE ? openNewClient : undefined} onClient={openClient} clients={currentClients} api={LIVE_MODE ? api : undefined} />}
          {section === "catalog" && <CatalogView api={LIVE_MODE ? api : undefined} groups={liveGroups} refreshKey={catalogRefreshKey} onNewTariff={LIVE_MODE ? () => setPanel("tariff") : undefined} onNewProduct={LIVE_MODE ? () => { setSelectedProduct(null); setPanel("product"); } : undefined} onEditProduct={LIVE_MODE ? (product) => { setSelectedProduct(product); setPanel("product"); } : undefined} onSellProduct={LIVE_MODE ? openProductSale : undefined} onNewDiscount={LIVE_MODE ? () => setPanel("discount") : undefined} />}
          {section === "analytics" && <AnalyticsView api={LIVE_MODE ? api : undefined} clients={currentClients} onClient={openClient} />}
          {section === "cash" && <CashView api={LIVE_MODE ? api : undefined} shifts={liveCashShifts} onOpenShift={LIVE_MODE ? openCashShiftPanel : undefined} onRecordMovement={LIVE_MODE ? openCashMovementPanel : undefined} onCloseShift={LIVE_MODE ? openCashClosePanel : undefined} />}
          {section === "settings" && <SettingsView api={LIVE_MODE ? api : undefined} pcs={currentPcs} refreshKey={settingsRefreshKey} onNewGroup={LIVE_MODE ? () => { setSelectedGroup(undefined); setPanel("group"); } : undefined} onEditGroup={LIVE_MODE ? (group) => { setSelectedGroup(group); setPanel("group"); } : undefined} onNewPaymentMethod={LIVE_MODE ? () => { setSelectedPaymentMethod(undefined); setPanel("payment-method"); } : undefined} onEditPaymentMethod={LIVE_MODE ? (method) => { setSelectedPaymentMethod(method); setPanel("payment-method"); } : undefined} />}
        </div>
      </main>

      {panel && panel !== "sale" && <div className="panel-overlay" aria-hidden="true" onClick={() => setPanel(null)} />}
      {panel && panel !== "sale" && <aside className={`right-panel ${panel ? "open" : ""}`} role="dialog" aria-modal={panel ? true : undefined} aria-label="Контекстная панель" aria-hidden={!panel}>
        {panel === "pc" && selectedPc && <PcPanel pc={selectedPc} clients={currentClients} cashShifts={liveCashShifts} onClose={() => setPanel(null)} onEdit={() => setPanel("workstation")} onBook={() => openBooking(selectedPc.id)} onDeposit={openDeposit} onOpenSale={() => openSale(selectedPc)} onSessionChanged={() => setLiveRefreshKey((value) => value + 1)} api={LIVE_MODE ? api : undefined} />}
        {panel === "client" && selectedClient && <ClientPanel client={selectedClient} api={LIVE_MODE ? api : undefined} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} onDeposit={() => openDeposit(selectedClient)} onBonusDeposit={() => openDeposit(selectedClient, true)} />}
        {panel === "new-client" && LIVE_MODE && <NewClientPanel api={api} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "deposit" && <DepositPanel initialClient={selectedClient ?? undefined} bonusOnly={depositBonusOnly} onClose={() => setPanel(null)} onCompleted={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} clients={currentClients} api={LIVE_MODE ? api : undefined} />}
        {panel === "booking" && <BookingPanel initialWorkstationId={bookingWorkstationId} onClose={() => setPanel(null)} pcs={currentPcs} api={LIVE_MODE ? api : undefined} onCreated={() => { setBookingRefreshKey((value) => value + 1); setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "booking-edit" && selectedBooking && <BookingEditPanel reservation={selectedBooking} clients={currentClients} onClose={() => setPanel(null)} pcs={currentPcs} api={LIVE_MODE ? api : undefined} onSaved={() => { setBookingRefreshKey((value) => value + 1); setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "tariff" && LIVE_MODE && <TariffPanel api={api} groups={liveGroups} onClose={() => setPanel(null)} onSaved={() => { setCatalogRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "product" && LIVE_MODE && <ProductPanel api={api} product={selectedProduct ?? undefined} onClose={() => setPanel(null)} onSaved={() => { setCatalogRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "discount" && LIVE_MODE && <DiscountPanel api={api} onClose={() => setPanel(null)} onSaved={() => { setCatalogRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "workstation" && LIVE_MODE && <WorkstationPanel api={api} workstation={selectedPc ?? undefined} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "group" && LIVE_MODE && <GroupSettingsPanel api={api} group={selectedGroup} onClose={() => setPanel(null)} onSaved={() => { setSettingsRefreshKey((value) => value + 1); setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "payment-method" && LIVE_MODE && <PaymentMethodPanel api={api} method={selectedPaymentMethod} onClose={() => setPanel(null)} onSaved={() => { setSettingsRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "cash-open" && LIVE_MODE && <CashOpenPanel api={api} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "cash-movement" && LIVE_MODE && selectedCashShift && <CashMovementPanel api={api} shift={selectedCashShift} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
        {panel === "cash-close" && LIVE_MODE && selectedCashShift && <CashClosePanel api={api} shift={selectedCashShift} onClose={() => setPanel(null)} onSaved={() => { setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
      </aside>}
      {panel === "sale" && <SaleWorkspace api={LIVE_MODE ? api : undefined} pc={selectedPc} initialProduct={saleInitialProduct} clients={currentClients} cashShifts={liveCashShifts} onClose={() => setPanel(null)} onSaved={() => { setCatalogRefreshKey((value) => value + 1); setLiveRefreshKey((value) => value + 1); setPanel(null); }} />}
    </div>
  );
}

function LoginView({ api, onAuthenticated, restoring = false }: { api: GameClubApi; onAuthenticated: () => void; restoring?: boolean }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.login(username, password);
      onAuthenticated();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось войти");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="brand login-brand"><div className="brand-mark"><Command size={19} strokeWidth={2.6} /></div><span>gameshell</span><span className="brand-dot">·</span></div>
        <p className="eyebrow">Операторский доступ</p>
        <h1>Вход в клуб</h1>
        <p className="subheading">{restoring ? "Восстанавливаем защищённую сессию…" : "Авторизуйтесь, чтобы открыть dashboard и карту мест."}</p>
        <label>Логин<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" /></label>
        <label>Пароль<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
        {error && <div className="form-error">{error}</div>}
        <button className="primary-button wide" disabled={submitting || restoring}>{submitting ? "Проверяем..." : "Войти"}</button>
      </form>
    </div>
  );
}

type DashboardProps = { onDeposit: () => void; onOpenCash: () => void; onOpenMap: () => void; onOpenBookings: () => void; onPc: (pc: Workstation) => void; pcs: Workstation[]; clients: Client[]; reservations: Reservation[]; auditEvents: BackendAuditEvent[]; liveMode: boolean; revenueCents: number | null; revenueChargeCount: number; group: string; setGroup: (group: string) => void; zoneOptions: string[] };

function AnalyticsView({ api, clients: clientList, onClient }: { api?: GameClubApi; clients: Client[]; onClient: (client: Client) => void }) {
  const [startDate, setStartDate] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 29);
    return localDateInputValue(date);
  });
  const [endDate, setEndDate] = useState(() => localDateInputValue(new Date()));
  const [overview, setOverview] = useState<BackendAnalyticsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(api));
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!api) {
      setLoading(false);
      return undefined;
    }
    let active = true;
    setLoading(true);
    const start = new Date(startDate + "T00:00:00Z").toISOString();
    const end = new Date(endDate + "T00:00:00Z");
    end.setUTCDate(end.getUTCDate() + 1);
    void api.getAnalyticsOverview(start, end.toISOString(), 8).then((result) => {
      if (active) {
        setOverview(result);
        setError(null);
        setLoading(false);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить аналитику");
        setLoading(false);
      }
    });
    return () => {
      active = false;
    };
  }, [api, startDate, endDate]);

  const money = (cents: number) => (cents / 100).toLocaleString("ru-RU") + " ₽";
  const hours = (minutes: number) => (minutes / 60).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " ч";
  const openClient = (id: string) => {
    const client = clientList.find((item) => item.id === id);
    if (client) onClient(client);
  };
  const setPreset = (days: number) => {
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - days + 1);
    setStartDate(localDateInputValue(start));
    setEndDate(localDateInputValue(end));
  };
  const exportCsv = async () => {
    if (!api) return;
    setExporting(true);
    try {
      const start = new Date(startDate + "T00:00:00Z").toISOString();
      const end = new Date(endDate + "T00:00:00Z");
      end.setUTCDate(end.getUTCDate() + 1);
      const blob = await api.downloadAnalyticsCsv(start, end.toISOString(), 50);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `analytics-${startDate}-${endDate}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось выгрузить аналитику");
    } finally {
      setExporting(false);
    }
  };
  if (!api) return <div className="catalog-empty-state"><p className="eyebrow">Отчёты · read-only</p><h1>Аналитика</h1><p className="subheading">Live-режим покажет выручку, загрузку, товары и статистику клиентов.</p></div>;
  const maxDailyRevenue = Math.max(1, ...(overview?.daily_activity ?? []).map((item) => item.total_revenue_cents));
  const maxHourlyMinutes = Math.max(1, ...(overview?.hourly_activity ?? []).map((item) => item.played_minutes));
  const breakdown = (items: BackendAnalyticsOverview["zones"], empty: string, mode: "sessions" | "products" = "sessions") => items.length ? <div className="analytics-breakdown-list">{items.slice(0, 8).map((item) => <div className="analytics-breakdown-row" key={item.key}><div className="analytics-breakdown-title"><strong>{item.label}</strong><span>{mode === "products" ? `${item.product_sale_count} продаж · ${item.product_units} шт. · маржа ${money(item.gross_profit_cents)}` : `${item.session_count} сессий · ${hours(item.played_minutes)}`}</span></div><div className="analytics-breakdown-bar"><i style={{ width: `${Math.max(2, item.share_bps / 100)}%` }} /></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">{empty}</div>;
  return <>
    <div className="page-heading analytics-heading"><div><p className="eyebrow">Отчёты · Клуб, продажи и клиенты</p><h1>Аналитика</h1><p className="subheading">Единый отчёт по выручке, загрузке оборудования, товарам и поведению клиентов.</p></div><div className="heading-actions analytics-period"><div className="analytics-presets"><button onClick={() => setPreset(7)}>7 дн.</button><button onClick={() => setPreset(30)}>30 дн.</button><button onClick={() => setPreset(90)}>90 дн.</button></div><div className="analytics-date-field"><span>С</span><DateTimePicker value={startDate} onChange={setStartDate} mode="date" label="Дата начала отчёта" /></div><div className="analytics-date-field"><span>По</span><DateTimePicker value={endDate} onChange={setEndDate} mode="date" label="Дата окончания отчёта" /></div><button className="secondary-button" onClick={() => void exportCsv()} disabled={exporting} aria-busy={exporting}><Download size={14} /> {exporting ? "Готовим…" : "CSV"}</button></div></div>
    {error && <div className="form-error" role="alert">{error}</div>}
    {loading && <div className="timeline-empty">Собираем показатели…</div>}
    {!loading && overview && <>
      <div className="metric-grid analytics-metrics analytics-metrics-wide">
        <MetricCard title="Общая выручка" value={money(overview.total_revenue_cents)} delta={overview.session_count + overview.product_sale_count + " операций"} positive icon={<BarChart3 size={18} />} accent="violet" />
        <MetricCard title="Валовая прибыль" value={money(overview.gross_profit_cents)} delta={`скидки ${money(overview.discount_cents)}`} positive icon={<TrendingUp size={18} />} accent="green" />
        <MetricCard title="Игровое время" value={hours(overview.played_minutes)} delta={`${overview.session_count} сессий`} icon={<Clock3 size={18} />} accent="blue" />
        <MetricCard title="Загрузка мест" value={`${overview.occupancy_percent.toLocaleString("ru-RU")}%`} delta={`${overview.workstation_count} ПК`} icon={<Computer size={18} />} accent="orange" />
        <MetricCard title="Активные клиенты" value={String(overview.active_client_count)} delta={`${overview.new_client_count} новых`} icon={<Users size={18} />} accent="blue" />
        <MetricCard title="Посетители" value={String(overview.unique_visitor_count)} delta={`${overview.guest_session_count} гостевых`} icon={<Users size={18} />} accent="violet" />
        <MetricCard title="Продажи товаров" value={money(overview.product_revenue_cents)} delta={`${overview.product_units} единиц`} icon={<ShoppingCart size={18} />} accent="green" />
        <MetricCard title="Средняя сессия" value={`${overview.average_session_minutes.toLocaleString("ru-RU")} мин`} delta={`пик ${overview.peak_usage_hour ?? "—"}`} icon={<Wifi size={18} />} accent="orange" />
      </div>
      <div className="analytics-report-grid">
        <section className="white-card analytics-card analytics-chart-card"><div className="section-row"><div><h2>Динамика выручки</h2><p className="section-caption">Сессии и товары по дням выбранного периода</p></div><span className="active-chip">{startDate} — {endDate}</span></div><div className="analytics-chart-legend"><span><i className="session" /> Игровое время</span><span><i className="products" /> Товары</span></div><div className="analytics-chart">{overview.daily_activity.map((item) => <div className="analytics-chart-column" key={item.key}><div className="analytics-chart-bars"><i className="session" style={{ height: `${Math.max(item.session_revenue_cents ? 5 : 0, item.session_revenue_cents / maxDailyRevenue * 100)}%` }} /><i className="products" style={{ height: `${Math.max(item.product_revenue_cents ? 5 : 0, item.product_revenue_cents / maxDailyRevenue * 100)}%` }} /></div><span>{item.label}</span></div>)}</div></section>
        <section className="white-card analytics-card analytics-insights"><div className="section-row"><div><h2>Сводка периода</h2><p className="section-caption">Ключевые операционные сигналы</p></div></div><div className="analytics-insight-list"><div><span>Новые клиенты</span><strong>{overview.new_client_count}</strong></div><div><span>Вернувшиеся клиенты</span><strong>{overview.returning_client_count}</strong></div><div><span>Товарная себестоимость</span><strong>{money(overview.product_cost_cents)}</strong></div><div><span>Пиковый час</span><strong>{overview.peak_usage_hour ?? "Нет данных"}</strong></div><div><span>Продажи / сессии</span><strong>{overview.product_sale_count} / {overview.session_count}</strong></div></div></section>
      </div>
      <div className="analytics-report-grid">
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Загрузка по часам</h2><p className="section-caption">Когда клуб наиболее загружен</p></div></div><div className="analytics-hourly-chart">{overview.hourly_activity.map((item) => <div className="analytics-hour-column" key={item.key} title={`${item.label}: ${hours(item.played_minutes)}`}><i style={{ height: `${Math.max(item.played_minutes ? 5 : 2, item.played_minutes / maxHourlyMinutes * 100)}%` }} /><span>{Number(item.key) % 3 === 0 ? item.label : ""}</span></div>)}</div></section>
        <section className="white-card analytics-card"><div className="section-row"><div><h2>Способы оплаты</h2><p className="section-caption">Распределение подтверждённой выручки</p></div></div>{overview.payment_methods.length ? <div className="analytics-payment-list">{overview.payment_methods.map((item) => <div className="analytics-payment-row" key={item.key}><div><strong>{item.label}</strong><span>{item.operation_count} операций · {item.share_bps / 100}%</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Оплат за период нет</div>}</section>
      </div>
      <div className="analytics-breakdown-grid"><section className="white-card analytics-card"><div className="section-row"><div><h2>Зоны клуба</h2><p className="section-caption">Загрузка и выручка по залам</p></div></div>{breakdown(overview.zones, "Сессий по зонам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Игровые места</h2><p className="section-caption">Какие ПК используются чаще</p></div></div>{breakdown(overview.workstations, "Данных по местам нет")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Тарифы</h2><p className="section-caption">Продажи игрового времени</p></div></div>{breakdown(overview.tariffs, "Тарифы за период не продавались")}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Категории товаров</h2><p className="section-caption">Выручка, себестоимость и маржа</p></div></div>{breakdown(overview.product_categories, "Продаж по категориям нет", "products")}</section></div>
      <div className="analytics-grid"><section className="white-card analytics-card"><div className="section-row"><div><h2>Популярные товары</h2><p className="section-caption">Количество, выручка и маржа по snapshots</p></div><span className="active-chip">{overview.product_sale_count} продаж</span></div>{overview.top_products.length ? <div className="analytics-list">{overview.top_products.map((item) => <div className="analytics-list-row" key={item.product_id + item.product_name}><div><strong>{item.product_name}</strong><span>{item.units} шт. · маржа {money(item.gross_profit_cents)}</span></div><b>{money(item.revenue_cents)}</b></div>)}</div> : <div className="timeline-empty">Продаж за период нет</div>}</section><section className="white-card analytics-card"><div className="section-row"><div><h2>Лучшие клиенты</h2><p className="section-caption">Игровое время, товары и общие траты</p></div><span className="active-chip">{overview.active_client_count} активных</span></div>{overview.top_clients.length ? <div className="analytics-list">{overview.top_clients.map((item) => <button className="analytics-list-row analytics-client-row" key={item.client_id} onClick={() => openClient(item.client_id)}><div><strong>{item.nickname}</strong><span>{hours(item.played_minutes)} · {item.session_count} сессий · товары {money(item.product_spend_cents)}</span></div><b>{money(item.total_spend_cents)}</b></button>)}</div> : <div className="timeline-empty">Активности клиентов за период нет</div>}</section></div>
    </>}
  </>;
}

function Dashboard({ onDeposit, onOpenCash, onOpenMap, onOpenBookings, onPc, pcs, clients: clientList, reservations, auditEvents, liveMode, revenueCents, revenueChargeCount, group, setGroup, zoneOptions }: DashboardProps) {
  const busy = pcs.filter((pc) => pc.status === "busy").length;
  const free = pcs.filter((pc) => pc.status === "online").length;
  const visiblePcs = pcs.filter((pc) => group === "Все зоны" || pc.group === group);
  const deposits = clientList.reduce((total, client) => total + client.balance, 0);
  const waitingReservations = reservations.filter((reservation) => reservation.status === "confirmed").length;
  return (
    <>
      <div className="page-heading"><div><p className="eyebrow">{new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p><h1>Добрый день, Алексей</h1><p className="subheading">Вот что происходит в клубе прямо сейчас.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onOpenCash}><Clock3 size={16} /> Открыть смену</button><button className="primary-button" onClick={onDeposit}><Plus size={17} /> Пополнить депозит</button></div></div>
      <div className="metric-grid">
        <MetricCard title={liveMode ? "Выручка сегодня" : "Выручка за смену"} value={liveMode ? (revenueCents === null ? "—" : `${(revenueCents / 100).toLocaleString("ru-RU")} ₽`) : "48 620 ₽"} delta={liveMode ? `${revenueChargeCount} списаний` : "+12,8%"} positive={!liveMode && revenueCents === null} icon={<Banknote size={18} />} accent="violet" />
        <MetricCard title="Активные сессии" value={`${busy} / ${pcs.length}`} delta={`${free} свободных`} positive icon={<Wifi size={18} />} accent="blue" />
        <MetricCard title="Брони сегодня" value={liveMode ? String(reservations.length) : "18"} delta={liveMode ? `${waitingReservations} ожидают` : "4 ожидают"} icon={<CalendarDays size={18} />} accent="orange" />
        <MetricCard title="На депозитах" value={liveMode ? `${deposits.toLocaleString("ru-RU")} ₽` : "126 840 ₽"} delta={liveMode ? `${clientList.length} клиентов` : "32 клиента"} icon={<CreditCard size={18} />} accent="green" />
      </div>
      <div className="section-row"><div><h2>Карта мест</h2><p className="section-caption">Состояние игровых мест в реальном времени</p></div><div className="section-tools"><Segmented value={group} onChange={setGroup} options={zoneOptions} /><button className="text-button" onClick={onOpenMap}>Открыть карту <ChevronRight size={15} /></button></div></div>
      <PcGrid pcs={visiblePcs} onPc={onPc} compact />
      <div className="lower-grid"><ActivityCard liveMode={liveMode} events={auditEvents} /><UpcomingBookings liveMode={liveMode} reservations={reservations} pcs={pcs} clients={clientList} onOpenBookings={onOpenBookings} /></div>
    </>
  );
}

function MetricCard({ title, value, delta, positive, icon, accent }: { title: string; value: string; delta: string; positive?: boolean; icon: React.ReactNode; accent: string }) {
  return <div className="metric-card"><div className={`metric-icon ${accent}`}>{icon}</div><div className="metric-title">{title}</div><div className="metric-value">{value}</div><div className={`metric-delta ${positive ? "positive" : ""}`}>{positive && <ArrowUpRight size={14} />}{delta}</div></div>;
}

function Segmented({ value, onChange, options }: { value: string; onChange: (value: string) => void; options: string[] }) {
  return <div className="segmented" role="group" aria-label="Фильтр зоны">{options.map((option) => <button className={value === option ? "selected" : ""} key={option} aria-pressed={value === option} onClick={() => onChange(option)}>{option}</button>)}</div>;
}

function PcGrid({ pcs, onPc, compact = false }: { pcs: Workstation[]; onPc: (pc: Workstation) => void; compact?: boolean }) {
  return <div className={`pc-grid ${compact ? "compact" : ""}`}>{pcs.map((pc) => <button className="pc-card" key={pc.id} onClick={() => onPc(pc)}><div className="pc-card-top"><span className={`pc-status-dot ${pc.status}`} /><span className="pc-name">{pc.name}</span><MoreHorizontal size={16} className="muted" /></div><div className="pc-illustration"><Computer size={compact ? 28 : 34} strokeWidth={1.45} /></div><div className="pc-card-bottom"><span className={statusMeta[pc.status].className}>{statusMeta[pc.status].label}</span>{pc.client ? <span className="pc-client">{pc.client}</span> : <span className="pc-zone">{pc.group}</span>}</div>{pc.session && <div className="session-time"><Clock3 size={12} /> {pc.session}</div>}</button>)}</div>;
}

function MapView({ onPc, onSalePc, onBookPc, onEditPc, pcs, group, setGroup, zoneOptions, onNewWorkstation, onPositionsChange }: { onPc: (pc: Workstation) => void; onSalePc: (pc: Workstation) => void; onBookPc: (workstationId?: string) => void; onEditPc: (pc: Workstation) => void; pcs: Workstation[]; group: string; setGroup: (group: string) => void; zoneOptions: string[]; onNewWorkstation?: () => void; onPositionsChange?: (changes: Array<{ workstationId: string; position: number }>) => Promise<void> }) {
  const [draggedWorkstationId, setDraggedWorkstationId] = useState<string | null>(null);
  const [dropTargetSlot, setDropTargetSlot] = useState<number | null>(null);
  const [positionError, setPositionError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [contextPcId, setContextPcId] = useState<string | null>(null);
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

  return <><div className="page-heading"><div><p className="eyebrow">Оборудование · Рабочая карта</p><h1>Карта клуба</h1><p className="subheading">{editMode ? "Перетащите места в нужные ячейки и сохраните планировку." : "Нажмите на место, чтобы сразу оформить продажу; управление ПК — через кнопку ⋯."}</p></div><div className="heading-actions"><button className={`secondary-button map-edit-toggle ${editMode ? "active" : ""}`} aria-pressed={editMode} onClick={() => { setEditMode((value) => !value); setContextPcId(null); }}><Edit3 size={15} /> {editMode ? "Завершить редактирование" : "Редактировать карту"}</button><button className="primary-button" disabled={!onNewWorkstation} onClick={onNewWorkstation}><Plus size={17} /> Добавить место</button></div></div><div className="map-toolbar"><Segmented value={group} onChange={setGroup} options={zoneOptions} />{editMode && onPositionsChange && <span className="map-arrange-hint">Перетащите карточку на нужное место</span>}<div className="legend"><span><i className="legend-dot online" /> Свободен</span><span><i className="legend-dot busy" /> Занят</span><span><i className="legend-dot offline" /> Не в сети</span><span><i className="legend-dot maintenance" /> Сервис</span></div></div>{positionError && <div className="form-error map-error" role="alert">{positionError}</div>}<div className="map-stage"><aside className="map-legend-panel"><div className="map-panel-title"><strong>Состояние мест</strong><span>{pcs.length}</span></div><div className="map-legend-item"><i className="legend-square online" /><span>Свободны</span><b>{pcs.filter((pc) => pc.status === "online").length}</b></div><div className="map-legend-item"><i className="legend-square busy" /><span>Активная сессия</span><b>{pcs.filter((pc) => pc.status === "busy").length}</b></div><div className="map-legend-item"><i className="legend-square offline" /><span>Нет связи</span><b>{pcs.filter((pc) => pc.status === "offline").length}</b></div><div className="map-legend-item"><i className="legend-square maintenance" /><span>Сервис</span><b>{pcs.filter((pc) => pc.status === "maintenance").length}</b></div><div className="map-panel-zone">{group === "Все зоны" ? "Все зоны" : group}</div></aside><div className="map-canvas" aria-label="Карта игровых мест">{pcs.length ? Array.from({ length: slotCount }, (_, slot) => { const placed = slotByIndex.get(slot); const showContext = placed && contextPcId === placed.pc.id && !editMode; return <div className={`map-slot ${placed ? "occupied" : ""} ${dropTargetSlot === slot ? "drop-target" : ""}`} key={slot} aria-label={`Место ${slot + 1}${placed ? `: ${placed.pc.name}` : ": свободно"}`} onDragOver={(event) => { if (editMode && onPositionsChange) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; setDropTargetSlot(slot); } }} onDragLeave={() => setDropTargetSlot((current) => current === slot ? null : current)} onDrop={(event) => void handleDrop(event, slot)}>{!placed && <span className="map-slot-number">#{slot + 1}</span>}{placed && <><button className={`map-seat ${placed.pc.status} ${draggedWorkstationId === placed.pc.id ? "is-dragging" : ""}`} draggable={editMode && Boolean(onPositionsChange)} onDragStart={(event) => { if (!editMode || !onPositionsChange) return; justDraggedRef.current = true; setPositionError(null); setDraggedWorkstationId(placed.pc.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", placed.pc.id); }} onDragEnd={() => { setDraggedWorkstationId(null); setDropTargetSlot(null); window.setTimeout(() => { justDraggedRef.current = false; }, 0); }} onClick={(event) => { event.stopPropagation(); if (justDraggedRef.current) { justDraggedRef.current = false; return; } if (editMode) { onEditPc(placed.pc); } else { onSalePc(placed.pc); } }} onContextMenu={(event) => { event.preventDefault(); setContextPcId(placed.pc.id); }} aria-label={`${placed.pc.name}: ${statusMeta[placed.pc.status].label}`}><div className="map-seat-top"><span>{placed.pc.name}</span><span className="map-seat-state">{placed.pc.status === "busy" ? <Wifi size={12} /> : placed.pc.status === "maintenance" ? <Settings size={12} /> : placed.pc.status === "offline" ? <X size={12} /> : <Check size={12} />}</span></div><div className="map-seat-screen"><Computer size={20} /></div><div className="map-seat-bottom"><small>{placed.pc.client || statusMeta[placed.pc.status].label}</small>{placed.pc.session && <small><Clock3 size={10} /> {placed.pc.session}</small>}</div></button><button type="button" className="map-seat-manage" title="Открыть карточку места" aria-label={`Открыть карточку ${placed.pc.name}`} onClick={(event) => { event.stopPropagation(); onPc(placed.pc); }}><PanelRightClose size={12} /></button>{showContext && <div className="map-context-menu" role="menu" onClick={(event) => event.stopPropagation()}><strong>{placed.pc.name}</strong><button role="menuitem" onClick={() => { setContextPcId(null); onSalePc(placed.pc); }}><Receipt size={13} /> Оформить продажу</button><button role="menuitem" onClick={() => { setContextPcId(null); onPc(placed.pc); }}><PanelRightClose size={13} /> Открыть карточку</button><button role="menuitem" disabled={placed.pc.status === "busy" || placed.pc.status === "offline" || placed.pc.status === "maintenance"} onClick={() => { setContextPcId(null); onBookPc(placed.pc.id); }}><CalendarDays size={13} /> Забронировать</button><button role="menuitem" onClick={() => { setContextPcId(null); onEditPc(placed.pc); }}><Settings size={13} /> Настройки места</button></div>}</>}</div>; }) : <div className="map-empty">Зарегистрированных мест пока нет</div>}</div></div></>;
}

function WorkstationTable({ pcs, onPc }: { pcs: Workstation[]; onPc: (pc: Workstation) => void }) {
  return <div className="table-card workstation-table"><div className="table-head"><span>Место</span><span>Зона</span><span>Статус</span><span>Клиент</span><span>Heartbeat</span><span /></div>{pcs.map((pc) => <button className="table-row" key={pc.id} onClick={() => onPc(pc)}><span className="client-cell"><span className={`pc-status-dot ${pc.status}`} /><strong>{pc.name}</strong></span><span>{pc.group}</span><span className={statusMeta[pc.status].className}>{statusMeta[pc.status].label}</span><span>{pc.client || "—"}</span><span className="muted">{pc.lastSeen || "—"}</span><ChevronRight size={16} /></button>)}{!pcs.length && <div className="timeline-empty">Зарегистрированных мест пока нет</div>}</div>;
}

function WorkstationPanel({ api, workstation, onClose, onSaved }: { api: GameClubApi; workstation?: Workstation; onClose: () => void; onSaved: () => void }) {
  const [deviceId, setDeviceId] = useState(workstation?.deviceId ?? "");
  const [name, setName] = useState(workstation?.name ?? "");
  const [groupId, setGroupId] = useState(workstation?.groupId ?? (workstation?.group === "VIP-зона" ? "vip" : "main"));
  const [position, setPosition] = useState(workstation?.position && workstation.position > 0 ? String(workstation.position) : "");
  const [groups, setGroups] = useState<BackendWorkstationGroup[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void api.listWorkstationGroups().then(setGroups).catch(() => setGroups([]));
  }, [api]);

  const availableGroups = groups.length
    ? groups.some((item) => item.id === groupId) || !workstation
      ? groups
      : [{ id: groupId, name: workstation.group, theme: "standard" as const, updated_at: null }, ...groups]
    : [];

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedPosition = position.trim() ? Number(position) : null;
    if ((!workstation && !deviceId.trim()) || !name.trim() || (parsedPosition !== null && (!Number.isInteger(parsedPosition) || parsedPosition < 1))) {
      setError(workstation ? "Укажите название и корректную позицию" : "Укажите device ID, название и корректную позицию");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (workstation) {
        await api.updateWorkstation(workstation.id, { name: name.trim(), group_id: groupId || null, position: parsedPosition });
      } else {
        await api.registerWorkstation({
          device_id: deviceId.trim(),
          name: name.trim(),
          group_id: groupId || null,
          position: parsedPosition,
          capabilities: ["commands.v1", "theme.v1", "sessions.v1"],
        });
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось добавить игровое место");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><div className="panel-header"><div><p>Оборудование</p><h2>{workstation ? "Редактировать игровое место" : "Новое игровое место"}</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}>{!workstation && <label>Device ID<input value={deviceId} onChange={(event) => setDeviceId(event.target.value)} placeholder="pc-001" autoFocus /></label>}{workstation && <div className="detail-row"><span>Device ID</span><strong>{deviceId}</strong></div>}<label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="VIP-01" autoFocus={Boolean(workstation)} /></label><label>Зона<select value={groupId} onChange={(event) => setGroupId(event.target.value)}>{availableGroups.length ? availableGroups.map((item) => <option value={item.id} key={item.id}>{item.name}</option>) : <><option value="main">Обычный зал</option><option value="vip">VIP-зона</option></>}</select></label><label>Позиция на карте<input type="number" min="1" step="1" value={position} onChange={(event) => setPosition(event.target.value)} placeholder="Не задана" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : workstation ? "Сохранить изменения" : "Добавить место"}</button><p className="subheading">Позиция задаёт место на рабочей карте; на карте место можно перетащить мышью.</p></form></div>;
}

function BookingsView({ api, pcs, clients, zoneOptions, onNewBooking, onEditBooking, refreshKey }: { api?: GameClubApi; pcs: Workstation[]; clients: Client[]; zoneOptions: string[]; onNewBooking: () => void; onEditBooking: (reservation: Reservation) => void; refreshKey: number }) {
  return api ? <LiveBookingsView api={api} pcs={pcs} clients={clients} zoneOptions={zoneOptions} onNewBooking={onNewBooking} onEditBooking={onEditBooking} refreshKey={refreshKey} /> : <MockBookingsView zoneOptions={zoneOptions} onNewBooking={onNewBooking} />;
}

function LiveBookingsView({ api, pcs, clients, zoneOptions, onNewBooking, onEditBooking, refreshKey }: { api: GameClubApi; pcs: Workstation[]; clients: Client[]; zoneOptions: string[]; onNewBooking: () => void; onEditBooking: (reservation: Reservation) => void; refreshKey: number }) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [transitioningId, setTransitioningId] = useState<string | null>(null);
  const [bookingGroup, setBookingGroup] = useState("Все зоны");
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const hours = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"];

  useEffect(() => {
    let active = true;
    const start = new Date(selectedDate);
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    api.listReservations(start.toISOString(), end.toISOString()).then((items) => {
      if (active) {
        setReservations(items);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить брони");
      }
    });
    return () => {
      active = false;
    };
  }, [api, refreshKey, selectedDate]);

  const resources = pcs.filter((pc) => bookingGroup === "Все зоны" || pc.group === bookingGroup);
  const timelineStart = new Date(selectedDate);
  timelineStart.setHours(10, 0, 0, 0);
  const timelineEnd = new Date(timelineStart);
  timelineEnd.setHours(18, 0, 0, 0);
  const totalMinutes = (timelineEnd.getTime() - timelineStart.getTime()) / 60000;
  const blockStyle = (reservation: Reservation) => {
    const start = new Date(reservation.start_at).getTime();
    const end = new Date(reservation.end_at).getTime();
    const left = Math.max(0, Math.min(100, ((start - timelineStart.getTime()) / 60000 / totalMinutes) * 100));
    const right = Math.max(left + 4, Math.min(100, ((end - timelineStart.getTime()) / 60000 / totalMinutes) * 100));
    return { left: `${left}%`, width: `${right - left}%` };
  };
  const statusClass = (status: string) => status === "active" ? "active" : status === "confirmed" ? "confirmed" : status === "completed" ? "completed" : status === "no_show" ? "no-show" : "pending";
  const clientNames = new Map(clients.map((client) => [client.id, client.nickname]));
  const clientLabel = (reservation: Reservation) => reservation.guest_name || (reservation.client_id ? clientNames.get(reservation.client_id) || "Клиент" : "Гость");
  const transition = async (
    reservation: Reservation,
    action: "activate" | "complete" | "no-show" | "cancel",
  ) => {
    const actionLabels = {
      activate: "активировать",
      complete: "завершить",
      "no-show": "отметить как неявку",
      cancel: "отменить",
    } as const;
    if (action === "no-show" || action === "cancel") {
      if (!window.confirm(`${actionLabels[action].replace(/^./, (value) => value.toUpperCase())} бронь ${clientLabel(reservation)}?`)) {
        return;
      }
    }
    setTransitioningId(reservation.id);
    setError(null);
    try {
      const updated = action === "activate"
        ? await api.activateReservation(reservation.id)
        : action === "complete"
          ? await api.completeReservation(reservation.id)
          : action === "no-show"
            ? await api.markNoShowReservation(reservation.id)
            : await api.cancelReservation(reservation.id);
      setReservations((items) => items.map((item) => item.id === reservation.id ? updated : item));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : `Не удалось ${actionLabels[action]} бронь`);
    } finally {
      setTransitioningId(null);
    }
  };

  const cancel = async (reservation: Reservation) => {
    await transition(reservation, "cancel");
  };

  return <><div className="page-heading"><div><p className="eyebrow">Расписание · {selectedDate.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</p><h1>Бронирования</h1><p className="subheading">Выбранная дата · {resources.length} мест в расписании</p></div><div className="heading-actions booking-heading-actions"><DateTimePicker value={localDateInputValue(selectedDate)} onChange={(value) => { const next = parsePickerValue(value, "date"); if (Number.isFinite(next.getTime())) setSelectedDate(next); }} mode="date" label="Дата расписания" className="booking-date-picker" /><button className="primary-button" onClick={onNewBooking}><Plus size={17} /> Новая бронь</button></div></div><div className="booking-toolbar"><div className="date-chip"><ChevronRight size={15} className="rotate-180" /> <strong>{selectedDate.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</strong> <ChevronRight size={15} /></div><Segmented value={bookingGroup} onChange={setBookingGroup} options={zoneOptions} /><div className="timeline-note"><i /> Данные из backend</div></div>{error && <div className="search-hint error">{error}</div>}<div className="timeline"><div className="timeline-hours"><div className="resource-head">Место</div>{hours.map((hour) => <span key={hour}>{hour}</span>)}</div>{resources.map((resource) => <div className="timeline-row" key={resource.id}><div className="resource-name"><span className={`pc-status-dot ${resource.status}`} />{resource.name}</div>{hours.map((hour) => <div className="timeline-cell" key={hour} />)}{reservations.filter((reservation) => reservation.workstation_ids.includes(resource.id) && reservation.status !== "cancelled").map((reservation) => <div className={`booking-block ${statusClass(reservation.status)}`} style={blockStyle(reservation)} key={reservation.id} role="button" tabIndex={0} aria-label={`Открыть бронь ${clientLabel(reservation)}`} onClick={() => onEditBooking(reservation)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onEditBooking(reservation); } }}><strong>{clientLabel(reservation)}</strong><span>{new Date(reservation.start_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} — {new Date(reservation.end_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span><div className="booking-actions">{reservation.status === "confirmed" && <><button className="booking-action" aria-label={`Активировать бронь ${clientLabel(reservation)}`} title="Активировать" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "activate"); }}><Play size={10} /></button><button className="booking-action" aria-label={`Отметить неявку ${clientLabel(reservation)}`} title="No-show" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "no-show"); }}><UserX size={11} /></button></>}{reservation.status === "active" && <button className="booking-action" aria-label={`Завершить бронь ${clientLabel(reservation)}`} title="Завершить" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void transition(reservation, "complete"); }}><Check size={11} /></button>}{(reservation.status === "confirmed" || reservation.status === "active") && <button className="booking-action danger" aria-label={`Отменить бронь ${clientLabel(reservation)}`} title="Отменить бронь" disabled={transitioningId === reservation.id} onClick={(event) => { event.stopPropagation(); void cancel(reservation); }}><X size={11} /></button>}</div></div>)}</div>)}{!resources.length && <div className="timeline-empty">Нет зарегистрированных мест</div>}</div></>;
}

function MockBookingsView({ zoneOptions, onNewBooking }: { zoneOptions: string[]; onNewBooking: () => void }) {
  const hours = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"];
  return <><div className="page-heading"><div><p className="eyebrow">Расписание · Сегодня</p><h1>Бронирования</h1><p className="subheading">Сегодня · 24 места в расписании</p></div><div className="heading-actions"><button className="secondary-button"><CalendarDays size={16} /> Выбрать дату</button><button className="primary-button" onClick={onNewBooking}><Plus size={17} /> Новая бронь</button></div></div><div className="booking-toolbar"><div className="date-chip"><ChevronRight size={15} className="rotate-180" /> <strong>Сегодня</strong> <ChevronRight size={15} /></div><Segmented value="Все зоны" onChange={() => undefined} options={zoneOptions} /><div className="timeline-note"><i /> Демо-расписание</div></div><div className="timeline"><div className="timeline-hours"><div className="resource-head">Место</div>{hours.map((hour) => <span key={hour}>{hour}</span>)}</div>{["VIP-01", "VIP-02", "VIP-03", "A-01", "A-02", "A-03"].map((resource) => <div className="timeline-row" key={resource}><div className="resource-name"><span className="pc-status-dot online" />{resource}</div>{hours.map((hour) => <div className="timeline-cell" key={hour} />)}{resource === "VIP-02" && <div className="booking-block confirmed" style={{ left: "26%", width: "25%" }}><strong>s1lent</strong><span>12:00 — 14:00</span></div>}{resource === "A-01" && <div className="booking-block pending" style={{ left: "43%", width: "19%" }}><strong>night_walker</strong><span>13:30 — 15:00</span></div>}{resource === "A-03" && <div className="booking-block active" style={{ left: "61%", width: "32%" }}><strong>Dasha</strong><span>14:00 — 17:00</span></div>}</div>)}</div></>;
}

function ClientsView({
  search,
  setSearch,
  onDeposit,
  onNewClient,
  onClient,
  clients: clientList,
  api,
}: {
  search: string;
  setSearch: (value: string) => void;
  onDeposit: () => void;
  onNewClient?: () => void;
  onClient: (client: Client) => void;
  clients: Client[];
  api?: GameClubApi;
}) {
  const normalized = search.toLowerCase().trim();
  const searchField = getSearchField(normalized);
  const canSearch = searchField !== null;
  const [liveResults, setLiveResults] = useState<Client[]>(clientList);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      setLiveResults(clientList);
      return undefined;
    }
    if (!searchField) {
      setLiveResults(search.trim() ? [] : clientList);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(normalized, searchField);
        if (active) {
          setLiveResults(found.map(toUiClient));
          setSearchError(null);
        }
      } catch (error) {
        if (active) {
          setSearchError(error instanceof ApiError ? error.message : "Не удалось выполнить поиск");
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientList, normalized, searchField]);

  const results = api
    ? liveResults
    : canSearch
      ? clientList.filter((client) => client.nickname.toLowerCase().includes(normalized) || client.phone.replace(/\D/g, "").includes(normalized.replace(/\D/g, "")))
      : clientList;
  return <><div className="page-heading"><div><p className="eyebrow">CRM · {api ? clientList.length : 32} клиентов онлайн</p><h1>Клиенты</h1><p className="subheading">Поиск, баланс и история операций клуба.</p></div><div className="heading-actions">{onNewClient && <button className="secondary-button" onClick={onNewClient}><Plus size={15} /> Новый клиент</button>}<button className="primary-button" onClick={onDeposit}><Plus size={17} /> Пополнить депозит</button></div></div><div className="search-row"><div className="search-box"><Search size={17} /><input aria-label="Поиск клиента" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти по нику или телефону..." /><kbd>⌘ K</kbd></div><button className="secondary-button">Фильтры <ChevronDown size={15} /></button></div>{search && !canSearch && <div className="search-hint">Введите минимум 3 символа ника или 4 цифры номера</div>}{searchError && <div className="search-hint error" role="alert">{searchError}</div>}<div className="table-card"><div className="table-head"><span>Клиент</span><span>Категория</span><span>Баланс</span><span>Бонусы</span><span>Последний визит</span><span /></div>{results.map((client) => <div className="table-row" key={client.id}><div className="client-cell"><div className="client-avatar">{client.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{client.nickname}</strong><span>{formatRussianPhone(client.phone)}</span></div></div><span className="category-chip">{client.category}</span><strong>{client.balance.toLocaleString("ru-RU")} ₽</strong><span className="bonus-value">+{client.bonus} ₽</span><span className="muted">{api ? "—" : "Сегодня, 11:24"}</span><button className="icon-button small" aria-label={`Открыть клиента ${client.nickname}`} onClick={() => onClient(client)}><ChevronRight size={16} /></button></div>)}</div></>;
}

function LegacyClientPanel({ client, api, onClose, onDeposit }: { client: Client; api?: GameClubApi; onClose: () => void; onDeposit: () => void }) {
  const [operations, setOperations] = useState<BackendBalanceOperation[]>([]);
  const [loadingOperations, setLoadingOperations] = useState(Boolean(api));
  const [operationsError, setOperationsError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      setLoadingOperations(false);
      return undefined;
    }
    let active = true;
    setLoadingOperations(true);
    setOperationsError(null);
    void api.listClientOperations(client.id).then((items) => {
      if (active) {
        setOperations(items);
        setLoadingOperations(false);
      }
    }).catch((error) => {
      if (active) {
        setLoadingOperations(false);
        setOperationsError(error instanceof ApiError ? error.message : "Не удалось загрузить историю");
      }
    });
    return () => {
      active = false;
    };
  }, [api, client.id]);

  return <div className="panel-inner"><PanelHeader title={client.nickname} subtitle="Карточка клиента" onClose={onClose} /><div className="panel-pc-hero"><div className="client-avatar large-client-avatar">{client.nickname.slice(0, 2).toUpperCase()}</div><div><span className="category-chip">{client.category}</span><h2>{formatRussianPhone(client.phone)}</h2><p>Профиль клиента клуба</p></div></div><div className="panel-section"><div className="detail-row"><span>Баланс</span><strong>{client.balance.toLocaleString("ru-RU")} ₽</strong></div><div className="detail-row"><span>Бонусы</span><strong className="bonus-value">{client.bonus.toLocaleString("ru-RU")} ₽</strong></div><div className="detail-row"><span>Категория скидки</span><strong>{client.category}</strong></div></div><div className="panel-section operation-section"><div className="operation-heading"><h3>История операций</h3><span>{api ? "Последние 20" : "Пример"}</span></div>{loadingOperations && <div className="timeline-empty">Загружаем операции…</div>}{operationsError && <div className="form-error" role="alert">{operationsError}</div>}{!loadingOperations && !operationsError && api && operations.length === 0 && <div className="timeline-empty">Операций пока нет</div>}{!api && <div className="timeline-empty">Операции появятся после пополнения или списания.</div>}{operations.map((operation) => <div className="operation-row" key={operation.id}><div className={`operation-icon ${operation.amount_cents >= 0 ? "income" : "expense"}`}>{operation.amount_cents >= 0 ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}</div><div><strong>{operation.reason || (operation.operation_type === "top_up" ? "Пополнение" : "Списание")}</strong><span>{new Date(operation.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}{operation.bonus_amount ? ` · бонус +${operation.bonus_amount} ₽` : ""}</span></div><b className={operation.amount_cents >= 0 ? "income-text" : "expense-text"}>{operation.amount_cents >= 0 ? "+" : ""}{(operation.amount_cents / 100).toLocaleString("ru-RU")} ₽</b></div>)}</div><div className="panel-actions"><button className="primary-button wide" onClick={onDeposit}><Plus size={16} /> Пополнить депозит</button></div></div>;
}

function ClientPanel({ client, api, onClose, onSaved, onDeposit, onBonusDeposit }: { client: Client; api?: GameClubApi; onClose: () => void; onSaved: () => void; onDeposit: () => void; onBonusDeposit: () => void }) {
  const [operations, setOperations] = useState<BackendBalanceOperation[]>([]);
  const [analytics, setAnalytics] = useState<BackendClientAnalytics | null>(null);
  const [discountRules, setDiscountRules] = useState<Awaited<ReturnType<GameClubApi["listDiscountRules"]>>>([]);
  const [editing, setEditing] = useState(false);
  const [nickname, setNickname] = useState(client.nickname);
  const [phone, setPhone] = useState(formatRussianPhone(client.phone));
  const [category, setCategory] = useState(client.category === "Без скидки" ? "" : client.category);
  const [error, setError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(Boolean(api));
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!api) {
      setLoading(false);
      return undefined;
    }
    let active = true;
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - 29);
    end.setDate(end.getDate() + 1);
    void Promise.all([
      api.listClientOperations(client.id),
      api.listDiscountRules(),
      api.getClientAnalytics(client.id, start.toISOString(), end.toISOString(), 6),
    ]).then(([items, rules, clientAnalytics]) => {
      if (active) {
        setOperations(items);
        setDiscountRules(rules);
        setAnalytics(clientAnalytics);
        setLoading(false);
      }
    }).catch((requestError) => {
      if (active) {
        setLoading(false);
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить данные клиента");
      }
    });
    return () => { active = false; };
  }, [api, client.id]);

  const categories = Array.from(new Set(discountRules.map((rule) => rule.category)));
  if (category && !categories.includes(category)) categories.unshift(category);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!api) return;
    if (nickname.trim().length < 3) {
      setError("Ник должен содержать минимум 3 символа");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.updateClient(client.id, { nickname: nickname.trim(), phone: phone.trim() || undefined, discount_category: category || undefined });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить клиента");
    } finally {
      setSaving(false);
    }
  };

  const resetPassword = async () => {
    if (!api || !window.confirm(`Сбросить пароль клиента «${client.nickname}»?`)) return;
    setSaving(true);
    setError(null);
    setPasswordMessage(null);
    try {
      const result = await api.resetClientPassword(client.id);
      setPasswordMessage(`Временный пароль: ${result.temporary_password}`);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сбросить пароль");
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!api || !window.confirm(`Удалить клиента «${client.nickname}» из активного списка?`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteClient(client.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить клиента");
      setSaving(false);
    }
  };

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  return <div className="panel-inner"><PanelHeader title={client.nickname} subtitle="CRM · карточка клиента" onClose={onClose} /><div className="panel-pc-hero client-panel-hero"><div className="client-avatar large-client-avatar">{client.nickname.slice(0, 2).toUpperCase()}</div><div><span className="category-chip">{client.category}</span><h2>{formatRussianPhone(client.phone)}</h2><p>Клиентский профиль и операции</p></div></div><div className="client-action-grid"><button className="secondary-button" onClick={() => setEditing((value) => !value)}><Edit3 size={14} /> {editing ? "Отменить" : "Редактировать"}</button><button className="secondary-button" onClick={() => void resetPassword()} disabled={!api || saving}><ShieldCheck size={14} /> Сбросить пароль</button></div>{passwordMessage && <div className="form-success" role="status">{passwordMessage}</div>}{editing && <form className="booking-form client-edit-form" onSubmit={(event) => void save(event)}><label>Ник<input value={nickname} onChange={(event) => setNickname(event.target.value)} /></label><label>Телефон<input type="tel" inputMode="tel" value={phone} onChange={(event) => setPhone(formatRussianPhone(event.target.value))} placeholder="+7 (999) 000-00-00" /></label><label>Категория скидки<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="">Без скидки</option>{categories.map((item) => <option value={item} key={item}>{item}</option>)}</select></label><button className="primary-button wide" disabled={saving}>{saving ? "Сохраняем..." : "Сохранить клиента"}</button></form>}<div className="panel-section client-balance-section"><div className="balance-highlight"><div><span>Основной баланс</span><strong>{client.balance.toLocaleString("ru-RU")} ₽</strong></div><div><span>Бонусный баланс</span><strong className="bonus-value">{client.bonus.toLocaleString("ru-RU")} ₽</strong></div></div><div className="client-action-grid"><button className="primary-button" onClick={onDeposit}><Plus size={14} /> Пополнить баланс</button><button className="secondary-button" onClick={onBonusDeposit}><Sparkles size={14} /> Начислить бонусы</button></div></div>{analytics && <div className="panel-section client-analytics-section"><div className="operation-heading"><h3>Статистика клиента</h3><span>Последние 30 дней</span></div><div className="client-analytics-grid"><div><strong>{analytics.played_hours.toLocaleString("ru-RU")} ч</strong><span>Игровое время</span></div><div><strong>{analytics.session_count}</strong><span>Сессий</span></div><div><strong>{money(analytics.total_spend_cents)}</strong><span>Всего потрачено</span></div><div><strong>{analytics.average_session_minutes.toLocaleString("ru-RU")} мин</strong><span>Средняя сессия</span></div><div><strong>{money(analytics.product_spend_cents)}</strong><span>Товары</span></div><div><strong>{analytics.product_units}</strong><span>Товаров куплено</span></div></div><div className="client-analytics-meta"><span>Первый визит: {analytics.first_session_at ? new Date(analytics.first_session_at).toLocaleDateString("ru-RU") : "нет данных"}</span><span>Последний визит: {analytics.last_session_at ? new Date(analytics.last_session_at).toLocaleDateString("ru-RU") : "нет данных"}</span></div>{analytics.favorite_products.length > 0 && <div className="client-favorites"><span>Любимые товары</span>{analytics.favorite_products.map((item) => <span className="category-chip" key={item.product_id}>{item.product_name} · {item.units} шт.</span>)}</div>}</div>}{loading && <div className="timeline-empty">Загружаем операции и статистику…</div>}{error && <div className="form-error" role="alert">{error}</div>}<div className="panel-section operation-section"><div className="operation-heading"><h3>История операций</h3><span>{api ? "Последние 20" : "Пример"}</span></div>{!loading && !api && <div className="timeline-empty">Операции появятся после пополнения или списания.</div>}{!loading && api && !operations.length && <div className="timeline-empty">Операций пока нет</div>}{operations.map((operation) => <div className="operation-row" key={operation.id}><div className={`operation-icon ${operation.amount_cents >= 0 ? "income" : "expense"}`}>{operation.amount_cents >= 0 ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}</div><div><strong>{operation.reason || (operation.operation_type === "top_up" ? "Пополнение" : "Списание")}</strong><span>{new Date(operation.created_at).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}{operation.bonus_amount ? ` · бонус +${operation.bonus_amount} ₽` : ""}</span></div><b className={operation.amount_cents >= 0 ? "income-text" : "expense-text"}>{operation.amount_cents >= 0 ? "+" : ""}{(operation.amount_cents / 100).toLocaleString("ru-RU")} ₽</b></div>)}</div><button className="danger-button client-delete-button" onClick={() => void remove()} disabled={!api || saving}>Удалить клиента <ChevronRight size={15} /></button></div>;
}

function NewClientPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
  const [nickname, setNickname] = useState("");
  const [phone, setPhone] = useState("");
  const [category, setCategory] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (nickname.trim().length < 3) {
      setError("Ник должен содержать минимум 3 символа");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createClient({
        nickname: nickname.trim(),
        phone: phone.trim() || undefined,
        discount_category: category.trim() || undefined,
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать клиента");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Новый клиент" subtitle="CRM · профиль клиента" onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Ник<input value={nickname} onChange={(event) => setNickname(event.target.value)} placeholder="night_walker" autoFocus /></label><label>Телефон<input type="tel" inputMode="tel" value={phone} onChange={(event) => setPhone(formatRussianPhone(event.target.value))} placeholder="+7 (999) 000-00-00" /></label><label>Категория скидки<input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="student" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Создаём..." : "Создать клиента"}</button><p className="subheading">Телефон сохраняется в едином формате +7XXXXXXXXXX.</p></form></div>;
}

function LegacyCatalogView({ api, groups, refreshKey, onNewTariff, onNewProduct, onNewDiscount }: { api?: GameClubApi; groups: BackendWorkstationGroup[]; refreshKey: number; onNewTariff?: () => void; onNewProduct?: () => void; onNewDiscount?: () => void }) {
  const [tariffs, setTariffs] = useState<Awaited<ReturnType<GameClubApi["listTariffs"]>>>([]);
  const [discountRules, setDiscountRules] = useState<Awaited<ReturnType<GameClubApi["listDiscountRules"]>>>([]);
  const [products, setProducts] = useState<Awaited<ReturnType<GameClubApi["listProducts"]>>>([]);
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lifecycleId, setLifecycleId] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      return undefined;
    }
    let active = true;
    Promise.all([api.listTariffs(), api.listDiscountRules(), api.listProducts(), api.listProductCategories()]).then(([items, rules, productItems, categoryItems]) => {
      if (active) {
        setTariffs(items);
        setDiscountRules(rules);
        setProducts(productItems);
        setCategories(categoryItems);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить тарифы");
      }
    });
    return () => {
      active = false;
    };
  }, [api, refreshKey]);

  const updateLifecycle = async (tariff: Awaited<ReturnType<GameClubApi["listTariffs"]>>[number]) => {
    if (!api) {
      return;
    }
    setLifecycleId(tariff.id);
    setError(null);
    try {
      const updated = tariff.lifecycle === "draft"
        ? await api.publishTariff(tariff.id)
        : await api.archiveTariff(tariff.id);
      setTariffs((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить тариф");
    } finally {
      setLifecycleId(null);
    }
  };

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const groupLabel = (groupId: string | null) => groups.find((group) => group.id === groupId)?.name ?? (groupId === "vip" ? "VIP-зона" : groupId === "main" ? "Обычный зал" : groupId ? groupId : "Все зоны");

  if (!api) {
    return <><div className="page-heading"><div><p className="eyebrow">Настройки клуба</p><h1>Каталог и тарифы</h1><p className="subheading">Управляйте товарами, игровым временем и правилами цены.</p></div><button className="primary-button" disabled={!onNewTariff} onClick={onNewTariff}><Plus size={17} /> Добавить тариф</button></div><div className="catalog-grid"><div className="catalog-card featured"><div className="catalog-card-head"><div className="metric-icon violet"><Sparkles size={18} /></div><span className="active-chip">Активен</span></div><h3>VIP · Будни</h3><p>Понедельник — пятница · VIP-зона</p><div className="tariff-price">450 ₽ <span>/ час</span></div><div className="catalog-card-footer"><span>Изменён сегодня</span><MoreHorizontal size={17} /></div></div><div className="catalog-card"><div className="catalog-card-head"><div className="metric-icon blue"><Clock3 size={18} /></div><span className="active-chip">Активен</span></div><h3>Обычный зал · Стандарт</h3><p>Все дни · Обычный зал</p><div className="tariff-price">180 ₽ <span>/ час</span></div><div className="catalog-card-footer"><span>Изменён 2 дня назад</span><MoreHorizontal size={17} /></div></div><div className="catalog-card add-card"><Plus size={22} /><strong>Добавить тариф</strong><span>Настроить новое правило</span></div></div></>;
  }

  return <><div className="page-heading"><div><p className="eyebrow">Настройки клуба · Backend</p><h1>Каталог и тарифы</h1><p className="subheading">Активные правила цены и игрового времени.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onNewProduct}><Plus size={15} /> Товар</button><button className="primary-button" onClick={onNewTariff}><Plus size={17} /> Добавить тариф</button></div></div>{error && <div className="search-hint error" role="alert">{error}</div>}<div className="catalog-grid">{tariffs.map((tariff, index) => <div className={`catalog-card ${index === 0 ? "featured" : ""}`} key={tariff.id}><div className="catalog-card-head"><div className={`metric-icon ${index === 0 ? "violet" : "blue"}`}><Clock3 size={18} /></div><span className={`active-chip ${tariff.lifecycle === "published" ? "" : "inactive"}`}>{tariff.lifecycle === "published" ? "Опубликован" : tariff.lifecycle === "draft" ? "Черновик" : "Архив"}</span></div><h3>{tariff.name}</h3><p>{groupLabel(tariff.group_id)} · {tariff.duration_minutes} минут · v{tariff.version}</p><div className="tariff-price">{money(tariff.price_cents)} <span>/ период</span></div><div className="catalog-card-footer"><span>С {new Date(tariff.valid_from).toLocaleDateString("ru-RU")}</span>{tariff.lifecycle !== "archived" && <button className="text-button" disabled={lifecycleId === tariff.id} onClick={() => void updateLifecycle(tariff)}>{lifecycleId === tariff.id ? "Сохраняем..." : tariff.lifecycle === "draft" ? "Опубликовать" : "Архивировать"}</button>}</div></div>)}{!tariffs.length && <div className="catalog-card add-card"><Clock3 size={22} /><strong>Тарифов пока нет</strong><span>Создайте первое правило цены</span></div>}</div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Товары</h3><p>Позиции для будущего заказа и кассы</p></div><button className="text-button" onClick={onNewProduct}><Plus size={15} /> Добавить</button></div>{products.length ? products.map((product) => <div className="product-row" key={product.id}><div><strong>{product.name}</strong><span>{categories.find((category) => category.id === product.category)?.name ?? product.category}</span></div><b>{money(product.price_cents)}</b><span className="active-chip">{product.active ? "Активен" : "Выключен"}</span></div>) : <div className="timeline-empty">Товаров пока нет</div>}</div><ProductCategoryManager api={api} categories={categories} onCategoriesChange={setCategories} /><div className="white-card discount-rules-card"><div className="card-heading"><div><h3>Категории скидок</h3><p>Правила применяются backend quote-расчётом</p></div><button className="text-button" onClick={onNewDiscount}><Plus size={15} /> Настроить</button></div>{discountRules.length ? discountRules.map((rule) => <div className="discount-rule-row" key={rule.id}><div><strong>{rule.category}</strong><span>Приоритет {rule.priority}</span></div><b>{(rule.percent_bps / 100).toLocaleString("ru-RU")}%</b><span className="active-chip">{rule.active ? "Активна" : "Выключена"}</span></div>) : <div className="timeline-empty">Категорий скидок пока нет</div>}</div></>;
}

function CatalogView({ api, groups, refreshKey, onNewTariff, onNewProduct, onEditProduct, onSellProduct, onNewDiscount }: { api?: GameClubApi; groups: BackendWorkstationGroup[]; refreshKey: number; onNewTariff?: () => void; onNewProduct?: () => void; onEditProduct?: (product: BackendProduct) => void; onSellProduct?: (product: BackendProduct) => void; onNewDiscount?: () => void }) {
  const [tariffs, setTariffs] = useState<Awaited<ReturnType<GameClubApi["listTariffs"]>>>([]);
  const [discountRules, setDiscountRules] = useState<Awaited<ReturnType<GameClubApi["listDiscountRules"]>>>([]);
  const [products, setProducts] = useState<BackendProduct[]>([]);
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [mode, setMode] = useState<"all" | "tariffs" | "products">("all");
  const [categoryId, setCategoryId] = useState("all");
  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [showArchivedTariffs, setShowArchivedTariffs] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lifecycleId, setLifecycleId] = useState<string | null>(null);

  useEffect(() => {
    if (!api) return undefined;
    let active = true;
    void Promise.all([api.listTariffs(), api.listDiscountRules(), api.listProducts(), api.listProductCategories()]).then(([tariffItems, ruleItems, productItems, categoryItems]) => {
      if (active) {
        setTariffs(tariffItems);
        setDiscountRules(ruleItems);
        setProducts(productItems);
        setCategories(categoryItems);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить каталог");
    });
    return () => { active = false; };
  }, [api, refreshKey]);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const groupLabel = (groupId: string | null) => groups.find((group) => group.id === groupId)?.name ?? (groupId === "vip" ? "VIP-зона" : groupId === "main" ? "Обычный зал" : groupId || "Все зоны");
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? id;
  const visibleProducts = categoryId === "all" ? products : products.filter((product) => product.category === categoryId);
  const visibleTariffs = showArchivedTariffs ? tariffs : tariffs.filter((tariff) => tariff.lifecycle !== "archived");
  const updateLifecycle = async (tariff: (typeof tariffs)[number]) => {
    if (!api) return;
    setLifecycleId(tariff.id);
    try {
      const updated = tariff.lifecycle === "draft" ? await api.publishTariff(tariff.id) : await api.archiveTariff(tariff.id);
      setTariffs((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить тариф");
    } finally {
      setLifecycleId(null);
    }
  };

  if (!api) return <div className="catalog-empty-state"><p className="eyebrow">Настройки клуба</p><h1>Каталог</h1><p className="subheading">Live-режим подключает тарифы, товары, категории и складские остатки.</p></div>;
  return <><div className="page-heading"><div><p className="eyebrow">Операции · Каталог</p><h1>Каталог клуба</h1><p className="subheading">Тарифы времени, товары и остатки — в одном рабочем списке.</p></div><div className="heading-actions"><button className="secondary-button" onClick={() => setCategoryModalOpen(true)}><Settings size={15} /> Категории</button><button className="secondary-button" onClick={onNewProduct}><Plus size={15} /> Товар</button><button className="primary-button" onClick={onNewTariff}><Plus size={17} /> Тариф</button></div></div>{error && <div className="search-hint error" role="alert">{error}</div>}<div className="catalog-summary"><div><span>Тарифы</span><strong>{tariffs.filter((item) => item.lifecycle === "published").length}</strong><small>опубликовано</small></div><div><span>Товары</span><strong>{products.length}</strong><small>позиций</small></div><div><span>Категории</span><strong>{categories.length}</strong><small>групп каталога</small></div><div><span>Скидки</span><strong>{discountRules.length}</strong><small>активных правил</small></div></div><div className="catalog-toolbar"><div className="compact-tabs" role="tablist" aria-label="Тип позиции"><button className={mode === "all" ? "selected" : ""} role="tab" aria-selected={mode === "all"} onClick={() => setMode("all")}>Все позиции</button><button className={mode === "tariffs" ? "selected" : ""} role="tab" aria-selected={mode === "tariffs"} onClick={() => setMode("tariffs")}>Тарифы</button><button className={mode === "products" ? "selected" : ""} role="tab" aria-selected={mode === "products"} onClick={() => setMode("products")}>Товары</button></div><select className="catalog-category-filter" aria-label="Фильтр категории товара" value={categoryId} onChange={(event) => setCategoryId(event.target.value)}><option value="all">Все категории</option>{categories.map((category) => <option value={category.id} key={category.id}>{category.name}</option>)}</select><span className="catalog-breadcrumb">Каталог <ChevronRight size={13} /> {mode === "all" ? "Все позиции" : mode === "tariffs" ? "Тарифы времени" : "Товары и напитки"}</span><button className={`archive-toggle ${showArchivedTariffs ? "active" : ""}`} type="button" aria-pressed={showArchivedTariffs} onClick={() => setShowArchivedTariffs((value) => !value)}>{showArchivedTariffs ? "Скрыть архивные" : "Показать архивные"}</button></div>{mode !== "products" && <section className="catalog-section"><div className="section-row"><div><h2>Тарифы времени</h2><p className="section-caption">{showArchivedTariffs ? "Активные, черновики и архивные версии." : "Активные и черновики · архивные скрыты."}</p></div><button className="text-button" onClick={onNewTariff}><Plus size={14} /> Новый тариф</button></div><div className="tariff-mini-grid">{visibleTariffs.map((tariff) => <article className={`tariff-mini-card ${tariff.lifecycle === "published" ? "" : "muted"}`} key={tariff.id}><div className="tariff-mini-top"><span className="tariff-type"><Clock3 size={13} /> Тариф</span><span className={`active-chip ${tariff.lifecycle === "published" ? "" : "inactive"}`}>{tariff.lifecycle === "published" ? "Активен" : tariff.lifecycle === "draft" ? "Черновик" : "Архив"}</span></div><h3>{tariff.name}</h3><p>{groupLabel(tariff.group_id)} · {tariff.duration_minutes} мин · v{tariff.version}</p><strong>{money(tariff.price_cents)}</strong><div className="tariff-mini-actions">{tariff.lifecycle !== "archived" && <button className="text-button" disabled={lifecycleId === tariff.id} onClick={() => void updateLifecycle(tariff)}>{tariff.lifecycle === "draft" ? "Опубликовать" : "Архивировать"}</button>}</div></article>)}{!visibleTariffs.length && <div className="empty-state-card">{tariffs.length ? "Архивные тарифы скрыты. Нажмите «Показать архивные», чтобы просмотреть историю." : "Тарифов пока нет. Создайте первое правило времени."}</div>}</div></section>}{mode !== "tariffs" && <section className="catalog-section"><div className="section-row"><div><h2>Товары и напитки</h2><p className="section-caption">Тип, цена продажи, закупочная цена и текущий остаток.</p></div><button className="text-button" onClick={onNewProduct}><Plus size={14} /> Добавить товар</button></div><div className="product-table"><div className="product-table-head"><span>Позиция</span><span>Тип</span><span>Продажа</span><span>Закупка</span><span>Остаток</span><span>Действия</span></div>{visibleProducts.map((product) => <div className="product-table-row" key={product.id}><div><strong>{product.name}</strong><small>{categoryName(product.category)}</small></div><span className="product-kind-chip">{categories.find((category) => category.id === product.category)?.kind === "drink" ? "Напиток" : "Товар"}</span><strong>{money(product.price_cents)}</strong><span>{money(product.cost_price_cents)}</span><span className={product.stock_quantity <= 5 ? "stock-low" : "stock-ok"}>{product.stock_quantity} шт.</span><div className="product-row-actions"><button className="secondary-button compact-action" aria-label={`Продать товар ${product.name}`} onClick={() => onSellProduct?.(product)} disabled={!onSellProduct || !product.active || product.stock_quantity < 1}><ShoppingCart size={13} /> Продать</button><button className="icon-button small" aria-label={`Редактировать товар ${product.name}`} onClick={() => onEditProduct?.(product)}><Edit3 size={14} /></button></div></div>)}{!visibleProducts.length && <div className="empty-state-card">По выбранной категории товаров нет.</div>}</div></section>}<section className="catalog-section discount-section"><div className="section-row"><div><h2>Скидки клиентов</h2><p className="section-caption">Категория клиента применяется backend-расчётом при продаже времени.</p></div><button className="text-button" onClick={onNewDiscount}><Plus size={14} /> Новое правило</button></div>{discountRules.length ? <div className="discount-compact-list">{discountRules.map((rule) => <div className="discount-compact-row" key={rule.id}><span className="product-kind-chip">{rule.category}</span><strong>{(rule.percent_bps / 100).toLocaleString("ru-RU")}%</strong><span>Приоритет {rule.priority}</span><span className="active-chip">{rule.active ? "Активна" : "Отключена"}</span></div>)}</div> : <div className="empty-state-card">Правил скидок пока нет.</div>}</section>{categoryModalOpen && <div className="modal-backdrop" role="presentation" onClick={() => setCategoryModalOpen(false)}><div className="modal-card" role="dialog" aria-modal="true" aria-label="Категории товаров и напитков" onClick={(event) => event.stopPropagation()}><div className="modal-card-head"><div><p className="eyebrow">Каталог</p><h2>Категории</h2></div><button className="icon-button" aria-label="Закрыть категории" onClick={() => setCategoryModalOpen(false)}><X size={18} /></button></div><ProductCategoryManager api={api} categories={categories} onCategoriesChange={setCategories} /></div></div>}</>;
}

function ProductCategoryManager({ api, categories, onCategoriesChange }: { api: GameClubApi; categories: BackendProductCategory[]; onCategoriesChange: (categories: BackendProductCategory[]) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BackendProductCategory["kind"]>("product");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [editingKind, setEditingKind] = useState<BackendProductCategory["kind"]>("product");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const create = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Укажите название категории");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.createProductCategory({ name: name.trim(), kind });
      onCategoriesChange([...categories, created]);
      setName("");
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать категорию");
    } finally {
      setSaving(false);
    }
  };

  const save = async (category: BackendProductCategory) => {
    if (!editingName.trim()) {
      setError("Название категории не может быть пустым");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateProductCategory(category.id, { name: editingName.trim(), kind: editingKind });
      onCategoriesChange(categories.map((item) => item.id === updated.id ? updated : item));
      setEditingId(null);
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить категорию");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (category: BackendProductCategory) => {
    if (!window.confirm(`Удалить категорию «${category.name}»? Товары не удаляются.`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteProductCategory(category.id);
      onCategoriesChange(categories.filter((item) => item.id !== category.id));
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить категорию");
    } finally {
      setSaving(false);
    }
  };

  return <div className="white-card product-list-card category-manager"><div className="card-heading"><div><h3>Категории товаров и напитков</h3><p>Создавайте, переименовывайте и удаляйте группы каталога.</p></div><span className="active-chip">{categories.length}</span></div><form className="category-create-form" onSubmit={(event) => void create(event)}><input aria-label="Название новой категории" value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Напитки" /><select aria-label="Тип новой категории" value={kind} onChange={(event) => setKind(event.target.value as BackendProductCategory["kind"])}><option value="product">Товары</option><option value="drink">Напитки</option></select><button className="secondary-button" disabled={saving}><Plus size={15} /> Добавить</button></form>{error && <div className="form-error" role="alert">{error}</div>}{categories.map((category) => editingId === category.id ? <div className="category-row" key={category.id}><input aria-label="Название категории" value={editingName} onChange={(event) => setEditingName(event.target.value)} /><select aria-label="Тип категории" value={editingKind} onChange={(event) => setEditingKind(event.target.value as BackendProductCategory["kind"])}><option value="product">Товары</option><option value="drink">Напитки</option></select><button className="text-button" disabled={saving} onClick={() => void save(category)}>Сохранить</button><button className="icon-button" aria-label="Отменить редактирование" onClick={() => setEditingId(null)}><X size={15} /></button></div> : <div className="category-row" key={category.id}><div><strong>{category.name}</strong><span>{category.kind === "drink" ? "Напитки" : "Товары"} · {category.id}</span></div><button className="text-button" onClick={() => { setEditingId(category.id); setEditingName(category.name); setEditingKind(category.kind); }}>Изменить</button><button className="text-button danger-text" disabled={saving} onClick={() => void remove(category)}>Удалить</button></div>)}{!categories.length && <div className="timeline-empty">Категорий пока нет — создайте первую выше.</div>}</div>;
}

const themeLabels: Record<BackendWorkstationGroup["theme"], string> = {
  standard: "Обычный зал",
  vip: "VIP-зона",
  neon: "Неон",
  minimal: "Минимал",
};

const cashDirectionLabels: Record<BackendCashMovement["direction"], string> = {
  cash_in: "Приход",
  cash_out: "Расход",
  correction: "Корректировка",
};

function cashMoney(cents: number): string {
  return `${(cents / 100).toLocaleString("ru-RU")} ₽`;
}

function cashIdempotencyKey(prefix: string): string {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
}

function CashScheduleEditor({ api, schedule, onSaved, onCancel }: { api: GameClubApi; schedule?: BackendCashShiftSchedule; onSaved: (schedule: BackendCashShiftSchedule) => void; onCancel?: () => void }) {
  const [registerId, setRegisterId] = useState(schedule?.register_id ?? "front-desk");
  const [timezone, setTimezone] = useState(schedule?.timezone ?? "Europe/Moscow");
  const [autoOpen, setAutoOpen] = useState(schedule?.auto_open ?? false);
  const [autoOpenAt, setAutoOpenAt] = useState(schedule?.auto_open_at?.slice(0, 5) ?? "10:00");
  const [autoClose, setAutoClose] = useState(schedule?.auto_close ?? false);
  const [autoCloseAt, setAutoCloseAt] = useState(schedule?.auto_close_at?.slice(0, 5) ?? "23:59");
  const [openingBalance, setOpeningBalance] = useState(((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRegisterId(schedule?.register_id ?? "front-desk");
    setTimezone(schedule?.timezone ?? "Europe/Moscow");
    setAutoOpen(schedule?.auto_open ?? false);
    setAutoOpenAt(schedule?.auto_open_at?.slice(0, 5) ?? "10:00");
    setAutoClose(schedule?.auto_close ?? false);
    setAutoCloseAt(schedule?.auto_close_at?.slice(0, 5) ?? "23:59");
    setOpeningBalance(((schedule?.opening_balance_cents ?? 0) / 100).toFixed(2));
  }, [schedule]);

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const opening = Number(openingBalance);
    if (!registerId.trim() || !timezone.trim() || !Number.isFinite(opening) || opening < 0 || (autoOpen && !autoOpenAt) || (autoClose && !autoCloseAt)) {
      setError("Заполните register, часовой пояс и время включённых правил");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await api.saveCashShiftSchedule(registerId.trim(), {
        timezone: timezone.trim(),
        auto_open: autoOpen,
        auto_open_at: autoOpen ? autoOpenAt : null,
        auto_close: autoClose,
        auto_close_at: autoClose ? autoCloseAt : null,
        opening_balance_cents: Math.round(opening * 100),
      });
      onSaved(saved);
      onCancel?.();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить расписание");
    } finally {
      setSaving(false);
    }
  };

  return <form className="schedule-editor" onSubmit={(event) => void save(event)}><div className="schedule-editor-head"><div><strong>{schedule ? `Register · ${schedule.register_id}` : "Новая касса"}</strong><span>{schedule ? "Расписание можно изменить в любое время" : "Автоматические правила применятся после сохранения"}</span></div>{onCancel && <button type="button" className="icon-button" aria-label="Отменить добавление кассы" onClick={onCancel}><X size={16} /></button>}</div><div className="schedule-fields"><label>Register<input value={registerId} onChange={(event) => setRegisterId(event.target.value)} disabled={Boolean(schedule)} /></label><label>Часовой пояс<input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Europe/Moscow" /></label><label>Остаток при автооткрытии, ₽<input type="number" min="0" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /></label></div><div className="schedule-rules"><label className="schedule-toggle"><input type="checkbox" checked={autoOpen} onChange={(event) => setAutoOpen(event.target.checked)} /><span><strong>Автооткрытие</strong><small>Открыть смену в начале рабочего дня</small></span><DateTimePicker value={autoOpenAt} onChange={setAutoOpenAt} mode="time" label="Время автооткрытия" disabled={!autoOpen} className="schedule-time-picker" /></label><label className="schedule-toggle"><input type="checkbox" checked={autoClose} onChange={(event) => setAutoClose(event.target.checked)} /><span><strong>Автозакрытие</strong><small>Закрыть смену в конце рабочего дня</small></span><DateTimePicker value={autoCloseAt} onChange={setAutoCloseAt} mode="time" label="Время автозакрытия" disabled={!autoClose} className="schedule-time-picker" /></label></div>{error && <div className="form-error" role="alert">{error}</div>}<div className="schedule-editor-actions"><button className="primary-button" disabled={saving}>{saving ? "Сохраняем..." : "Сохранить расписание"}</button>{onCancel && <button type="button" className="secondary-button" onClick={onCancel}>Отмена</button>}</div></form>;
}

function CashView({
  api,
  shifts,
  onOpenShift,
  onRecordMovement,
  onCloseShift,
}: {
  api?: GameClubApi;
  shifts: BackendCashShift[];
  onOpenShift?: () => void;
  onRecordMovement?: (shift: BackendCashShift) => void;
  onCloseShift?: (shift: BackendCashShift) => void;
}) {
  const [movements, setMovements] = useState<BackendCashMovement[]>([]);
  const [schedules, setSchedules] = useState<BackendCashShiftSchedule[]>([]);
  const [addingSchedule, setAddingSchedule] = useState(false);
  const [movementError, setMovementError] = useState<string | null>(null);
  const openShift = shifts.find((shift) => shift.status === "open");

  useEffect(() => {
    if (!api) {
      setSchedules([]);
      return undefined;
    }
    let active = true;
    void api.listCashShiftSchedules().then((items) => {
      if (active) setSchedules(items);
    }).catch(() => {
      if (active) setSchedules([]);
    });
    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => {
    if (!api || !openShift) {
      setMovements([]);
      return undefined;
    }
    let active = true;
    void api.listCashMovements(openShift.id).then((items) => {
      if (active) {
        setMovements(items);
        setMovementError(null);
      }
    }).catch((error) => {
      if (active) {
        setMovementError(error instanceof ApiError ? error.message : "Не удалось загрузить движения");
      }
    });
    return () => {
      active = false;
    };
  }, [api, openShift?.id, shifts]);

  if (!api) {
    return <><div className="page-heading"><div><p className="eyebrow">Финансы · Демонстрация</p><h1>Касса</h1><p className="subheading">Открытие смены, наличные движения и закрытие дня.</p></div></div><div className="white-card product-list-card"><div className="timeline-empty">Подключите live-режим, чтобы управлять кассовой сменой через backend.</div></div></>;
  }

  return <><div className="page-heading"><div><p className="eyebrow">Финансы · Сегодня</p><h1>Касса</h1><p className="subheading">Наличный ledger отделён от клиентских депозитов и session charge.</p></div><button className="primary-button" disabled={Boolean(openShift)} onClick={onOpenShift}><Plus size={17} /> Открыть смену</button></div>{openShift ? <div className="white-card product-list-card"><div className="card-heading"><div><h3>Смена · {openShift.register_id}</h3><p>Открыта {new Date(openShift.opened_at).toLocaleString("ru-RU")} · {openShift.opened_by}</p></div><span className="active-chip">Открыта</span></div><div className="cash-summary-grid"><div><span>В начале</span><strong>{cashMoney(openShift.opening_balance_cents)}</strong></div><div><span>Ожидается</span><strong>{cashMoney(openShift.expected_close_cents)}</strong></div><div><span>Разница</span><strong>—</strong></div></div><div className="panel-actions"><button className="secondary-button" onClick={() => onRecordMovement?.(openShift)}><Plus size={15} /> Движение</button><button className="primary-button" onClick={() => onCloseShift?.(openShift)}>Закрыть смену</button></div><div className="operation-section"><div className="operation-heading"><h3>Последние движения</h3><span>{movements.length}</span></div>{movementError && <div className="form-error" role="alert">{movementError}</div>}{!movementError && !movements.length && <div className="timeline-empty">Движений пока нет</div>}{movements.map((movement) => <div className="operation-row" key={movement.id}><div className={`operation-icon ${movement.direction === "cash_out" ? "expense" : "income"}`}><Banknote size={14} /></div><div><strong>{cashDirectionLabels[movement.direction]}</strong><span>{movement.reason} · {new Date(movement.created_at).toLocaleString("ru-RU")}</span></div><b className={movement.direction === "cash_out" || movement.amount_cents < 0 ? "expense-text" : "income-text"}>{movement.direction === "cash_out" ? "-" : movement.amount_cents > 0 ? "+" : ""}{cashMoney(Math.abs(movement.amount_cents))}</b></div>)}</div></div> : <div className="white-card product-list-card"><div className="timeline-empty"><Banknote size={20} /><strong>Открытой смены нет</strong><span>Откройте смену перед приёмом наличных.</span></div></div>}<div className="white-card product-list-card schedule-card"><div className="card-heading"><div><h3>Автоматизация смен</h3><p>Ручное открытие и закрытие остаются доступными всегда.</p></div><button className="secondary-button" onClick={() => setAddingSchedule(true)} disabled={addingSchedule}><Plus size={15} /> Добавить кассу</button></div><div className="schedule-note"><Settings size={15} /><span>Автозакрытие использует ожидаемый остаток из ledger. Фактический пересчёт наличных оператор подтверждает вручную.</span></div>{schedules.map((schedule) => <CashScheduleEditor key={schedule.register_id} api={api} schedule={schedule} onSaved={(saved) => setSchedules((items) => items.map((item) => item.register_id === saved.register_id ? saved : item))} />)}{addingSchedule && <CashScheduleEditor api={api} onSaved={(saved) => { setSchedules((items) => [...items, saved]); setAddingSchedule(false); }} onCancel={() => setAddingSchedule(false)} />}{!schedules.length && !addingSchedule && <div className="timeline-empty">Авторасписаний пока нет. Ручное управление сменой уже доступно выше.</div>}</div><div className="white-card product-list-card"><div className="card-heading"><div><h3>История смен</h3><p>Закрытые смены доступны только для чтения.</p></div></div>{shifts.filter((shift) => shift.status === "closed").map((shift) => <div className="settings-row" key={shift.id}><div><strong>{shift.register_id}</strong><span>{new Date(shift.opened_at).toLocaleDateString("ru-RU")} · закрыта {shift.closed_at ? new Date(shift.closed_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "—"}</span></div><b>{shift.difference_cents === null ? "—" : `${shift.difference_cents >= 0 ? "+" : ""}${cashMoney(shift.difference_cents)}`}</b><span className="active-chip">Закрыта</span></div>)}{!shifts.some((shift) => shift.status === "closed") && <div className="timeline-empty">Закрытых смен пока нет</div>}</div></>;
}

function CashOpenPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
  const [registerId, setRegisterId] = useState("front-desk");
  const [openingBalance, setOpeningBalance] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(openingBalance);
    if (!registerId.trim() || !Number.isFinite(rubles) || rubles < 0) {
      setError("Укажите register и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.openCashShift(
        { register_id: registerId.trim(), opening_balance_cents: Math.round(rubles * 100) },
        cashIdempotencyKey("cash-open"),
      );
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось открыть смену");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Открыть смену" subtitle="Касса · новый рабочий день" onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Register<input value={registerId} onChange={(event) => setRegisterId(event.target.value)} autoFocus /></label><label>Остаток на начало, ₽<input type="number" min="0" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Открываем..." : "Открыть смену"}</button><p className="subheading">Для одного register одновременно допускается только одна открытая смена.</p></form></div>;
}

function CashMovementPanel({ api, shift, onClose, onSaved }: { api: GameClubApi; shift: BackendCashShift; onClose: () => void; onSaved: () => void }) {
  const [direction, setDirection] = useState<BackendCashMovement["direction"]>("cash_in");
  const [amount, setAmount] = useState("0");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operationKey] = useState(() => cashIdempotencyKey("cash-movement"));

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(amount);
    if (!Number.isFinite(rubles) || (direction !== "correction" && rubles <= 0) || (direction === "correction" && rubles === 0) || !reason.trim()) {
      setError("Укажите сумму и причину движения");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { direction, amount_cents: Math.round(rubles * 100), reason: reason.trim() };
      const approval = direction === "correction"
        ? await api.createCashApproval(
            shift.id,
            { kind: "correction", target_key: operationKey, reason: `Одобрение: ${reason.trim()}` },
            `approval-${operationKey}`,
          )
        : undefined;
      await api.recordCashMovement(shift.id, { ...payload, approval_id: approval?.id }, operationKey);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось записать движение");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Движение наличных" subtitle={`Смена · ${shift.register_id}`} onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Тип<select value={direction} onChange={(event) => setDirection(event.target.value as BackendCashMovement["direction"])}><option value="cash_in">Приход</option><option value="cash_out">Расход</option><option value="correction">Корректировка</option></select></label>{direction === "correction" && <p className="subheading">Для корректировки автоматически запрашивается отдельное supervisor approval и сохраняется audit.</p>}<label>Сумма, ₽<input type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} /></label><label>Причина<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Приём наличных" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Записать движение"}</button></form></div>;
}

function CashClosePanel({ api, shift, onClose, onSaved }: { api: GameClubApi; shift: BackendCashShift; onClose: () => void; onSaved: () => void }) {
  const [actualBalance, setActualBalance] = useState((shift.expected_close_cents / 100).toFixed(2));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [operationKey] = useState(() => cashIdempotencyKey("cash-close"));

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const rubles = Number(actualBalance);
    if (!Number.isFinite(rubles) || rubles < 0) {
      setError("Укажите корректный фактический остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const actualCloseCents = Math.round(rubles * 100);
      const approval = actualCloseCents !== shift.expected_close_cents
        ? await api.createCashApproval(
            shift.id,
            { kind: "close_difference", target_key: operationKey, reason: "Supervisor verified the final count" },
            `approval-${operationKey}`,
          )
        : undefined;
      await api.closeCashShift(shift.id, actualCloseCents, operationKey, approval?.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось закрыть смену");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Закрыть смену" subtitle={`Смена · ${shift.register_id}`} onClose={onClose} /><form className="booking-form" onSubmit={submit}><div className="detail-row"><span>Ожидаемый остаток</span><strong>{cashMoney(shift.expected_close_cents)}</strong></div><label>Фактический остаток, ₽<input type="number" min="0" step="0.01" value={actualBalance} onChange={(event) => setActualBalance(event.target.value)} autoFocus /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Закрываем..." : "Закрыть смену"}</button><p className="subheading">После закрытия смена становится неизменяемой; расхождение сохраняется в ledger.</p></form></div>;
}

function SettingsView({ api, pcs, refreshKey, onNewGroup, onEditGroup, onNewPaymentMethod, onEditPaymentMethod }: { api?: GameClubApi; pcs: Workstation[]; refreshKey: number; onNewGroup?: () => void; onEditGroup?: (group: BackendWorkstationGroup) => void; onNewPaymentMethod?: () => void; onEditPaymentMethod?: (method: BackendPaymentMethod) => void }) {
  const [groups, setGroups] = useState<BackendWorkstationGroup[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<BackendPaymentMethod[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api) {
      return undefined;
    }
    let active = true;
    Promise.all([api.listWorkstationGroups(), api.listPaymentMethods()]).then(([groupItems, methodItems]) => {
      if (active) {
        setGroups(groupItems);
        setPaymentMethods(methodItems);
        setError(null);
      }
    }).catch((requestError) => {
      if (active) {
        setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить настройки");
      }
    });
    return () => {
      active = false;
    };
  }, [api, refreshKey]);

  const knownGroupIds = new Set(groups.map((group) => group.id));
  const legacyGroups = pcs.reduce<BackendWorkstationGroup[]>((items, pc) => {
    if (!pc.groupId || knownGroupIds.has(pc.groupId) || items.some((group) => group.id === pc.groupId)) {
      return items;
    }
    items.push({
      id: pc.groupId,
      name: pc.group,
      theme: pc.groupId.toLowerCase().includes("vip") ? "vip" : "standard",
      updated_at: null,
    });
    return items;
  }, []);
  const visibleGroups = [...groups, ...legacyGroups];

  if (!api) {
    return <><div className="page-heading"><div><p className="eyebrow">Конфигурация клуба</p><h1>Настройки</h1><p className="subheading">Группы ПК, темы Windows-клиента и способы оплаты.</p></div></div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Темы групп</h3><p>В live-режиме здесь сохраняются настройки backend.</p></div></div><div className="settings-row"><div><strong>VIP-зона</strong><span>Тема по умолчанию для демонстрации</span></div><span className="active-chip">VIP-зона</span></div><div className="settings-row"><div><strong>Обычный зал</strong><span>Тема по умолчанию для демонстрации</span></div><span className="active-chip">Обычный зал</span></div></div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Способы оплаты</h3><p>Демо-режим показывает базовые способы оплаты.</p></div></div><div className="settings-row"><div><strong>Баланс клиента</strong><span>balance</span></div><span className="active-chip">Включён</span></div><div className="settings-row"><div><strong>Наличные</strong><span>cash</span></div><span className="active-chip">Включён</span></div></div></>;
  }

  return <><div className="page-heading"><div><p className="eyebrow">Конфигурация клуба · Backend</p><h1>Настройки</h1><p className="subheading">Тема и пароль обслуживания назначаются группе ПК, а способы оплаты управляются отдельно.</p></div><div className="heading-actions"><button className="secondary-button" onClick={onNewPaymentMethod}><Plus size={16} /> Способ оплаты</button><button className="primary-button" onClick={onNewGroup}><Plus size={17} /> Добавить группу</button></div></div>{error && <div className="search-hint error" role="alert">{error}</div>}<div className="white-card product-list-card"><div className="card-heading"><div><h3>Группы игровых мест</h3><p>Изменения сохраняются в backend и применяются без новой версии клиента.</p></div></div>{visibleGroups.length ? visibleGroups.map((group) => <div className="settings-row" key={group.id}><div><strong>{group.name}</strong><span>{group.id} · обновлено {group.updated_at ? new Date(group.updated_at).toLocaleString("ru-RU") : "наследуемая настройка"}</span></div><span className="active-chip">{themeLabels[group.theme]}</span><button className="text-button" onClick={() => onEditGroup?.(group)}>Изменить</button></div>) : <div className="timeline-empty">Группы ещё не настроены</div>}</div><div className="white-card product-list-card"><div className="card-heading"><div><h3>Способы оплаты</h3><p>Настройка справочника для операций клуба. Фактические проводки сейчас используют balance и cash.</p></div><button className="secondary-button" onClick={onNewPaymentMethod}><Plus size={16} /> Добавить</button></div>{paymentMethods.length ? paymentMethods.map((method) => <div className="settings-row payment-method-row" key={method.id}><div><strong>{method.name}</strong><span>{method.key} · порядок {method.sort_order}</span></div><span className={method.active ? "active-chip" : "inactive-chip"}>{method.active ? "Включён" : "Выключен"}</span><button className="text-button" onClick={() => onEditPaymentMethod?.(method)}>Изменить</button></div>) : <div className="timeline-empty">Способы оплаты ещё не настроены</div>}</div><p className="subheading settings-note">Новые способы оплаты сохраняются в настройках. Подключение внешнего провайдера к проведению платежа добавляется отдельным интеграционным модулем.</p></>;
}

function GroupSettingsPanel({ api, group, onClose, onSaved }: { api: GameClubApi; group?: BackendWorkstationGroup; onClose: () => void; onSaved: () => void }) {
  const [groupId, setGroupId] = useState(group?.id ?? "");
  const [name, setName] = useState(group?.name ?? "");
  const [theme, setTheme] = useState<BackendWorkstationGroup["theme"]>(group?.theme ?? "standard");
  const [managerPassword, setManagerPassword] = useState("");
  const [deploymentMode, setDeploymentMode] = useState<BackendLockdownPolicy["deployment_mode"]>(group?.lockdown_policy?.deployment_mode ?? "app_gate");
  const [shellEnabled, setShellEnabled] = useState(group?.lockdown_policy?.shell_enabled ?? true);
  const [userSelfLoginEnabled, setUserSelfLoginEnabled] = useState(group?.lockdown_policy?.user_self_login_enabled ?? true);
  const [lockAfterSession, setLockAfterSession] = useState(group?.lockdown_policy?.lock_after_session ?? true);
  const [restartAfterSession, setRestartAfterSession] = useState(group?.lockdown_policy?.restart_after_session ?? true);
  const [blockExternalStorage, setBlockExternalStorage] = useState(group?.lockdown_policy?.block_external_storage ?? false);
  const [disableStartMenu, setDisableStartMenu] = useState(group?.lockdown_policy?.disable_start_menu ?? false);
  const [disableDesktopSwitching, setDisableDesktopSwitching] = useState(group?.lockdown_policy?.disable_desktop_switching ?? false);
  const [hiddenDrives, setHiddenDrives] = useState((group?.lockdown_policy?.hidden_drives ?? []).join(", "));
  const [blockedWindowRules, setBlockedWindowRules] = useState((group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setGroupId(group?.id ?? "");
    setName(group?.name ?? "");
    setTheme(group?.theme ?? "standard");
    setManagerPassword("");
    setDeploymentMode(group?.lockdown_policy?.deployment_mode ?? "app_gate");
    setShellEnabled(group?.lockdown_policy?.shell_enabled ?? true);
    setUserSelfLoginEnabled(group?.lockdown_policy?.user_self_login_enabled ?? true);
    setLockAfterSession(group?.lockdown_policy?.lock_after_session ?? true);
    setRestartAfterSession(group?.lockdown_policy?.restart_after_session ?? true);
    setBlockExternalStorage(group?.lockdown_policy?.block_external_storage ?? false);
    setDisableStartMenu(group?.lockdown_policy?.disable_start_menu ?? false);
    setDisableDesktopSwitching(group?.lockdown_policy?.disable_desktop_switching ?? false);
    setHiddenDrives((group?.lockdown_policy?.hidden_drives ?? []).join(", "));
    setBlockedWindowRules((group?.lockdown_policy?.blocked_window_rules ?? []).join("\n"));
    setError(null);
  }, [group]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!groupId.trim() || !name.trim()) {
      setError("Укажите идентификатор и название группы");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.saveWorkstationGroup(groupId, { name: name.trim(), theme });
      const policy: BackendLockdownPolicy = {
        deployment_mode: deploymentMode,
        shell_enabled: shellEnabled,
        user_self_login_enabled: userSelfLoginEnabled,
        lock_after_session: lockAfterSession,
        restart_after_session: restartAfterSession,
        hidden_drives: hiddenDrives.split(",").map((item) => item.trim().toUpperCase()).filter(Boolean),
        block_external_storage: blockExternalStorage,
        disable_start_menu: disableStartMenu,
        disable_desktop_switching: disableDesktopSwitching,
        blocked_window_rules: blockedWindowRules.split("\n").map((item) => item.trim()).filter(Boolean),
        allowed_application_ids: group?.lockdown_policy?.allowed_application_ids ?? [],
        version: (group?.lockdown_policy?.version ?? 0) + 1,
      };
      await api.setWorkstationGroupLockdownPolicy(groupId, policy);
      if (managerPassword) {
        await api.setWorkstationGroupManagerPassword(groupId, managerPassword);
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить группу");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Настройки зон" subtitle={group ? "Изменение группы" : "Новая группа ПК"} onClose={onClose} /><form className="booking-form" onSubmit={submit}><label>Идентификатор группы<input value={groupId} onChange={(event) => setGroupId(event.target.value)} placeholder="vip" autoFocus disabled={Boolean(group)} /></label><label>Название группы<input value={name} onChange={(event) => setName(event.target.value)} placeholder="VIP-зона" /></label><label>Тема Windows-клиента<select value={theme} onChange={(event) => setTheme(event.target.value as BackendWorkstationGroup["theme"])}>{Object.entries(themeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><label>Режим блокировки Windows<select value={deploymentMode} onChange={(event) => setDeploymentMode(event.target.value as BackendLockdownPolicy["deployment_mode"])}><option value="app_gate">Только access-gate приложения</option><option value="assigned_access">Assigned Access</option><option value="shell_launcher">Shell Launcher</option></select></label><div className="settings-toggle-list"><label><input type="checkbox" checked={shellEnabled} onChange={(event) => setShellEnabled(event.target.checked)} /> Запускать GameClub shell</label><label><input type="checkbox" checked={userSelfLoginEnabled} onChange={(event) => setUserSelfLoginEnabled(event.target.checked)} /> Разрешить вход пользователя</label><label><input type="checkbox" checked={lockAfterSession} onChange={(event) => setLockAfterSession(event.target.checked)} /> Блокировать после сессии</label><label><input type="checkbox" checked={restartAfterSession} onChange={(event) => setRestartAfterSession(event.target.checked)} /> Перезапускать ПК после сессии</label><label><input type="checkbox" checked={blockExternalStorage} onChange={(event) => setBlockExternalStorage(event.target.checked)} /> Запретить внешние накопители</label><label><input type="checkbox" checked={disableStartMenu} onChange={(event) => setDisableStartMenu(event.target.checked)} /> Ограничить Start Menu</label><label><input type="checkbox" checked={disableDesktopSwitching} onChange={(event) => setDisableDesktopSwitching(event.target.checked)} /> Запретить смену рабочих столов</label></div><label>Скрытые диски<input value={hiddenDrives} onChange={(event) => setHiddenDrives(event.target.value)} placeholder="C:, D:" /></label><label>Блокируемые окна/классы<textarea value={blockedWindowRules} onChange={(event) => setBlockedWindowRules(event.target.value)} placeholder="CabinetWClass\n*cmd*" rows={3} /></label><label>Пароль менеджера Win-клиента<input type="password" value={managerPassword} onChange={(event) => setManagerPassword(event.target.value)} placeholder={group ? "Оставьте пустым без изменений" : "Минимум 8 символов"} autoComplete="new-password" minLength={8} maxLength={128} /></label><p className="subheading">Профиль применяется клиентом только по allowlist. Assigned Access/Shell Launcher требуют отдельного Windows provisioning. Пароль сохраняется как PBKDF2-verifier и передаётся через аутентифицированный heartbeat. Ctrl+Alt+P открывает обслуживание.</p>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Сохранить группу"}</button><p className="subheading">При следующем heartbeat клиент получит тему, policy и обновлённый пароль. Для немедленного изменения темы можно также отправить theme.apply.</p></form></div>;
}

function PaymentMethodPanel({ api, method, onClose, onSaved }: { api: GameClubApi; method?: BackendPaymentMethod; onClose: () => void; onSaved: () => void }) {
  const [key, setKey] = useState(method?.key ?? "");
  const [name, setName] = useState(method?.name ?? "");
  const [active, setActive] = useState(method?.active ?? true);
  const [sortOrder, setSortOrder] = useState(String(method?.sort_order ?? 0));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setKey(method?.key ?? "");
    setName(method?.name ?? "");
    setActive(method?.active ?? true);
    setSortOrder(String(method?.sort_order ?? 0));
    setError(null);
  }, [method]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const parsedOrder = Number(sortOrder);
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(key.trim().toLowerCase()) || !name.trim() || !Number.isInteger(parsedOrder) || parsedOrder < 0) {
      setError("Укажите ключ (латиница, цифры, _ или -), название и порядок сортировки");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { key: key.trim().toLowerCase(), name: name.trim(), active, sort_order: parsedOrder };
      if (method) {
        await api.updatePaymentMethod(method.id, payload);
      } else {
        await api.createPaymentMethod(payload);
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить способ оплаты");
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!method || !window.confirm(`Удалить способ оплаты «${method.name}»?`)) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.deletePaymentMethod(method.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить способ оплаты");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Способ оплаты" subtitle={method ? "Изменение способа оплаты" : "Новый способ оплаты"} onClose={onClose} /><form className="booking-form" onSubmit={(event) => void submit(event)}><label>Системный ключ<input value={key} onChange={(event) => setKey(event.target.value)} placeholder="terminal" autoFocus /></label><label>Название в интерфейсе<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Терминал" /></label><label>Порядок отображения<input type="number" min="0" step="1" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} /></label><label className="settings-checkbox"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Показывать как активный способ</label><p className="subheading">Ключ используется в контракте операций. В текущем checkout подключены встроенные ключи balance и cash; внешний провайдер подключается отдельным модулем.</p>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : method ? "Сохранить изменения" : "Добавить способ оплаты"}</button>{method && <button type="button" className="danger-button" onClick={() => void remove()} disabled={submitting}>Удалить способ оплаты</button>}</form></div>;
}

function TariffPanel({ api, groups, onClose, onSaved }: { api: GameClubApi; groups: BackendWorkstationGroup[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState("main");
  const [duration, setDuration] = useState("60");
  const [price, setPrice] = useState("300");
  const [billingMode, setBillingMode] = useState<"block" | "per_minute">("block");
  const [pricePerMinute, setPricePerMinute] = useState("5");
  const [freeMinutes, setFreeMinutes] = useState("5");
  const [validFrom, setValidFrom] = useState(() => {
    const date = new Date();
    date.setSeconds(0, 0);
    return localDateTimeValue(date);
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const durationMinutes = Number(duration);
    const priceRubles = Number(price);
    const minutePriceRubles = Number(pricePerMinute);
    const free = Number(freeMinutes);
    if (!name.trim() || !Number.isInteger(durationMinutes) || durationMinutes <= 0 || !Number.isFinite(priceRubles) || priceRubles < 0 || billingMode === "per_minute" && (!Number.isFinite(minutePriceRubles) || minutePriceRubles <= 0) || !Number.isInteger(free) || free < 0) {
      setError("Заполните название, длительность и корректную цену");
      return;
    }
    const parsedDate = new Date(validFrom);
    if (Number.isNaN(parsedDate.getTime())) {
      setError("Укажите дату начала действия тарифа");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createTariff({
        name: name.trim(),
        group_id: groupId || null,
        duration_minutes: durationMinutes,
        price_cents: Math.round(priceRubles * 100),
        billing_mode: billingMode,
        price_per_minute_cents: Math.round(minutePriceRubles * 100),
        free_minutes: free,
        valid_from: parsedDate.toISOString(),
        lifecycle: "draft",
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать тариф");
    } finally {
      setSubmitting(false);
    }
  };

  const tariffGroups = groups.length ? groups : [{ id: "main", name: "Обычный зал" }, { id: "vip", name: "VIP-зона" }];
  return <div className="panel-inner"><div className="panel-header"><div><p>Настройки клуба</p><h2>Новый тариф</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Обычный зал · час" autoFocus /></label><label>Зона<select value={groupId} onChange={(event) => setGroupId(event.target.value)}>{tariffGroups.map((group) => <option value={group.id} key={group.id}>{group.name}</option>)}</select></label><div className="compact-tabs tariff-mode-tabs"><button type="button" className={billingMode === "block" ? "selected" : ""} onClick={() => setBillingMode("block")}>Пакет времени</button><button type="button" className={billingMode === "per_minute" ? "selected" : ""} onClick={() => setBillingMode("per_minute")}>Поминутно</button></div><label>Длительность шага, минут<input type="number" min="1" step="1" value={duration} onChange={(event) => setDuration(event.target.value)} /></label>{billingMode === "block" ? <label>Цена пакета, ₽<input type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label> : <div className="form-grid-two"><label>Цена за минуту, ₽<input type="number" min="0.01" step="0.01" value={pricePerMinute} onChange={(event) => setPricePerMinute(event.target.value)} /></label><label>Бесплатно в начале, минут<input type="number" min="0" step="1" value={freeMinutes} onChange={(event) => setFreeMinutes(event.target.value)} /></label></div>}<label>Начало действия<DateTimePicker value={validFrom} onChange={setValidFrom} mode="datetime" label="Начало действия тарифа" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Создать draft-тариф"}</button><p className="subheading">{billingMode === "per_minute" ? "После бесплатного времени backend списывает только поминутную дельту с баланса клиента." : "Количество одинаковых пакетов можно выбрать на карте ПК перед запуском."}</p></form></div>;
}

function LegacyProductPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [price, setPrice] = useState("0");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void api.listProductCategories().then((items) => {
      setCategories(items);
      setCategory((current) => current || items[0]?.id || "");
    }).catch(() => setCategories([]));
  }, [api]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const priceRubles = Number(price);
    if (!name.trim() || !category.trim() || !Number.isFinite(priceRubles) || priceRubles < 0) {
      setError("Заполните название, категорию и корректную цену");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createProduct({
        name: name.trim(),
        category: category.trim(),
        price_cents: Math.round(priceRubles * 100),
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать товар");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><div className="panel-header"><div><p>Каталог</p><h2>Новый товар</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Кофе" autoFocus /></label><label>Категория<select value={category} onChange={(event) => setCategory(event.target.value)} disabled={!categories.length}><option value="">{categories.length ? "Выберите категорию" : "Сначала создайте категорию"}</option>{categories.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.kind === "drink" ? "напитки" : "товары"}</option>)}</select></label>{!categories.length && <p className="subheading">Сначала создайте категорию на странице «Каталог и тарифы».</p>}<label>Цена, ₽<input type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !categories.length}>{submitting ? "Сохраняем..." : "Создать товар"}</button></form></div>;
}

function ProductPanel({ api, product, onClose, onSaved }: { api: GameClubApi; product?: BackendProduct; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(product?.name ?? "");
  const [category, setCategory] = useState(product?.category ?? "");
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [price, setPrice] = useState(product ? String(product.price_cents / 100) : "0");
  const [costPrice, setCostPrice] = useState(product ? String(product.cost_price_cents / 100) : "0");
  const [stock, setStock] = useState(product ? String(product.stock_quantity) : "0");
  const [active, setActive] = useState(product?.active ?? true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void api.listProductCategories().then((items) => {
      setCategories(items);
      setCategory((current) => current || items[0]?.id || "");
    }).catch(() => setCategories([]));
  }, [api]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const priceRubles = Number(price.replace(",", "."));
    const costRubles = Number(costPrice.replace(",", "."));
    const stockQuantity = Number(stock);
    if (!name.trim() || !category.trim() || !Number.isFinite(priceRubles) || priceRubles < 0 || !Number.isFinite(costRubles) || costRubles < 0 || !Number.isInteger(stockQuantity) || stockQuantity < 0) {
      setError("Заполните позицию, категорию, цены и корректный остаток");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = { name: name.trim(), category: category.trim(), price_cents: Math.round(priceRubles * 100), cost_price_cents: Math.round(costRubles * 100), stock_quantity: stockQuantity, active };
      if (product) await api.updateProduct(product.id, payload);
      else await api.createProduct(payload);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось сохранить товар");
    } finally {
      setSubmitting(false);
    }
  };

  const remove = async () => {
    if (!product || !window.confirm(`Удалить товар «${product.name}»?`)) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.deleteProduct(product.id);
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось удалить товар");
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title={product ? "Редактирование товара" : "Новый товар"} subtitle="Каталог · позиция" onClose={onClose} /><form className="booking-form product-edit-form" onSubmit={(event) => void submit(event)}><label>Название<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Кофе" autoFocus /></label><label>Категория<select value={category} onChange={(event) => setCategory(event.target.value)} disabled={!categories.length}><option value="">{categories.length ? "Выберите категорию" : "Сначала создайте категорию"}</option>{categories.map((item) => <option value={item.id} key={item.id}>{item.name} · {item.kind === "drink" ? "напитки" : "товары"}</option>)}</select></label><div className="form-grid-two"><label>Цена продажи, ₽<input type="number" min="0" step="0.01" value={price} onChange={(event) => setPrice(event.target.value)} /></label><label>Закупочная цена, ₽<input type="number" min="0" step="0.01" value={costPrice} onChange={(event) => setCostPrice(event.target.value)} /></label></div><div className="form-grid-two"><label>Остаток, шт.<input type="number" min="0" step="1" value={stock} onChange={(event) => setStock(event.target.value)} /></label><label className="checkbox-field"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Позиция активна</label></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !categories.length}>{submitting ? "Сохраняем..." : product ? "Сохранить изменения" : "Создать товар"}</button></form>{product && <button className="danger-button product-delete-button" onClick={() => void remove()} disabled={submitting}>Удалить товар <ChevronRight size={15} /></button>}</div>;
}

type SaleLine = {
  key: string;
  kind: "tariff" | "product";
  sourceId: string;
  name: string;
  detail: string;
  priceCents: number;
  quantity: number;
  durationMinutes?: number;
  stockQuantity?: number;
};

const demoSaleTariffs: BackendTariff[] = [
  { id: "demo-tariff-3h", name: "Пакет 3 часа", group_id: null, duration_minutes: 180, price_cents: 32000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-3h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "demo-tariff-1h", name: "Пакет 1 час", group_id: null, duration_minutes: 60, price_cents: 10000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-1h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "demo-tariff-2h", name: "Пакет 2 часа", group_id: null, duration_minutes: 120, price_cents: 22000, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-2h", version: 1, lifecycle: "published", billing_mode: "block", price_per_minute_cents: 0, free_minutes: 0 },
  { id: "demo-tariff-minute", name: "Поминутный", group_id: null, duration_minutes: 0, price_cents: 0, valid_from: "2026-01-01T00:00:00Z", valid_to: null, active: true, tariff_key: "demo-minute", version: 1, lifecycle: "published", billing_mode: "per_minute", price_per_minute_cents: 700, free_minutes: 10 },
];

const demoSaleProducts: BackendProduct[] = [
  { id: "demo-cola", name: "Coca-Cola", category: "drinks", price_cents: 18000, active: true, cost_price_cents: 9000, stock_quantity: 12 },
  { id: "demo-coffee", name: "Кофе", category: "drinks", price_cents: 15000, active: true, cost_price_cents: 5500, stock_quantity: 24 },
  { id: "demo-water", name: "Вода 0,5 л", category: "drinks", price_cents: 10000, active: true, cost_price_cents: 4000, stock_quantity: 30 },
  { id: "demo-chips", name: "Чипсы Lay's", category: "snacks", price_cents: 22000, active: true, cost_price_cents: 12000, stock_quantity: 8 },
  { id: "demo-energy", name: "Monster", category: "energy", price_cents: 25000, active: true, cost_price_cents: 14000, stock_quantity: 6 },
  { id: "demo-headset", name: "Игровые наушники", category: "accessories", price_cents: 45000, active: true, cost_price_cents: 29000, stock_quantity: 3 },
];

function SaleWorkspace({ api, pc, initialProduct, clients: clientList, cashShifts, onClose, onSaved }: { api?: GameClubApi; pc: Workstation | null; initialProduct: BackendProduct | null; clients: Client[]; cashShifts: BackendCashShift[]; onClose: () => void; onSaved: () => void }) {
  const [tariffs, setTariffs] = useState<BackendTariff[]>([]);
  const [products, setProducts] = useState<BackendProduct[]>([]);
  const [categories, setCategories] = useState<BackendProductCategory[]>([]);
  const [activeTab, setActiveTab] = useState<"time" | "products">("time");
  const [tariffCategory, setTariffCategory] = useState<"all" | "blocks" | "minute">("all");
  const [productCategory, setProductCategory] = useState("all");
  const [lines, setLines] = useState<SaleLine[]>([]);
  const [buyerMode, setBuyerMode] = useState<"guest" | "client">("guest");
  const [clientQuery, setClientQuery] = useState("");
  const [client, setClient] = useState<Client | null>(null);
  const [searchResults, setSearchResults] = useState<Client[]>([]);
  const [paymentMethod, setPaymentMethod] = useState<"balance" | "cash">("cash");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const seededProduct = useRef(false);
  const sessionIdempotencyKey = useRef(`sale-session-${crypto.randomUUID()}`);
  const productIdempotencyKeys = useRef(new Map<string, string>());
  const [startedSession, setStartedSession] = useState<{ id: string; signature: string } | null>(null);
  const activeShift = cashShifts.find((shift) => shift.status === "open");
  const searchField = getSearchField(clientQuery);

  useEffect(() => {
    if (!api) {
      setTariffs(demoSaleTariffs);
      setProducts(demoSaleProducts);
      setCategories([
        { id: "drinks", name: "Напитки", kind: "drink", active: true },
        { id: "snacks", name: "Снэки", kind: "product", active: true },
        { id: "energy", name: "Энергетики", kind: "drink", active: true },
        { id: "accessories", name: "Аксессуары", kind: "product", active: true },
      ]);
      return undefined;
    }
    let active = true;
    void Promise.all([api.listTariffs(), api.listProducts(), api.listProductCategories()]).then(([tariffItems, productItems, categoryItems]) => {
      if (!active) return;
      setTariffs(tariffItems.filter((item) => item.lifecycle === "published" && item.active));
      setProducts(productItems.filter((item) => item.active && item.stock_quantity > 0));
      setCategories(categoryItems);
    }).catch((requestError) => {
      if (active) setError(requestError instanceof ApiError ? requestError.message : "Не удалось загрузить каталог");
    });
    return () => { active = false; };
  }, [api]);

  useEffect(() => {
    if (!initialProduct || seededProduct.current || !products.length) return;
    const product = products.find((item) => item.id === initialProduct.id);
    if (product) {
      setLines([{ key: `product:${product.id}`, kind: "product", sourceId: product.id, name: product.name, detail: "Товар", priceCents: product.price_cents, quantity: 1, stockQuantity: product.stock_quantity }]);
      setActiveTab("products");
      seededProduct.current = true;
    }
  }, [initialProduct, products]);

  useEffect(() => {
    if (!searchField) {
      setSearchResults([]);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      if (!api) {
        const normalized = clientQuery.trim().toLowerCase();
        const phoneQuery = normalizePhoneQuery(clientQuery);
        setSearchResults(clientList.filter((item) => searchField === "phone"
          ? normalizePhoneQuery(item.phone).includes(phoneQuery)
          : item.nickname.toLowerCase().includes(normalized)).slice(0, 4));
        return;
      }
      void api.searchClients(clientQuery, searchField).then((items) => {
        if (active) setSearchResults(items.map(toUiClient).slice(0, 4));
      }).catch(() => {
        if (active) setSearchResults([]);
      });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientList, clientQuery, searchField]);

  const money = (cents: number) => `${(cents / 100).toLocaleString("ru-RU")} ₽`;
  const categoryName = (id: string) => categories.find((category) => category.id === id)?.name ?? id;
  const formatDuration = (minutes: number) => minutes >= 60 ? `${minutes / 60} ч` : `${minutes} мин`;
  const timeLines = lines.filter((line) => line.kind === "tariff");
  const productLines = lines.filter((line) => line.kind === "product");
  const totalCents = lines.reduce((sum, line) => sum + line.priceCents * line.quantity, 0);
  const totalMinutes = timeLines.reduce((sum, line) => sum + (line.durationMinutes ?? 0) * line.quantity, 0);
  const mixedTariffs = new Set(timeLines.map((line) => line.sourceId)).size > 1;
  const lineCount = lines.reduce((sum, line) => sum + line.quantity, 0);
  const visibleTariffs = tariffCategory === "all" ? tariffs : tariffs.filter((tariff) => tariff.billing_mode === (tariffCategory === "minute" ? "per_minute" : "block"));
  const productCategoryOptions = ["all", ...Array.from(new Set(products.map((product) => product.category)))];
  const visibleProducts = productCategory === "all" ? products : products.filter((product) => product.category === productCategory);

  const addTariff = (tariff: BackendTariff) => {
    setError(null);
    setSuccess(null);
    setLines((current) => {
      const key = `tariff:${tariff.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing) return current.map((line) => line.key === key ? { ...line, quantity: Math.min(10, line.quantity + 1) } : line);
      return [...current, { key, kind: "tariff", sourceId: tariff.id, name: tariff.name, detail: tariff.billing_mode === "per_minute" ? `${tariff.free_minutes} мин бесплатно · затем поминутно` : formatDuration(tariff.duration_minutes), priceCents: tariff.billing_mode === "per_minute" ? 0 : tariff.price_cents, quantity: 1, durationMinutes: tariff.duration_minutes }];
    });
  };
  const addProduct = (product: BackendProduct) => {
    setError(null);
    setSuccess(null);
    setLines((current) => {
      const key = `product:${product.id}`;
      const existing = current.find((line) => line.key === key);
      if (existing) return current.map((line) => line.key === key ? { ...line, quantity: Math.min(product.stock_quantity, line.quantity + 1) } : line);
      return [...current, { key, kind: "product", sourceId: product.id, name: product.name, detail: categoryName(product.category), priceCents: product.price_cents, quantity: 1, stockQuantity: product.stock_quantity }];
    });
  };
  const changeQuantity = (key: string, delta: number) => setLines((current) => current.flatMap((line) => {
    if (line.key !== key) return [line];
    const max = line.kind === "product" ? line.stockQuantity ?? 1 : 10;
    const quantity = Math.min(max, line.quantity + delta);
    return quantity > 0 ? [{ ...line, quantity }] : [];
  }));
  const removeLine = (key: string) => setLines((current) => current.filter((line) => line.key !== key));
  const selectClient = (value: Client) => {
    setClient(value);
    setBuyerMode("client");
    setClientQuery(value.nickname);
    setSearchResults([]);
    setError(null);
  };
  const selectGuest = () => {
    setBuyerMode("guest");
    setClient(null);
    setClientQuery("");
    setSearchResults([]);
    if (paymentMethod === "balance") setPaymentMethod("cash");
  };

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    if (!lines.length) {
      setError("Добавьте в продажу хотя бы одну позицию");
      return;
    }
    if (mixedTariffs) {
      setError("Смешанный набор тарифов «3 часа + 1 час» пока нельзя провести одним стартом: backend принимает один тариф с количеством пакетов. Корзина сохранена.");
      return;
    }
    if (timeLines.length && !pc) {
      setError("Продажа времени доступна из карточки игрового места");
      return;
    }
    if (paymentMethod === "balance" && !client) {
      setError("Для оплаты с баланса выберите зарегистрированного клиента");
      return;
    }
    if (api && paymentMethod === "cash" && !activeShift) {
      setError("Нет актуальной открытой кассовой смены");
      return;
    }
    const timeSignature = timeLines[0] ? `${timeLines[0].sourceId}:${timeLines[0].quantity}` : "";
    if (startedSession && startedSession.signature !== timeSignature) {
      setError("Сессия уже запущена с другим тарифом. Завершите текущую операцию или откройте новую продажу.");
      return;
    }
    setSubmitting(true);
    try {
      if (!api) {
        setSuccess("Демо: заказ собран и готов к проведению");
        return;
      }
      if (pc && timeLines[0] && !startedSession) {
        const session = await api.startSession({
            workstation_id: pc.id,
            client_id: client?.id,
            guest_name: client ? undefined : "Гость",
            source: "operator",
            tariff_id: timeLines[0].sourceId,
            tariff_quantity: timeLines[0].quantity,
          }, sessionIdempotencyKey.current);
        setStartedSession({ id: session.id, signature: timeSignature });
      }
      for (const line of productLines) {
        const operationKey = productIdempotencyKeys.current.get(line.key) ?? `sale-product-${crypto.randomUUID()}`;
        productIdempotencyKeys.current.set(line.key, operationKey);
        await api.sellProduct({
          product_id: line.sourceId,
          quantity: line.quantity,
          client_id: client?.id,
          payment_method: paymentMethod,
          cash_shift_id: paymentMethod === "cash" ? activeShift?.id : undefined,
        }, operationKey);
      }
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось провести продажу");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="sale-workspace-backdrop">
    <section className="sale-workspace" role="dialog" aria-modal="true" aria-labelledby="sale-workspace-title">
      <header className="sale-workspace-header">
        <div className="sale-workspace-title"><button type="button" className="sale-close-button" aria-label="Закрыть продажу" onClick={onClose}><X size={19} /></button><div><p>ОПЕРАЦИЯ · НОВАЯ ПРОДАЖА</p><h1 id="sale-workspace-title">Продажа для {pc?.name ?? "магазина"}</h1><span>{pc ? `${pc.group} · ${pc.status === "online" ? "готов к запуску" : "карточка места"}` : "Товары без привязки к игровому месту"}</span></div></div>
        <div className="sale-header-meta"><div className="sale-shift-badge"><i /><div><small>Актуальная смена</small><strong>{activeShift?.register_id ?? (api ? "Не открыта" : "Демо-смена")}</strong></div></div><div className="sale-header-total"><small>Итого</small><strong>{money(totalCents)}</strong></div></div>
      </header>
      <div className="sale-workspace-body">
        <div className="sale-workspace-main">
          <section className="sale-buyer-card">
            <div className="sale-section-heading"><div><span className="sale-step">01</span><div><h2>Покупатель</h2><p>Кому оформить время и товары</p></div></div>{buyerMode === "guest" && <span className="sale-auto-note"><Sparkles size={14} /> Гость включён автоматически</span>}</div>
            <div className="sale-buyer-choices"><button type="button" className={`sale-buyer-choice ${buyerMode === "guest" ? "selected" : ""}`} onClick={selectGuest}><span className="sale-choice-icon guest"><UserX size={17} /></span><span><strong>Гость</strong><small>Без регистрации и баланса</small></span>{buyerMode === "guest" && <Check size={16} />}</button><button type="button" className={`sale-buyer-choice ${buyerMode === "client" ? "selected" : ""}`} onClick={() => setBuyerMode("client")}><span className="sale-choice-icon client"><UserRound size={17} /></span><span><strong>{client?.nickname ?? "Зарегистрированный клиент"}</strong><small>{client ? `Баланс ${client.balance.toLocaleString("ru-RU")} ₽ · ${client.category}` : "Поиск по нику или телефону"}</small></span>{buyerMode === "client" && <Check size={16} />}</button></div>
            {buyerMode === "client" && <div className="sale-client-search"><Search size={17} /><input aria-label="Клиент для продажи" autoFocus value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClient(null); }} placeholder="Введите от 3 букв ника или 4 цифр телефона" />{client && <button type="button" className="sale-clear-client" aria-label="Сбросить клиента" onClick={() => { setClient(null); setClientQuery(""); }}>×</button>}</div>}
            {buyerMode === "client" && searchResults.length > 0 && !client && <div className="sale-client-results">{searchResults.map((item) => <button type="button" className="sale-client-result" key={item.id} onClick={() => selectClient(item)}><span className="client-avatar">{item.nickname.slice(0, 2).toUpperCase()}</span><span><strong>{item.nickname}</strong><small>{formatRussianPhone(item.phone)} · баланс {item.balance.toLocaleString("ru-RU")} ₽</small></span><ChevronRight size={16} /></button>)}</div>}
          </section>
          <section className="sale-catalog-card">
            <div className="sale-section-heading"><div><span className="sale-step">02</span><div><h2>Добавьте в продажу</h2><p>Выберите несколько позиций — они появятся справа в заказе</p></div></div><div className="sale-catalog-count"><span>{lineCount}</span> поз. в заказе</div></div>
            <div className="sale-main-tabs" role="tablist" aria-label="Каталог продажи"><button type="button" className={activeTab === "time" ? "selected" : ""} role="tab" aria-selected={activeTab === "time"} onClick={() => setActiveTab("time")}><Clock3 size={16} /> Игровое время <em>{tariffs.length}</em></button><button type="button" className={activeTab === "products" ? "selected" : ""} role="tab" aria-selected={activeTab === "products"} onClick={() => setActiveTab("products")}><ShoppingCart size={16} /> Товары и напитки <em>{products.length}</em></button></div>
            {activeTab === "time" ? <><div className="sale-category-tabs"><button type="button" className={tariffCategory === "all" ? "selected" : ""} onClick={() => setTariffCategory("all")}>Все тарифы</button><button type="button" className={tariffCategory === "blocks" ? "selected" : ""} onClick={() => setTariffCategory("blocks")}><Tags size={14} /> Пакеты</button><button type="button" className={tariffCategory === "minute" ? "selected" : ""} onClick={() => setTariffCategory("minute")}><Clock3 size={14} /> Поминутно</button></div><div className="sale-item-grid">{visibleTariffs.map((tariff) => <button type="button" className="sale-item-card time-card" key={tariff.id} onClick={() => addTariff(tariff)}><div className="sale-item-top"><span className={`sale-item-icon ${tariff.billing_mode === "per_minute" ? "minute" : "package"}`}>{tariff.billing_mode === "per_minute" ? <Clock3 size={18} /> : <Gamepad2 size={18} />}</span><span className="sale-add-icon"><Plus size={16} /></span></div><strong>{tariff.name}</strong><small>{tariff.billing_mode === "per_minute" ? `${(tariff.price_per_minute_cents / 100).toLocaleString("ru-RU")} ₽/мин · ${tariff.free_minutes} мин бесплатно` : `${formatDuration(tariff.duration_minutes)} игрового времени`}</small><div className="sale-item-price">{tariff.billing_mode === "per_minute" ? <><b>По минутам</b><span>от {(tariff.price_per_minute_cents / 100).toLocaleString("ru-RU")} ₽</span></> : <><b>{money(tariff.price_cents)}</b><span>за пакет</span></>}</div></button>)}{!visibleTariffs.length && <div className="sale-empty-catalog">Опубликованных тарифов нет</div>}</div></> : <><div className="sale-category-tabs">{productCategoryOptions.map((category) => <button type="button" className={productCategory === category ? "selected" : ""} key={category} onClick={() => setProductCategory(category)}>{category === "all" ? "Все товары" : categoryName(category)}</button>)}</div><div className="sale-item-grid">{visibleProducts.map((product) => <button type="button" className="sale-item-card product-card" key={product.id} onClick={() => addProduct(product)}><div className="sale-item-top"><span className="sale-item-icon product"><ShoppingCart size={18} /></span><span className="sale-stock">{product.stock_quantity} шт.</span></div><strong>{product.name}</strong><small>{categoryName(product.category)}</small><div className="sale-item-price"><b>{money(product.price_cents)}</b><span>за штуку</span></div></button>)}{!visibleProducts.length && <div className="sale-empty-catalog">Товаров с остатком нет</div>}</div></>}
          </section>
        </div>
        <form className="sale-order-panel" onSubmit={(event) => void submit(event)}>
          <div className="sale-order-heading"><div><span className="sale-step">03</span><div><h2>Заказ</h2><p>{client?.nickname ?? "Гость"} · {pc?.name ?? "без ПК"}</p></div></div><span className="sale-order-count">{lineCount}</span></div>
          <div className="sale-order-target"><span className="sale-target-icon"><Gamepad2 size={17} /></span><div><small>Игровое место</small><strong>{pc?.name ?? "Не выбрано"}</strong></div><span className={`sale-target-status ${pc ? "ready" : "muted"}`}>{pc ? "Готово" : "Только товары"}</span></div>
          <div className="sale-lines">{lines.length ? lines.map((line) => <div className="sale-line" key={line.key}><div className={`sale-line-icon ${line.kind}`}>
            {line.kind === "tariff" ? <Clock3 size={15} /> : <ShoppingCart size={15} />}
          </div><div className="sale-line-info"><strong>{line.name}</strong><small>{line.detail}</small><b>{money(line.priceCents * line.quantity)}</b></div><div className="sale-quantity"><button type="button" aria-label={`Уменьшить ${line.name}`} onClick={() => changeQuantity(line.key, -1)}><Minus size={13} /></button><span>{line.quantity}</span><button type="button" aria-label={`Увеличить ${line.name}`} onClick={() => changeQuantity(line.key, 1)}><Plus size={13} /></button></div><button type="button" className="sale-remove-line" aria-label={`Удалить ${line.name}`} onClick={() => removeLine(line.key)}><X size={14} /></button></div>) : <div className="sale-empty-order"><Receipt size={24} /><strong>Заказ пока пуст</strong><span>Нажимайте на карточки слева, чтобы добавить время или товары</span></div>}</div>
          <div className="sale-order-summary"><div><span>Игровое время</span><strong>{totalMinutes ? formatDuration(totalMinutes) : "—"}</strong></div><div><span>Товары</span><strong>{productLines.length ? `${productLines.reduce((sum, line) => sum + line.quantity, 0)} шт.` : "—"}</strong></div><div className="sale-total-row"><span>Итого к оплате</span><strong>{money(totalCents)}</strong></div></div>
          {mixedTariffs && <div className="sale-inline-warning"><Tags size={16} /><span>В корзине разные тарифы. Визуально можно собрать заказ, но backend пока проводит только один тариф за старт.</span></div>}
          <div className="sale-payment"><div className="sale-payment-heading"><span>Способ оплаты товаров</span></div><div className="sale-payment-tabs"><button type="button" className={paymentMethod === "cash" ? "selected" : ""} onClick={() => setPaymentMethod("cash")}><Receipt size={15} /> Наличные</button><button type="button" className={paymentMethod === "balance" ? "selected" : ""} disabled={!client} onClick={() => setPaymentMethod("balance")}><WalletCards size={15} /> Баланс</button></div></div>
          {error && <div className="sale-form-error" role="alert">{error}</div>}
          {success && <div className="sale-form-success" role="status">{success}</div>}
          <button className="sale-submit-button" disabled={submitting || !lines.length || mixedTariffs}>{submitting ? "Проводим заказ…" : `Оформить продажу · ${money(totalCents)}`}<ChevronRight size={17} /></button>
          <button type="button" className="sale-cancel-button" onClick={onClose}>Отмена</button>
        </form>
      </div>
    </section>
  </div>;
}

function ProductSalePanel({ api, product, clients, cashShifts, onClose, onSaved }: { api: GameClubApi; product: BackendProduct; clients: Client[]; cashShifts: BackendCashShift[]; onClose: () => void; onSaved: () => void }) {
  const [quantity, setQuantity] = useState("1");
  const [clientQuery, setClientQuery] = useState("");
  const [client, setClient] = useState<Client | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<"balance" | "cash">("cash");
  const [cashShiftId, setCashShiftId] = useState(cashShifts.find((shift) => shift.status === "open")?.id ?? "");
  const [searchResults, setSearchResults] = useState<Client[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const parsedQuantity = Number(quantity);
  const totalCents = Number.isInteger(parsedQuantity) && parsedQuantity > 0 ? product.price_cents * parsedQuantity : 0;
  const openShifts = cashShifts.filter((shift) => shift.status === "open");
  const searchField = getSearchField(clientQuery);

  useEffect(() => {
    if (!searchField) {
      setSearchResults([]);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void api.searchClients(clientQuery, searchField).then((items) => {
        if (active) setSearchResults(items.map(toUiClient));
      }).catch(() => {
        if (active) setSearchResults([]);
      });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientQuery, searchField]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!Number.isInteger(parsedQuantity) || parsedQuantity < 1 || parsedQuantity > product.stock_quantity) {
      setError("Количество должно быть от 1 до " + product.stock_quantity + " шт.");
      return;
    }
    if (paymentMethod === "balance" && !client) {
      setError("Для оплаты с баланса выберите зарегистрированного клиента");
      return;
    }
    if (paymentMethod === "cash" && !cashShiftId) {
      setError("Откройте кассовую смену для наличной продажи");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.sellProduct({
        product_id: product.id,
        quantity: parsedQuantity,
        client_id: client?.id,
        payment_method: paymentMethod,
        cash_shift_id: paymentMethod === "cash" ? cashShiftId : undefined,
      }, "product-sale-" + crypto.randomUUID());
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось продать товар");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Продажа товара" subtitle="Магазин · операция" onClose={onClose} /><div className="sale-product-card"><div className="sale-product-icon"><ShoppingCart size={21} /></div><div><strong>{product.name}</strong><span>Остаток {product.stock_quantity} шт. · {(product.price_cents / 100).toLocaleString("ru-RU")} ₽/шт.</span></div></div><form className="booking-form product-sale-form" onSubmit={(event) => void submit(event)}><label>Количество, шт.<input type="number" min="1" max={product.stock_quantity} step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} autoFocus /></label><label>Клиент <span className="field-hint">необязательно для наличной оплаты</span><input value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClient(null); }} placeholder="Ник или телефон" /></label>{searchResults.length > 0 && !client && <div className="sale-client-results">{searchResults.slice(0, 4).map((item) => <button type="button" className="client-result" key={item.id} onClick={() => { setClient(item); setClientQuery(item.nickname); setSearchResults([]); }}><span className="client-avatar">{item.nickname.slice(0, 2).toUpperCase()}</span><span><strong>{item.nickname}</strong><small>{formatRussianPhone(item.phone)}</small></span><ChevronRight size={14} /></button>)}</div>}<div className="sale-payment-picker"><span>Способ оплаты</span><div className="compact-tabs"><button type="button" className={paymentMethod === "cash" ? "selected" : ""} onClick={() => setPaymentMethod("cash")}>Наличные</button><button type="button" className={paymentMethod === "balance" ? "selected" : ""} onClick={() => setPaymentMethod("balance")} disabled={!client}>Баланс клиента</button></div></div>{paymentMethod === "cash" && <label>Кассовая смена<select value={cashShiftId} onChange={(event) => setCashShiftId(event.target.value)} disabled={!openShifts.length}><option value="">{openShifts.length ? "Выберите смену" : "Нет открытой смены"}</option>{openShifts.map((shift) => <option value={shift.id} key={shift.id}>{shift.register_id} · {(shift.expected_close_cents / 100).toLocaleString("ru-RU")} ₽</option>)}</select></label>}<div className="sale-total"><span>Итого</span><strong>{(totalCents / 100).toLocaleString("ru-RU")} ₽</strong></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Проводим продажу..." : "Продать товар"}</button><button type="button" className="secondary-button wide" onClick={onClose}>Отмена</button></form></div>;
}

function DiscountPanel({ api, onClose, onSaved }: { api: GameClubApi; onClose: () => void; onSaved: () => void }) {
  const [category, setCategory] = useState("");
  const [percent, setPercent] = useState("0");
  const [priority, setPriority] = useState("0");
  const [validFrom, setValidFrom] = useState(() => {
    const date = new Date();
    date.setSeconds(0, 0);
    return localDateTimeValue(date);
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const percentValue = Number(percent);
    const priorityValue = Number(priority);
    const parsedDate = new Date(validFrom);
    if (!category.trim() || !Number.isFinite(percentValue) || percentValue < 0 || percentValue > 100 || !Number.isInteger(priorityValue) || priorityValue < 0 || Number.isNaN(parsedDate.getTime())) {
      setError("Заполните категорию, процент от 0 до 100 и приоритет");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.createDiscountRule({
        category: category.trim(),
        percent_bps: Math.round(percentValue * 100),
        priority: priorityValue,
        valid_from: parsedDate.toISOString(),
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать правило скидки");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><div className="panel-header"><div><p>Каталог</p><h2>Новая скидка</h2></div><button className="icon-button" aria-label="Закрыть панель" onClick={onClose}><X size={18} /></button></div><form className="booking-form" onSubmit={submit}><label>Категория клиента<input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="student" autoFocus /></label><label>Скидка, %<input type="number" min="0" max="100" step="0.01" value={percent} onChange={(event) => setPercent(event.target.value)} /></label><label>Приоритет<input type="number" min="0" step="1" value={priority} onChange={(event) => setPriority(event.target.value)} /></label><label>Начало действия<DateTimePicker value={validFrom} onChange={setValidFrom} mode="datetime" label="Начало действия правила" /></label>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting}>{submitting ? "Сохраняем..." : "Создать правило"}</button><p className="subheading">Backend применит наиболее приоритетное правило при quote.</p></form></div>;
}

function ActivityCard({ liveMode, events }: { liveMode: boolean; events: BackendAuditEvent[] }) {
  if (liveMode) {
    const eventIcon = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("client")) return <ArrowDownLeft size={16} />;
      if (path.includes("session")) return <Computer size={16} />;
      if (path.includes("reservation")) return <CalendarDays size={16} />;
      return <ShieldCheck size={16} />;
    };
    const eventTitle = (event: BackendAuditEvent) => {
      const path = event.resource_path.toLowerCase();
      if (path.includes("top-up") || path.includes("topup")) return "Пополнение баланса";
      if (path.includes("charge")) return "Списание за сессию";
      if (path.includes("reservation")) return "Операция с бронью";
      if (path.includes("session")) return "Операция сессии";
      if (path.includes("workstation")) return "Операция с игровым ПК";
      if (path.includes("client")) return "Операция с клиентом";
      if (path.includes("catalog")) return "Изменение каталога";
      return event.action;
    };
    const outcomeLabel = (event: BackendAuditEvent) => event.outcome === "success" ? "Успешно" : `Ошибка ${event.status_code}`;
    return <div className="white-card activity-card"><div className="card-heading"><div><h3>Активность смены</h3><p>Последние операции из backend audit trail</p></div><ShieldCheck size={18} className="muted" /></div>{events.map((event) => <div className="activity-item" key={event.id}><div className={`activity-icon ${event.outcome === "success" ? "income" : "booking"}`}>{eventIcon(event)}</div><div><strong>{eventTitle(event)}</strong><span>{new Date(event.created_at).toLocaleString("ru-RU")} · {event.actor_id || "Система"} · {event.action}</span></div><b className={event.outcome === "success" ? "income-text" : ""}>{outcomeLabel(event)}</b></div>)}{!events.length && <div className="timeline-empty">Операций пока нет</div>}</div>;
  }
  return <div className="white-card activity-card"><div className="card-heading"><div><h3>Активность смены</h3><p>Последние операции оператора</p></div><ShieldCheck size={18} className="muted" /></div><div className="activity-item"><div className="activity-icon income"><ArrowDownLeft size={16} /></div><div><strong>Пополнение · NightFox</strong><span>Сегодня, 12:36</span></div><b className="income-text">+1 000 ₽</b></div><div className="activity-item"><div className="activity-icon session"><Computer size={16} /></div><div><strong>Запущена сессия · VIP-01</strong><span>Сегодня, 12:18</span></div><b>m0onlight</b></div><div className="activity-item"><div className="activity-icon booking"><CalendarDays size={16} /></div><div><strong>Создана бронь · A-04</strong><span>Сегодня, 12:04</span></div><b>night_walker</b></div></div>;
}

function UpcomingBookings({
  liveMode,
  reservations,
  pcs,
  clients,
  onOpenBookings,
}: {
  liveMode: boolean;
  reservations: Reservation[];
  pcs: Workstation[];
  clients: Client[];
  onOpenBookings: () => void;
}) {
  const workstationNames = new Map(pcs.map((pc) => [pc.id, pc.name]));
  const clientNames = new Map(clients.map((client) => [client.id, client.nickname]));
  const liveItems = reservations
    .filter((reservation) => reservation.status !== "cancelled" && Date.parse(reservation.end_at) >= Date.now())
    .sort((left, right) => Date.parse(left.start_at) - Date.parse(right.start_at))
    .slice(0, 3);
  return <div className="white-card upcoming-card"><div className="card-heading"><div><h3>Ближайшие брони</h3><p>{liveMode ? "Данные из backend" : "Сегодня"}</p></div><button className="text-button" onClick={onOpenBookings}>Все брони <ChevronRight size={15} /></button></div>{liveMode ? liveItems.map((reservation) => <div className="upcoming-item" key={reservation.id}><div className="booking-time"><strong>{new Date(reservation.start_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</strong><span>{new Date(reservation.end_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</span></div><div className="booking-line" /><div><strong>{reservation.guest_name || (reservation.client_id ? clientNames.get(reservation.client_id) || "Клиент" : "Гость")}</strong><span>{reservation.workstation_ids.map((id) => workstationNames.get(id) || id.slice(0, 8)).join(", ")}</span></div><span className={`booking-status ${reservation.status === "confirmed" ? "pending" : ""}`}>{reservation.status}</span></div>) : bookings.slice(0, 3).map((booking) => <div className="upcoming-item" key={booking.id}><div className="booking-time"><strong>{booking.start}</strong><span>{booking.end}</span></div><div className="booking-line" /><div><strong>{booking.client}</strong><span>{booking.workstation}</span></div><span className={`booking-status ${booking.status === "Ожидает" ? "pending" : ""}`}>{booking.status}</span></div>)}{liveMode && !liveItems.length && <div className="timeline-empty">На сегодня броней не найдено</div>}</div>;
}

function PcPanel({
  pc,
  clients,
  cashShifts,
  onClose,
  onEdit,
  onBook,
  onDeposit,
  onOpenSale,
  onSessionChanged,
  api,
}: {
  pc: Workstation;
  clients: Client[];
  cashShifts: BackendCashShift[];
  onClose: () => void;
  onEdit: () => void;
  onBook: () => void;
  onDeposit: (client?: Client, bonusOnly?: boolean) => void;
  onOpenSale: () => void;
  onSessionChanged: () => void;
  api?: GameClubApi;
}) {
  const meta = statusMeta[pc.status];
  const [operationState, setOperationState] = useState<string | null>(null);
  const [operationSuccess, setOperationSuccess] = useState(false);
  const [clientQuery, setClientQuery] = useState("");
  const [clientCandidate, setClientCandidate] = useState<Client | undefined>();
  const [tariffs, setTariffs] = useState<Awaited<ReturnType<GameClubApi["listTariffs"]>>>([]);
  const [tariffId, setTariffId] = useState<string>("");
  const [tariffQuantity, setTariffQuantity] = useState("1");
  const [meter, setMeter] = useState<BackendSessionMeter | null>(null);
  const [products, setProducts] = useState<BackendProduct[]>([]);
  const [saleProductId, setSaleProductId] = useState("");
  const [saleQuantity, setSaleQuantity] = useState("1");
  const [salePaymentMethod, setSalePaymentMethod] = useState<"balance" | "cash">("cash");
  const [saleCashShiftId, setSaleCashShiftId] = useState(cashShifts.find((shift) => shift.status === "open")?.id ?? "");
  const [stoppedSessionId, setStoppedSessionId] = useState<string | undefined>();
  const [submitting, setSubmitting] = useState(false);
  const clientField = getSearchField(clientQuery);

  useEffect(() => {
    if (!api) {
      return undefined;
    }
    void Promise.all([api.listTariffs(), api.listProducts()]).then(([items, productItems]) => {
      const published = items.filter((item) => item.lifecycle === "published");
      setTariffs(published);
      setTariffId((current) => current || published[0]?.id || "");
      setProducts(productItems.filter((item) => item.active && item.stock_quantity > 0));
      setSaleProductId((current) => current || productItems[0]?.id || "");
    }).catch(() => {
      setTariffs([]);
      setProducts([]);
    });
    return undefined;
  }, [api]);

  useEffect(() => {
    if (!api || pc.status !== "busy" || !pc.sessionId) {
      setMeter(null);
      return undefined;
    }
    let active = true;
    const refreshMeter = () => {
      void api.getSessionMeter(pc.sessionId!).then((value) => {
        if (active) setMeter(value);
      }).catch(() => {
        if (active) setMeter(null);
      });
    };
    refreshMeter();
    const timer = window.setInterval(refreshMeter, 10_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, pc.sessionId, pc.status]);

  useEffect(() => {
    if (!api || !clientField || pc.status === "busy") {
      setClientCandidate(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(clientQuery, clientField);
        if (active) {
          setClientCandidate(found[0] ? toUiClient(found[0]) : undefined);
        }
      } catch {
        if (active) {
          setClientCandidate(undefined);
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientField, clientQuery, pc.status]);

  const startOrStop = async () => {
    if (!api) {
      setOperationSuccess(false);
      setOperationState("Mock-режим: сессия не отправлялась");
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      if (pc.status === "busy") {
        if (!pc.sessionId) {
          setOperationState("Не найден ID активной сессии");
          return;
        }
        if (!window.confirm(`Прервать сессию на «${pc.name}»? Время будет рассчитано по фактическому окончанию.`)) {
          return;
        }
        const session = await api.interruptSession(
          pc.sessionId,
          "Клиент завершил сессию раньше",
          crypto.randomUUID(),
        );
        setStoppedSessionId(session.id);
        setOperationSuccess(true);
        setOperationState("Сессия прервана. Проверьте итог и выполните списание.");
      } else {
        await api.startSession(
          {
            workstation_id: pc.id,
            client_id: clientCandidate?.id,
            guest_name: clientCandidate ? undefined : "Гость",
            source: "operator",
            tariff_id: tariffId || undefined,
            tariff_quantity: Math.max(1, Math.min(100, Number(tariffQuantity) || 1)),
          },
          crypto.randomUUID(),
        );
        setOperationSuccess(true);
        setOperationState("Сессия открыта");
      }
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось изменить сессию");
    } finally {
      setSubmitting(false);
    }
  };
  const charge = async () => {
    if (!api || !stoppedSessionId) {
      return;
    }
    if (!window.confirm("Списать стоимость завершённой сессии по действующему тарифу?")) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      const result = await api.chargeSession(stoppedSessionId, crypto.randomUUID());
      setOperationSuccess(true);
      setOperationState(
        `Списано ${(result.amount_cents / 100).toLocaleString("ru-RU")} ₽. Баланс: ${(result.client_balance_cents / 100).toLocaleString("ru-RU")} ₽`,
      );
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось списать с баланса");
    } finally {
      setSubmitting(false);
    }
  };

  const sellProduct = async () => {
    if (!api) return;
    const product = products.find((item) => item.id === saleProductId);
    const quantity = Number(saleQuantity);
    const openShiftId = saleCashShiftId || cashShifts.find((shift) => shift.status === "open")?.id;
    if (!product || !Number.isInteger(quantity) || quantity < 1 || quantity > product.stock_quantity) {
      setOperationState("Выберите товар и корректное количество");
      return;
    }
    if (salePaymentMethod === "balance" && !clientCandidate) {
      setOperationState("Для оплаты с баланса выберите зарегистрированного клиента");
      return;
    }
    if (salePaymentMethod === "cash" && !openShiftId) {
      setOperationState("Откройте кассовую смену для продажи за наличные");
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      await api.sellProduct({
        product_id: product.id,
        quantity,
        client_id: clientCandidate?.id,
        payment_method: salePaymentMethod,
        cash_shift_id: salePaymentMethod === "cash" ? openShiftId : undefined,
      }, "pc-product-sale-" + crypto.randomUUID());
      setSaleQuantity("1");
      setOperationSuccess(true);
      setOperationState("Товар продан: " + product.name + " · " + quantity + " шт.");
      onSessionChanged();
      const refreshed = await api.listProducts();
      setProducts(refreshed.filter((item) => item.active && item.stock_quantity > 0));
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось продать товар");
    } finally {
      setSubmitting(false);
    }
  };

  const toggleAvailability = async () => {
    if (!api || !window.confirm(`${pc.status === "maintenance" ? "Включить" : "Отключить"} игровое место «${pc.name}»?`)) {
      return;
    }
    setSubmitting(true);
    setOperationSuccess(false);
    setOperationState(null);
    try {
      if (pc.status === "maintenance") {
        await api.enableWorkstation(pc.id);
        setOperationState("Место включено; ожидается heartbeat клиента");
      } else {
        await api.disableWorkstation(pc.id, "Отключено оператором из панели");
        setOperationState("Место отключено; новые команды заблокированы");
      }
      onSessionChanged();
    } catch (error) {
      setOperationSuccess(false);
      setOperationState(error instanceof ApiError ? error.message : "Не удалось отключить место");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner">
    <PanelHeader title={pc.name} subtitle={pc.group} onClose={onClose} />
    <div className="panel-pc-hero">
      <div className={"large-pc-icon " + pc.status}><Computer size={50} strokeWidth={1.2} /></div>
      <div><span className={"pill-status " + meta.className}><i /> {meta.label}</span><h2>{pc.client || "Место свободно"}</h2><p>{pc.session ? "Сессия началась " + pc.session + " назад" : pc.lastSeen || "Готово к новой сессии"}</p>{meter && <small className="meter-status">Поминутно · списано {(meter.billed_cents / 100).toLocaleString("ru-RU")} ₽ · {meter.billed_minutes} мин · {meter.status === "exhausted" ? "баланс исчерпан" : "активно"}</small>}</div>
    </div>
    <div className="panel-section">
      <div className="detail-row"><span>Группа</span><strong>{pc.group}</strong></div>
      <div className="detail-row"><span>Позиция на карте</span><strong>{pc.position ?? "—"}</strong></div>
      <div className="detail-row"><span>Клиентский агент</span><strong>{pc.deviceId || "—"}</strong></div>
    </div>
    {pc.status !== "busy" && <button type="button" className="sale-entry-card" onClick={onOpenSale}>
      <div className="sale-entry-icon"><Receipt size={20} /></div>
      <div><strong>Оформить продажу</strong><span>Время, товары и покупатель — в одном окне</span></div>
      <ChevronRight size={17} />
    </button>}
    <div className="panel-actions">
      <button className="secondary-button wide" onClick={() => onDeposit(clientCandidate)}><WalletCards size={15} /> Пополнить баланс</button>
      <button className="secondary-button wide" onClick={onEdit}><Settings size={15} /> Редактировать ПК</button>
      {pc.status === "busy" ? <button className="primary-button wide" onClick={() => void startOrStop()} disabled={submitting || Boolean(stoppedSessionId)}>{submitting ? "Сохраняем..." : "Прервать сессию"}</button> : <button className="primary-button wide" onClick={onOpenSale} disabled={pc.status === "offline" || pc.status === "maintenance"}><ShoppingCart size={15} /> Открыть продажи</button>}
      {stoppedSessionId && api && <button className="primary-button wide" onClick={() => void charge()} disabled={submitting}>Списать по тарифу</button>}
      <button className="secondary-button wide" onClick={onBook}>Забронировать место</button>
      {operationState && <div className={`${operationSuccess ? "form-success" : "form-error"} command-result`} role={operationSuccess ? "status" : "alert"} aria-live="polite">{operationState}</div>}
    </div>
    <button className="danger-button" onClick={() => void toggleAvailability()} disabled={!api || submitting} aria-disabled={!api}>{pc.status === "maintenance" ? "Включить место" : "Отключить место"} <ChevronRight size={15} /></button>
    <button className="danger-button" onClick={async () => { if (!api || !window.confirm("Удалить «" + pc.name + "» из активной карты?")) return; setSubmitting(true); try { await api.deleteWorkstation(pc.id); onSessionChanged(); onClose(); } catch (error) { setOperationSuccess(false); setOperationState(error instanceof ApiError ? error.message : "Не удалось удалить место"); } finally { setSubmitting(false); } }}>Удалить из карты</button>
  </div>;
}

function DepositPanel({
  initialClient,
  bonusOnly = false,
  onClose,
  onCompleted,
  clients: clientList,
  api,
}: {
  initialClient?: Client;
  bonusOnly?: boolean;
  onClose: () => void;
  onCompleted: () => void;
  clients: Client[];
  api?: GameClubApi;
}) {
  const [query, setQuery] = useState(initialClient?.nickname ?? "");
  const [amount, setAmount] = useState("1000");
  const [bonusAmount, setBonusAmount] = useState(bonusOnly ? "100" : "0");
  const [liveResult, setLiveResult] = useState<Client | undefined>(initialClient);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const normalized = query.trim().toLowerCase();
  const searchField = getSearchField(normalized);
  const ready = searchField !== null;

  useEffect(() => {
    if (!api) {
      setLiveResult(undefined);
      return undefined;
    }
    if (!searchField) {
      setLiveResult(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(normalized, searchField);
        if (active) {
          setLiveResult(found[0] ? toUiClient(found[0]) : undefined);
          setSearchError(null);
        }
      } catch (error) {
        if (active) {
          setSearchError(error instanceof ApiError ? error.message : "Не удалось выполнить поиск");
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, normalized, searchField]);

  const result = api
    ? liveResult
    : ready
      ? clientList.find((client) => client.nickname.toLowerCase().includes(normalized) || client.phone.replace(/\D/g, "").includes(normalized.replace(/\D/g, "")))
      : undefined;

  const submit = async () => {
    if (!result) {
      return;
    }
    if (!api) {
      onCompleted();
      return;
    }
    const amountCents = Math.round(Number(amount.replace(",", ".")) * 100);
    const parsedBonus = Math.round(Number(bonusAmount.replace(",", ".")));
    if ((!bonusOnly && (!Number.isFinite(amountCents) || amountCents <= 0)) || !Number.isFinite(parsedBonus) || parsedBonus < 0 || (bonusOnly && parsedBonus <= 0)) {
      setSearchError(bonusOnly ? "Введите положительное количество бонусов" : "Введите положительную сумму");
      return;
    }
    setSubmitting(true);
    setSearchError(null);
    try {
      await api.topUp(
        result.id,
        { amount_cents: bonusOnly ? 0 : amountCents, bonus_amount: parsedBonus, reason: bonusOnly ? "Начисление бонусов через оператора" : "Пополнение через оператора" },
        crypto.randomUUID(),
      );
      onCompleted();
    } catch (error) {
      setSearchError(error instanceof ApiError ? error.message : "Не удалось пополнить депозит");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title={bonusOnly ? "Начисление бонусов" : "Пополнение депозита"} subtitle="Баланс клиента" onClose={onClose} /><div className="deposit-step"><span className="step-label">1 / 2</span><h2>Найдите клиента</h2><p>Введите минимум 3 символа ника или 4 цифры телефона.</p><div className="search-box panel-search"><Search size={17} /><input aria-label="Ник или номер телефона" autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ник или номер телефона" /></div>{ready && result && <div className="client-result"><div className="client-avatar">{result.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{result.nickname}</strong><span>{formatRussianPhone(result.phone)}</span></div><ChevronRight size={16} /></div>}{ready && !result && <div className="empty-result" role="status" aria-live="polite">{searchError || "Клиент не найден"}</div>}</div><div className="deposit-preview"><div><span>{bonusOnly ? "Бонусы будут начислены на" : "Средства будут зачислены на"}</span><strong>{result?.nickname || "—"}</strong></div><ShieldCheck size={21} /></div>{!bonusOnly && <label className="amount-field">Сумма пополнения<input aria-label="Сумма пополнения в рублях" inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} /> <span>₽</span></label>}<label className="amount-field">Бонусы<input aria-label="Количество бонусов" inputMode="numeric" value={bonusAmount} onChange={(event) => setBonusAmount(event.target.value)} /> <span>шт.</span></label>{searchError && result && <div className="form-error" role="alert">{searchError}</div>}<button className="primary-button wide" disabled={!result || submitting} onClick={() => void submit()}>{submitting ? "Зачисляем..." : bonusOnly ? "Начислить бонусы" : "Зачислить депозит"}</button><button className="secondary-button wide" onClick={onClose}>Отмена</button></div>;
}

function localDateTimeValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localDateInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

type PickerMode = "date" | "datetime" | "time";

function parsePickerValue(value: string, mode: PickerMode): Date {
  const fallback = new Date();
  if (mode === "time") {
    const { hour, minute } = pickerTimeValue(value);
    return new Date(fallback.getFullYear(), fallback.getMonth(), fallback.getDate(), hour, minute);
  }
  const [datePart, timePart = "00:00"] = value.split("T");
  const [year, month, day] = (datePart || localDateInputValue(new Date())).split("-").map(Number);
  const [hour, minute] = timePart.split(":").map(Number);
  return new Date(
    Number.isFinite(year) ? year : fallback.getFullYear(),
    Number.isFinite(month) ? month - 1 : fallback.getMonth(),
    Number.isFinite(day) ? day : fallback.getDate(),
    mode === "date" ? 12 : Number.isFinite(hour) ? hour : 0,
    mode === "date" ? 0 : Number.isFinite(minute) ? minute : 0,
  );
}

function pickerTimeValue(value: string): { hour: number; minute: number } {
  const [, timePart = "00:00"] = value.split("T");
  const [hour, minute] = timePart.split(":").map(Number);
  return {
    hour: Number.isFinite(hour) ? hour : 0,
    minute: Number.isFinite(minute) ? minute : 0,
  };
}

function DateTimePicker({
  value,
  onChange,
  mode,
  label,
  disabled = false,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  mode: PickerMode;
  label: string;
  disabled?: boolean;
  className?: string;
}) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectedDate = parsePickerValue(value, mode);
  const [open, setOpen] = useState(false);
  const [viewDate, setViewDate] = useState(selectedDate);
  const time = pickerTimeValue(value);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => {
    if (open) setViewDate(selectedDate);
  }, [open, value]);

  const dateText = selectedDate.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
  const displayValue = mode === "time"
    ? `${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`
    : mode === "date"
      ? dateText
      : `${dateText} · ${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}`;
  const monthLabel = viewDate.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
  const firstDay = new Date(viewDate.getFullYear(), viewDate.getMonth(), 1);
  const leadingDays = (firstDay.getDay() + 6) % 7;
  const daysInMonth = new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 0).getDate();
  const calendarDays = Array.from({ length: Math.ceil((leadingDays + daysInMonth) / 7) * 7 }, (_, index) => new Date(viewDate.getFullYear(), viewDate.getMonth(), index - leadingDays + 1));
  const selectedDateKey = localDateInputValue(selectedDate);

  const selectDate = (date: Date) => {
    const nextDate = localDateInputValue(date);
    onChange(mode === "datetime" ? `${nextDate}T${String(time.hour).padStart(2, "0")}:${String(time.minute).padStart(2, "0")}` : nextDate);
    setViewDate(date);
    if (mode === "date") setOpen(false);
  };
  const selectTime = (hour: number, minute: number) => {
    const date = localDateInputValue(selectedDate);
    onChange(mode === "time" ? `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}` : `${date}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`);
  };
  const jumpToToday = () => {
    const today = new Date();
    selectDate(today);
  };

  return <div className={`date-time-picker ${open ? "open" : ""} ${className}`} ref={wrapperRef} onClick={(event) => event.stopPropagation()}>
    <button type="button" className="date-time-trigger" aria-label={label} aria-expanded={open} disabled={disabled} onClick={() => setOpen((current) => !current)}>
      {mode === "time" ? <Clock3 size={15} /> : <CalendarDays size={15} />}
      <span>{displayValue}</span>
      <ChevronDown size={14} className="date-time-chevron" />
    </button>
    {open && <div className={`date-time-popover ${mode === "time" ? "time-only" : ""}`} role="dialog" aria-label={`${label}: выбор значения`}>
      {mode !== "time" && <>
        <div className="picker-month-head"><button type="button" aria-label="Предыдущий месяц" onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() - 1, 1))}><ChevronRight size={15} className="rotate-180" /></button><strong>{monthLabel}</strong><button type="button" aria-label="Следующий месяц" onClick={() => setViewDate(new Date(viewDate.getFullYear(), viewDate.getMonth() + 1, 1))}><ChevronRight size={15} /></button></div>
        <div className="picker-weekdays">{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => <span key={day}>{day}</span>)}</div>
        <div className="picker-calendar">{calendarDays.map((day) => <button type="button" key={localDateInputValue(day)} className={`${day.getMonth() !== viewDate.getMonth() ? "outside" : ""} ${localDateInputValue(day) === selectedDateKey ? "selected" : ""}`} onClick={() => selectDate(day)}>{day.getDate()}</button>)}</div>
        <button type="button" className="picker-today" onClick={jumpToToday}>Сегодня</button>
      </>}
      {mode !== "date" && <div className="picker-time-panel"><span>Время</span><div className="picker-time-selects"><label><span>Часы</span><select aria-label={`${label}: часы`} value={time.hour} onChange={(event) => selectTime(Number(event.target.value), time.minute)}>{Array.from({ length: 24 }, (_, hour) => <option value={hour} key={hour}>{String(hour).padStart(2, "0")}</option>)}</select></label><b>:</b><label><span>Минуты</span><select aria-label={`${label}: минуты`} value={time.minute} onChange={(event) => selectTime(time.hour, Number(event.target.value))}>{Array.from({ length: 60 }, (_, minute) => <option value={minute} key={minute}>{String(minute).padStart(2, "0")}</option>)}</select></label></div></div>}
      {mode !== "date" && <button type="button" className="picker-done" onClick={() => setOpen(false)}>Готово</button>}
    </div>}
  </div>;
}

function BookingPanel({
  initialWorkstationId,
  onClose,
  onCreated,
  pcs,
  api,
}: {
  initialWorkstationId?: string;
  onClose: () => void;
  onCreated: () => void;
  pcs: Workstation[];
  api?: GameClubApi;
}) {
  const now = useMemo(() => new Date(Date.now() + 30 * 60 * 1000), []);
  const [workstationId, setWorkstationId] = useState(initialWorkstationId ?? pcs[0]?.id ?? "");
  const [startAt, setStartAt] = useState(localDateTimeValue(now));
  const [endAt, setEndAt] = useState(localDateTimeValue(new Date(now.getTime() + 60 * 60 * 1000)));
  const [clientQuery, setClientQuery] = useState("");
  const [clientId, setClientId] = useState<string | undefined>();
  const [clientCandidate, setClientCandidate] = useState<Client | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const clientField = getSearchField(clientQuery);

  useEffect(() => {
    if (!workstationId && pcs[0]) {
      setWorkstationId(pcs[0].id);
    }
  }, [pcs, workstationId]);

  useEffect(() => {
    if (!api || !clientField) {
      setClientCandidate(undefined);
      return undefined;
    }
    let active = true;
    const timer = window.setTimeout(async () => {
      try {
        const found = await api.searchClients(clientQuery, clientField);
        if (active) {
          setClientCandidate(found[0] ? toUiClient(found[0]) : undefined);
        }
      } catch {
        if (active) {
          setClientCandidate(undefined);
        }
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [api, clientField, clientQuery]);

  const submit = async () => {
    if (!workstationId) {
      setError("Выберите игровое место");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      setError("Проверьте период бронирования");
      return;
    }
    if (!api) {
      onCreated();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const payload = {
        workstation_ids: [workstationId],
        client_id: clientId ?? null,
        guest_id: null,
        guest_name: clientId ? null : "Гость",
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        notes: null,
        tariff_id: null,
      };
      const availability = await api.checkReservationAvailability(payload);
      if (!availability.available) {
        setError(
          availability.reason === "workstation_disabled"
            ? "Игровое место отключено"
            : "Игровое место уже занято в выбранный период",
        );
        return;
      }
      await api.createReservation(payload, crypto.randomUUID());
      onCreated();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось создать бронь");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Новая бронь" subtitle="Игровое место и время" onClose={onClose} /><div className="booking-form"><label>Игровое место<select aria-label="Игровое место" value={workstationId} onChange={(event) => setWorkstationId(event.target.value)}>{pcs.map((pc) => <option value={pc.id} key={pc.id}>{pc.name} · {pc.group}</option>)}</select></label><label>Начало<DateTimePicker value={startAt} onChange={setStartAt} mode="datetime" label="Начало брони" /></label><label>Окончание<DateTimePicker value={endAt} onChange={setEndAt} mode="datetime" label="Окончание брони" /></label><label>Клиент <span className="field-hint">необязательно</span><input aria-label="Клиент" value={clientQuery} onChange={(event) => { setClientQuery(event.target.value); setClientId(undefined); }} placeholder="Ник или телефон" /></label>{clientCandidate && !clientId && <button className="client-result" onClick={() => { setClientId(clientCandidate.id); setClientQuery(clientCandidate.nickname); }}><div className="client-avatar">{clientCandidate.nickname.slice(0, 2).toUpperCase()}</div><div><strong>{clientCandidate.nickname}</strong><span>{formatRussianPhone(clientCandidate.phone)}</span></div><ChevronRight size={16} /></button>}<div className="guest-mode-card"><div className="guest-mode-icon"><UserX size={16} /></div><div><strong>{clientId ? "Бронь на клиента" : "Гостевая бронь"}</strong><span>{clientId ? "Ник клиента будет показан в расписании" : "Если клиент не выбран, участник будет указан как «Гость»"}</span></div></div>{error && <div className="form-error" role="alert">{error}</div>}<button className="primary-button wide" disabled={submitting || !pcs.length} onClick={() => void submit()}>{submitting ? "Создаём..." : "Создать бронь"}</button><button className="secondary-button wide" onClick={onClose}>Отмена</button></div></div>;
}

function BookingEditPanel({
  reservation,
  clients,
  onClose,
  onSaved,
  pcs,
  api,
}: {
  reservation: Reservation;
  clients: Client[];
  onClose: () => void;
  onSaved: () => void;
  pcs: Workstation[];
  api?: GameClubApi;
}) {
  const [workstationId, setWorkstationId] = useState(reservation.workstation_ids[0] ?? "");
  const [startAt, setStartAt] = useState(localDateTimeValue(new Date(reservation.start_at)));
  const [endAt, setEndAt] = useState(localDateTimeValue(new Date(reservation.end_at)));
  const [notes, setNotes] = useState(reservation.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const canEdit = reservation.status === "confirmed";
  const clientName = reservation.client_id
    ? clients.find((client) => client.id === reservation.client_id)?.nickname ?? "Клиент"
    : "Гость";

  const submit = async () => {
    if (!canEdit) {
      setError("Изменять можно только подтверждённую бронь");
      return;
    }
    const start = new Date(startAt);
    const end = new Date(endAt);
    if (!workstationId || !Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) {
      setError("Проверьте место и период бронирования");
      return;
    }
    if (!api) {
      onSaved();
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.updateReservation(reservation.id, {
        workstation_ids: workstationId === reservation.workstation_ids[0] ? reservation.workstation_ids : [workstationId],
        client_id: reservation.client_id,
        guest_id: reservation.guest_id,
        guest_name: reservation.client_id ? null : "Гость",
        start_at: start.toISOString(),
        end_at: end.toISOString(),
        notes: notes.trim() || null,
        tariff_id: reservation.tariff_id,
      });
      onSaved();
    } catch (requestError) {
      setError(requestError instanceof ApiError ? requestError.message : "Не удалось изменить бронь");
    } finally {
      setSubmitting(false);
    }
  };

  return <div className="panel-inner"><PanelHeader title="Бронь" subtitle="Подробности и изменение" onClose={onClose} /><div className="booking-form"><div className="detail-row"><span>Статус</span><strong>{reservation.status === "confirmed" ? "Подтверждена" : reservation.status}</strong></div><label>Игровое место<select aria-label="Игровое место брони" value={workstationId} onChange={(event) => setWorkstationId(event.target.value)} disabled={!canEdit}>{pcs.map((pc) => <option value={pc.id} key={pc.id}>{pc.name} · {pc.group}</option>)}</select></label><label>Начало<DateTimePicker value={startAt} onChange={setStartAt} mode="datetime" label="Начало изменяемой брони" disabled={!canEdit} /></label><label>Окончание<DateTimePicker value={endAt} onChange={setEndAt} mode="datetime" label="Окончание изменяемой брони" disabled={!canEdit} /></label><div className="detail-row"><span>Участник</span><strong>{clientName}</strong></div><label>Комментарий<textarea aria-label="Комментарий к брони" value={notes} onChange={(event) => setNotes(event.target.value)} disabled={!canEdit} rows={3} /></label>{!canEdit && <div className="search-hint">Для этой брони доступны только просмотр и действия в расписании.</div>}{error && <div className="form-error" role="alert">{error}</div>}{canEdit && <button className="primary-button wide" disabled={submitting} onClick={() => void submit()}>{submitting ? "Сохраняем..." : "Сохранить изменения"}</button>}<button className="secondary-button wide" onClick={onClose}>Закрыть</button></div></div>;
}

function PanelHeader({ title, subtitle, onClose }: { title: string; subtitle: string; onClose: () => void }) {
  return <div className="panel-header"><div><p>{subtitle}</p><h2>{title}</h2></div><button className="icon-button" aria-label={`Закрыть панель «${title}»`} onClick={onClose}><X size={18} /></button></div>;
}

export default App;
