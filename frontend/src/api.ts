export type BackendWorkstation = {
  id: string;
  device_id: string;
  mac_address: string | null;
  installation_bound: boolean;
  name: string;
  group_id: string | null;
  position: number | null;
  status: "unknown" | "online" | "stale" | "offline" | "disabled";
  last_seen_at: string | null;
  client_version: string | null;
  disabled_reason: string | null;
  capabilities?: string[];
  theme: "standard" | "vip" | "neon" | "minimal";
  archived_at?: string | null;
};

export function normalizePhoneQuery(value: string): string {
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("8")) {
    digits = `7${digits.slice(1)}`;
  }
  if (digits.length === 10) {
    digits = `7${digits}`;
  }
  return digits;
}

export type BackendLockdownPolicy = {
  deployment_mode: "app_gate" | "assigned_access" | "shell_launcher";
  shell_enabled: boolean;
  user_self_login_enabled: boolean;
  lock_after_session: boolean;
  restart_after_session: boolean;
  hidden_drives: string[];
  block_external_storage: boolean;
  disable_start_menu: boolean;
  disable_desktop_switching: boolean;
  blocked_window_rules: string[];
  allowed_application_ids: string[];
  version: number;
};

export type BackendWorkstationGroup = {
  id: string;
  name: string;
  theme: "standard" | "vip" | "neon" | "minimal";
  updated_at: string | null;
  lockdown_policy?: BackendLockdownPolicy;
};

export type BackendClient = {
  id: string;
  nickname: string;
  phone: string | null;
  discount_category: string | null;
  balance_cents: number;
  balance_bonus: number;
  created_at: string;
  updated_at: string;
};

export type BackendGuest = {
  id: string;
  nickname: string;
  phone: string | null;
  discount_category: string | null;
  created_at: string;
  updated_at: string;
};

export type BackendBalanceOperation = {
  id: string;
  client_id: string;
  operation_type: "top_up" | "debit";
  amount_cents: number;
  bonus_amount: number;
  reason: string;
  actor_id: string;
  idempotency_key: string;
  created_at: string;
  payment_parts: BackendPaymentPart[];
};

export type BackendPaymentPart = {
  method: string;
  amount_cents: number;
  reference?: string | null;
};

export type BackendEntitlement = {
  id: string;
  client_id: string;
  tariff_id: string;
  zone_id: string | null;
  duration_minutes: number;
  remaining_minutes: number;
  price_cents: number;
  queue_position: number;
  status: "queued" | "active" | "exhausted" | "burned";
  idempotency_key: string;
  purchased_at: string;
  activated_at: string | null;
  ended_at: string | null;
  burn_reason: string | null;
  window_start_minute?: number | null;
  window_end_minute?: number | null;
  window_timezone?: string | null;
};

export type BackendGuestSessionPayment = {
  id: string;
  workstation_id: string;
  tariff_id: string;
  tariff_quantity: number;
  guest_id: string | null;
  guest_name: string;
  total_price_cents: number;
  payment_parts: BackendPaymentPart[];
  cash_shift_id: string;
  status: "confirmed";
  idempotency_key: string;
  created_at: string;
};

export type BackendAuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  resource_path: string;
  outcome: "success" | "failure";
  status_code: number;
  request_id: string | null;
  created_at: string;
};

export type BackendCommand = {
  id: string;
  workstation_id: string;
  command_type: string;
  payload: Record<string, unknown>;
  idempotency_key: string;
  status: "queued" | "acknowledged" | "failed" | "expired";
  created_at: string;
  expires_at: string;
  acknowledged_at: string | null;
  acknowledgement_message: string | null;
};

export type BackendTariff = {
  id: string;
  name: string;
  group_id: string | null;
  duration_minutes: number;
  price_cents: number;
  valid_from: string;
  valid_to: string | null;
  active: boolean;
  tariff_key: string;
  version: number;
  lifecycle: "draft" | "published" | "archived";
  billing_mode: "block" | "per_minute";
  price_per_minute_cents: number;
  free_minutes: number;
  window_start_minute?: number | null;
  window_end_minute?: number | null;
  window_timezone?: string | null;
};

export type BackendDiscountRule = {
  id: string;
  category: string;
  percent_bps: number;
  priority: number;
  valid_from: string;
  valid_to: string | null;
  active: boolean;
};

export type BackendQuote = {
  tariff_id: string;
  duration_minutes: number;
  price_cents: number;
  price_before_discount_cents: number;
  discount_amount_cents: number;
  discount_percent_bps: number;
  discount_category: string | null;
};

export type BackendCatalogSnapshot = {
  tariffs: BackendTariff[];
  discount_rules: BackendDiscountRule[];
};

export type BackendProduct = {
  id: string;
  name: string;
  category: string;
  price_cents: number;
  active: boolean;
  cost_price_cents: number;
  stock_quantity: number;
};

export type BackendProductSale = {
  id: string;
  product_id: string;
  product_name: string;
  product_category: string;
  client_id: string | null;
  guest_name: string | null;
  quantity: number;
  unit_price_cents: number;
  unit_cost_price_cents: number;
  total_price_cents: number;
  total_cost_price_cents: number;
  payment_method: "balance" | "cash" | "mixed";
  cash_shift_id: string | null;
  status: "pending" | "completed" | "cancelled" | "needs_review";
  sold_by: string;
  idempotency_key: string;
  created_at: string;
  completed_at: string | null;
  payment_parts: BackendPaymentPart[];
  settlement_error: string | null;
};

export type BackendTopProduct = {
  product_id: string;
  product_name: string;
  units: number;
  revenue_cents: number;
  gross_profit_cents: number;
};

export type BackendTopClient = {
  client_id: string;
  nickname: string;
  session_count: number;
  played_minutes: number;
  session_spend_cents: number;
  product_spend_cents: number;
  product_units: number;
  total_spend_cents: number;
};

export type BackendAnalyticsBucket = {
  key: string;
  label: string;
  session_revenue_cents: number;
  product_revenue_cents: number;
  total_revenue_cents: number;
  session_count: number;
  product_sale_count: number;
  product_units: number;
  played_minutes: number;
  guest_session_count: number;
};

export type BackendAnalyticsBreakdown = {
  key: string;
  label: string;
  session_revenue_cents: number;
  product_revenue_cents: number;
  revenue_cents: number;
  product_cost_cents: number;
  gross_profit_cents: number;
  session_count: number;
  product_sale_count: number;
  product_units: number;
  played_minutes: number;
  share_bps: number;
  discount_cents: number;
};

export type BackendAnalyticsPayment = {
  key: string;
  label: string;
  revenue_cents: number;
  operation_count: number;
  share_bps: number;
};

export type BackendAnalyticsOverview = {
  start_at: string;
  end_at: string;
  session_revenue_cents: number;
  product_revenue_cents: number;
  total_revenue_cents: number;
  session_count: number;
  product_sale_count: number;
  product_units: number;
  played_minutes: number;
  average_session_minutes: number;
  guest_session_count: number;
  client_count: number;
  top_products: BackendTopProduct[];
  top_clients: BackendTopClient[];
  product_cost_cents: number;
  gross_profit_cents: number;
  discount_cents: number;
  active_client_count: number;
  new_client_count: number;
  returning_client_count: number;
  unique_visitor_count: number;
  workstation_count: number;
  occupancy_percent: number;
  peak_usage_hour: string | null;
  daily_activity: BackendAnalyticsBucket[];
  hourly_activity: BackendAnalyticsBucket[];
  zones: BackendAnalyticsBreakdown[];
  workstations: BackendAnalyticsBreakdown[];
  tariffs: BackendAnalyticsBreakdown[];
  payment_methods: BackendAnalyticsPayment[];
  product_categories: BackendAnalyticsBreakdown[];
};

export type BackendClientAnalytics = {
  client_id: string;
  nickname: string;
  phone: string | null;
  start_at: string;
  end_at: string;
  played_minutes: number;
  played_hours: number;
  session_count: number;
  average_session_minutes: number;
  session_spend_cents: number;
  product_spend_cents: number;
  total_spend_cents: number;
  product_units: number;
  product_cost_cents: number;
  first_session_at: string | null;
  last_session_at: string | null;
  last_purchase_at: string | null;
  favorite_products: BackendTopProduct[];
  daily_activity: BackendAnalyticsBucket[];
  payment_methods: BackendAnalyticsPayment[];
};

export type BackendProductCategory = {
  id: string;
  name: string;
  kind: "product" | "drink";
  active: boolean;
};

export type BackendPaymentMethod = {
  id: string;
  key: string;
  name: string;
  active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string;
};

export type Reservation = {
  id: string;
  workstation_ids: string[];
  client_id: string | null;
  guest_id: string | null;
  guest_name: string | null;
  start_at: string;
  end_at: string;
  status: string;
  notes: string | null;
  tariff_id: string | null;
  created_by: string;
  created_at: string;
  cancelled_at: string | null;
  idempotency_key: string | null;
};

export type ReservationWritePayload = Omit<
  Reservation,
  "id" | "status" | "created_by" | "created_at" | "cancelled_at" | "idempotency_key"
>;

export type ReservationAvailability = {
  available: boolean;
  conflicting_reservation_ids: string[];
  reason: "workstation_reserved" | "workstation_disabled" | null;
};

export type BackendSession = {
  id: string;
  workstation_id: string;
  client_id: string | null;
  guest_id: string | null;
  guest_name: string | null;
  status: "active" | "completed";
  started_at: string;
  ended_at: string | null;
  source: string;
  created_by: string;
  created_at: string;
  reservation_id: string | null;
  idempotency_key: string | null;
  tariff_id: string | null;
  tariff_quantity: number;
  guest_payment_id: string | null;
  login_grant_minutes: number;
  entitlement_id: string | null;
};

export type BackendSessionSnapshot = {
  schema_version: number;
  server_time: string;
  session: BackendSession;
  workstation_id: string;
  zone_id: string | null;
  client_id: string | null;
  balance_cents: number | null;
  balance_bonus: number | null;
  active_entitlement: BackendSnapshotEntitlement | null;
  entitlements: BackendSnapshotEntitlement[];
  meter: BackendSessionMeter | null;
  allowed_actions: string[];
};

export type BackendSnapshotEntitlement = {
  id: string;
  tariff_id: string;
  zone_id: string | null;
  duration_minutes: number;
  remaining_minutes: number;
  status: "queued" | "active" | "exhausted" | "burned";
  queue_position: number;
  window_start_minute: number | null;
  window_end_minute: number | null;
  window_timezone: string | null;
};

export type BackendSessionMeter = {
  session_id: string;
  client_id: string;
  tariff_id: string;
  billed_minutes: number;
  billed_cents: number;
  package_minutes: number;
  active_entitlement_id: string | null;
  status: "running" | "exhausted" | "settled";
  updated_at: string;
};

export type BackendTransferOffer = {
  id: string;
  session_id: string;
  client_id: string;
  source_workstation_id: string;
  target_workstation_id: string;
  token: string;
  status: "pending" | "confirmed" | "expired" | "rejected";
  requires_package_burn: boolean;
  warning: string | null;
  created_at: string;
  expires_at: string;
  confirmed_at: string | null;
};

export type BackendTransferResult = {
  offer: BackendTransferOffer;
  session_id: string;
  workstation_id: string;
  status: "active" | "completed";
};

export type BackendSessionCharge = {
  id: string;
  session_id: string;
  client_id: string;
  balance_operation_id: string;
  tariff_id: string;
  duration_minutes: number;
  amount_cents: number;
  amount_before_discount_cents: number;
  discount_amount_cents: number;
  discount_percent_bps: number;
  discount_category: string | null;
  charged_by: string;
  idempotency_key: string;
  created_at: string;
  client_balance_cents: number;
  client_balance_bonus: number;
};

export type BackendRevenueSummary = {
  start_at: string;
  end_at: string;
  amount_cents: number;
  charge_count: number;
};

export type BackendCashShift = {
  id: string;
  register_id: string;
  opened_by: string;
  opened_at: string;
  opening_balance_cents: number;
  expected_close_cents: number;
  status: "open" | "closed";
  closed_by: string | null;
  closed_at: string | null;
  actual_close_cents: number | null;
  difference_cents: number | null;
};

export type BackendCashMovement = {
  id: string;
  shift_id: string;
  direction: "cash_in" | "cash_out" | "correction";
  amount_cents: number;
  reason: string;
  actor_id: string;
  idempotency_key: string;
  created_at: string;
  reference_type: string | null;
  reference_id: string | null;
};

export type BackendCashApproval = {
  id: string;
  shift_id: string;
  kind: "correction" | "close_difference";
  target_key: string;
  approved_by: string;
  reason: string;
  idempotency_key: string;
  created_at: string;
};

export type BackendCashShiftSchedule = {
  register_id: string;
  timezone: string;
  auto_open: boolean;
  auto_open_at: string | null;
  auto_close: boolean;
  auto_close_at: string | null;
  opening_balance_cents: number;
};

export type StartSessionPayload = {
  workstation_id: string;
  client_id?: string;
  guest_id?: string;
  guest_name?: string;
  source?: string;
  reservation_id?: string;
  tariff_id?: string;
  tariff_quantity?: number;
  guest_payment_id?: string;
  entitlement_id?: string;
};

export type BackendEntryDecision = {
  allowed: boolean;
  reason: string;
  reservation_id: string | null;
  assigned_client_id: string | null;
  starts_at: string | null;
  ends_at: string | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export class GameClubApi {
  private readonly baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private refreshInFlight: Promise<boolean> | null = null;
  private static readonly refreshStorageKey = "gameshell.refresh-token";

  constructor(baseUrl = import.meta.env.VITE_API_URL ?? "/api/v1") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async login(username: string, password: string): Promise<void> {
    this.clearSession();
    const token = await this.request<TokenResponse>("/auth/token", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.accessToken = token.access_token;
    this.refreshToken = token.refresh_token ?? null;
    this.persistRefreshToken();
  }

  async restoreSession(): Promise<boolean> {
    if (!this.refreshToken) {
      try {
        this.refreshToken = window.localStorage.getItem(GameClubApi.refreshStorageKey);
      } catch {
        this.refreshToken = null;
      }
    }
    return this.refreshAccessToken();
  }

  clearSession(): void {
    this.accessToken = null;
    this.refreshToken = null;
    try {
      window.localStorage.removeItem(GameClubApi.refreshStorageKey);
    } catch {
      // Storage can be disabled by browser privacy settings.
    }
  }

  private persistRefreshToken(): void {
    try {
      if (this.refreshToken) {
        window.localStorage.setItem(GameClubApi.refreshStorageKey, this.refreshToken);
      }
    } catch {
      // The in-memory session still works when persistent storage is unavailable.
    }
  }

  get isAuthenticated(): boolean {
    return this.accessToken !== null;
  }

  async listWorkstations(): Promise<BackendWorkstation[]> {
    return this.request<BackendWorkstation[]>("/workstations");
  }

  async registerWorkstation(payload: {
    device_id?: string;
    mac_address: string;
    name: string;
    group_id: string | null;
    position: number | null;
    capabilities: string[];
  }): Promise<BackendWorkstation> {
    return this.request<BackendWorkstation>("/workstations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async disableWorkstation(workstationId: string, reason: string): Promise<BackendWorkstation> {
    return this.request<BackendWorkstation>(`/workstations/${workstationId}/disable`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  }

  async updateWorkstation(workstationId: string, payload: { name: string; mac_address: string | null; group_id: string | null; position: number | null }): Promise<BackendWorkstation> {
    return this.request<BackendWorkstation>(`/workstations/${workstationId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async enableWorkstation(workstationId: string): Promise<BackendWorkstation> {
    return this.request<BackendWorkstation>(`/workstations/${workstationId}/enable`, { method: "POST" });
  }

  async deleteWorkstation(workstationId: string): Promise<void> {
    await this.request<void>(`/workstations/${workstationId}`, { method: "DELETE" });
  }

  async listWorkstationGroups(): Promise<BackendWorkstationGroup[]> {
    return this.request<BackendWorkstationGroup[]>("/workstation-groups");
  }

  async saveWorkstationGroup(
    groupId: string,
    payload: { name: string; theme: BackendWorkstationGroup["theme"] },
  ): Promise<BackendWorkstationGroup> {
    return this.request<BackendWorkstationGroup>(`/workstation-groups/${encodeURIComponent(groupId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async createWorkstationGroup(payload: { name: string; theme: BackendWorkstationGroup["theme"] }): Promise<BackendWorkstationGroup> {
    return this.request<BackendWorkstationGroup>("/workstation-groups", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async deleteWorkstationGroup(groupId: string): Promise<void> {
    await this.request<void>(`/workstation-groups/${encodeURIComponent(groupId)}`, { method: "DELETE" });
  }

  async setWorkstationGroupManagerPassword(groupId: string, password: string): Promise<void> {
    await this.request<void>(`/workstation-groups/${encodeURIComponent(groupId)}/manager-password`, {
      method: "PUT",
      body: JSON.stringify({ password }),
    });
  }

  async setWorkstationGroupLockdownPolicy(groupId: string, policy: BackendLockdownPolicy): Promise<BackendWorkstationGroup> {
    return this.request<BackendWorkstationGroup>(`/workstation-groups/${encodeURIComponent(groupId)}/lockdown-policy`, {
      method: "PUT",
      body: JSON.stringify(policy),
    });
  }

  async listSessions(activeOnly = false, workstationId?: string): Promise<BackendSession[]> {
    const params = new URLSearchParams({ active_only: String(activeOnly) });
    if (workstationId) {
      params.set("workstation_id", workstationId);
    }
    return this.request<BackendSession[]>(`/sessions?${params}`);
  }

  async getSessionSnapshot(sessionId: string): Promise<BackendSessionSnapshot> {
    return this.request<BackendSessionSnapshot>(`/sessions/${sessionId}/snapshot`);
  }

  async createTransferOffer(
    sessionId: string,
    targetWorkstationId: string,
    idempotencyKey: string,
  ): Promise<BackendTransferOffer> {
    return this.request<BackendTransferOffer>("/session-transfers/offers", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({
        session_id: sessionId,
        target_workstation_id: targetWorkstationId,
      }),
    });
  }

  async getTransferOffer(offerId: string): Promise<BackendTransferOffer> {
    return this.request<BackendTransferOffer>(`/session-transfers/offers/${offerId}`);
  }

  async confirmTransfer(offerId: string, idempotencyKey: string): Promise<BackendTransferResult> {
    return this.request<BackendTransferResult>(`/session-transfers/offers/${offerId}/confirm`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  async checkEntry(
    workstationId: string,
    clientId?: string,
    guestId?: string,
  ): Promise<BackendEntryDecision> {
    const params = new URLSearchParams({ workstation_id: workstationId });
    if (clientId) params.set("client_id", clientId);
    if (guestId) params.set("guest_id", guestId);
    return this.request<BackendEntryDecision>(`/reservations/entry-decision?${params}`);
  }

  async chargeSession(sessionId: string, idempotencyKey: string): Promise<BackendSessionCharge> {
    return this.request<BackendSessionCharge>(`/billing/sessions/${sessionId}/charge`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
    });
  }

  async startSession(
    payload: StartSessionPayload,
    idempotencyKey: string,
  ): Promise<BackendSession> {
    return this.request<BackendSession>("/sessions", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async stopSession(sessionId: string): Promise<BackendSession> {
    return this.request<BackendSession>(`/sessions/${sessionId}/stop`, { method: "POST" });
  }

  async interruptSession(
    sessionId: string,
    reason: string,
    idempotencyKey: string,
  ): Promise<BackendSession> {
    return this.request<BackendSession>(`/sessions/${sessionId}/interrupt`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ reason }),
    });
  }

  async getSessionCharge(sessionId: string): Promise<BackendSessionCharge> {
    return this.request<BackendSessionCharge>(`/billing/sessions/${sessionId}/charge`);
  }

  async getSessionMeter(sessionId: string): Promise<BackendSessionMeter> {
    return this.request<BackendSessionMeter>(`/billing/sessions/${sessionId}/meter`);
  }

  async getRevenue(startAt: string, endAt: string): Promise<BackendRevenueSummary> {
    const params = new URLSearchParams({ start_at: startAt, end_at: endAt });
    return this.request<BackendRevenueSummary>(`/billing/revenue?${params}`);
  }

  async listCashShifts(limit = 50): Promise<BackendCashShift[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<BackendCashShift[]>(`/cash-shifts?${params}`);
  }

  async openCashShift(
    payload: { register_id: string; opening_balance_cents: number },
    idempotencyKey: string,
  ): Promise<BackendCashShift> {
    return this.request<BackendCashShift>("/cash-shifts", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async listCashMovements(shiftId: string, limit = 50): Promise<BackendCashMovement[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<BackendCashMovement[]>(`/cash-shifts/${shiftId}/movements?${params}`);
  }

  async recordCashMovement(
    shiftId: string,
    payload: {
      direction: BackendCashMovement["direction"];
      amount_cents: number;
      reason: string;
      reference_type?: string;
      reference_id?: string;
      approval_id?: string;
    },
    idempotencyKey: string,
  ): Promise<BackendCashMovement> {
    return this.request<BackendCashMovement>(`/cash-shifts/${shiftId}/movements`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async closeCashShift(
    shiftId: string,
    actualCloseCents: number,
    idempotencyKey: string,
    approvalId?: string,
  ): Promise<BackendCashShift> {
    return this.request<BackendCashShift>(`/cash-shifts/${shiftId}/close`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ actual_close_cents: actualCloseCents, approval_id: approvalId }),
    });
  }

  async createCashApproval(
    shiftId: string,
    payload: { kind: BackendCashApproval["kind"]; target_key: string; reason: string },
    idempotencyKey: string,
  ): Promise<BackendCashApproval> {
    return this.request<BackendCashApproval>(`/cash-shifts/${shiftId}/approvals`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async dispatchWorkstationCommand(
    workstationId: string,
    commandType: string,
    payload: Record<string, unknown>,
    idempotencyKey: string,
  ): Promise<BackendCommand> {
    return this.request<BackendCommand>(`/workstations/${workstationId}/commands`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ command_type: commandType, payload }),
    });
  }

  async getWorkstationCommand(workstationId: string, commandId: string): Promise<BackendCommand> {
    return this.request<BackendCommand>(`/workstations/${workstationId}/commands/${commandId}`);
  }

  async searchClients(query: string, field: "nickname" | "phone"): Promise<BackendClient[]> {
    const normalizedQuery = field === "phone" ? normalizePhoneQuery(query) : query.trim();
    const params = new URLSearchParams({ q: normalizedQuery, field });
    return this.request<BackendClient[]>(`/clients/search?${params}`);
  }

  async listClients(): Promise<BackendClient[]> {
    return this.request<BackendClient[]>("/clients");
  }

  async createClient(payload: {
    nickname: string;
    phone?: string;
    discount_category?: string;
  }): Promise<BackendClient> {
    return this.request<BackendClient>("/clients", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateClient(
    clientId: string,
    payload: { nickname: string; phone?: string; discount_category?: string },
  ): Promise<BackendClient> {
    return this.request<BackendClient>(`/clients/${clientId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async deleteClient(clientId: string): Promise<void> {
    await this.request<void>(`/clients/${clientId}`, { method: "DELETE" });
  }

  async resetClientPassword(clientId: string): Promise<{ temporary_password: string }> {
    return this.request<{ temporary_password: string }>(`/clients/${clientId}/reset-password`, {
      method: "POST",
    });
  }

  async searchGuests(query: string, field: "nickname" | "phone"): Promise<BackendGuest[]> {
    const normalizedQuery = field === "phone" ? normalizePhoneQuery(query) : query.trim();
    const params = new URLSearchParams({ q: normalizedQuery, field });
    return this.request<BackendGuest[]>(`/guests/search?${params}`);
  }

  async listGuests(): Promise<BackendGuest[]> {
    return this.request<BackendGuest[]>("/guests");
  }

  async createGuest(payload: {
    nickname: string;
    phone?: string;
    discount_category?: string;
  }): Promise<BackendGuest> {
    return this.request<BackendGuest>("/guests", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async getGuest(guestId: string): Promise<BackendGuest> {
    return this.request<BackendGuest>(`/guests/${guestId}`);
  }

  async listClientOperations(clientId: string, limit = 20): Promise<BackendBalanceOperation[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<BackendBalanceOperation[]>(`/clients/${clientId}/balance-operations?${params}`);
  }

  async listAuditEvents(limit = 8): Promise<BackendAuditEvent[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return this.request<BackendAuditEvent[]>(`/audit/events?${params}`);
  }

  async topUp(
    clientId: string,
    payload: {
      amount_cents: number;
      bonus_amount: number;
      reason: string;
      payment_parts?: BackendPaymentPart[];
    },
    idempotencyKey: string,
  ): Promise<BackendClient> {
    const response = await this.request<{ client: BackendClient }>(`/clients/${clientId}/top-up`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
    return response.client;
  }

  async listClientEntitlements(clientId: string): Promise<BackendEntitlement[]> {
    return this.request<BackendEntitlement[]>(`/clients/${clientId}/entitlements`);
  }

  async purchaseEntitlement(
    clientId: string,
    tariffId: string,
    idempotencyKey: string,
  ): Promise<BackendEntitlement> {
    return this.request<BackendEntitlement>(`/clients/${clientId}/entitlements`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ tariff_id: tariffId }),
    });
  }

  async activateEntitlement(clientId: string, entitlementId: string): Promise<BackendEntitlement> {
    return this.request<BackendEntitlement>(
      `/clients/${clientId}/entitlements/${entitlementId}/activate`,
      { method: "POST" },
    );
  }

  async confirmGuestSessionPayment(
    payload: {
      workstation_id: string;
      tariff_id: string;
      tariff_quantity?: number;
      guest_id?: string;
      guest_name?: string;
      cash_shift_id: string;
      payment_parts: BackendPaymentPart[];
    },
    idempotencyKey: string,
  ): Promise<BackendGuestSessionPayment> {
    return this.request<BackendGuestSessionPayment>("/guest-payments", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }


  async listReservations(startAt: string, endAt: string): Promise<Reservation[]> {
    const params = new URLSearchParams({ start_at: startAt, end_at: endAt });
    return this.request<Reservation[]>(`/reservations?${params}`);
  }

  async listTariffs(): Promise<BackendTariff[]> {
    return this.request<BackendTariff[]>("/catalog/tariffs");
  }

  async createTariff(payload: {
    name: string;
    group_id: string | null;
    duration_minutes: number;
    price_cents: number;
    valid_from: string;
    lifecycle: "draft" | "published";
    billing_mode?: "block" | "per_minute";
    price_per_minute_cents?: number;
    free_minutes?: number;
    window_start_minute?: number;
    window_end_minute?: number;
    window_timezone?: string;
  }): Promise<BackendTariff> {
    return this.request<BackendTariff>("/catalog/tariffs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async listProducts(): Promise<BackendProduct[]> {
    return this.request<BackendProduct[]>("/catalog/products");
  }

  async createProduct(payload: {
    name: string;
    category: string;
    price_cents: number;
    cost_price_cents?: number;
    stock_quantity?: number;
    active?: boolean;
  }): Promise<BackendProduct> {
    return this.request<BackendProduct>("/catalog/products", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateProduct(
    productId: string,
    payload: { name: string; category: string; price_cents: number; cost_price_cents: number; stock_quantity: number; active: boolean },
  ): Promise<BackendProduct> {
    return this.request<BackendProduct>(`/catalog/products/${productId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async deleteProduct(productId: string): Promise<void> {
    await this.request<void>(`/catalog/products/${productId}`, { method: "DELETE" });
  }

  async sellProduct(
    payload: {
      product_id: string;
      quantity: number;
      client_id?: string;
      payment_method: "balance" | "cash" | "mixed";
      cash_shift_id?: string;
      payment_parts?: BackendPaymentPart[];
    },
    idempotencyKey: string,
  ): Promise<BackendProductSale> {
    return this.request<BackendProductSale>("/sales", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async listSales(params: { startAt?: string; endAt?: string; clientId?: string; limit?: number } = {}): Promise<BackendProductSale[]> {
    const query = new URLSearchParams();
    if (params.startAt) query.set("start_at", params.startAt);
    if (params.endAt) query.set("end_at", params.endAt);
    if (params.clientId) query.set("client_id", params.clientId);
    query.set("limit", String(params.limit ?? 100));
    return this.request<BackendProductSale[]>(`/sales?${query}`);
  }

  async getAnalyticsOverview(startAt: string, endAt: string, limit = 10): Promise<BackendAnalyticsOverview> {
    const query = new URLSearchParams({ start_at: startAt, end_at: endAt, limit: String(limit) });
    return this.request<BackendAnalyticsOverview>(`/analytics/overview?${query}`);
  }

  async downloadAnalyticsCsv(startAt: string, endAt: string, limit = 10): Promise<Blob> {
    const query = new URLSearchParams({ start_at: startAt, end_at: endAt, limit: String(limit) });
    return this.requestBlob(`/analytics/overview.csv?${query}`);
  }

  async getClientAnalytics(clientId: string, startAt: string, endAt: string, limit = 10): Promise<BackendClientAnalytics> {
    const query = new URLSearchParams({ start_at: startAt, end_at: endAt, limit: String(limit) });
    return this.request<BackendClientAnalytics>(`/analytics/clients/${clientId}?${query}`);
  }

  async listProductCategories(): Promise<BackendProductCategory[]> {
    return this.request<BackendProductCategory[]>("/catalog/categories");
  }

  async listPaymentMethods(): Promise<BackendPaymentMethod[]> {
    return this.request<BackendPaymentMethod[]>("/payment-methods");
  }

  async createPaymentMethod(payload: {
    key: string;
    name: string;
    active: boolean;
    sort_order: number;
  }): Promise<BackendPaymentMethod> {
    return this.request<BackendPaymentMethod>("/payment-methods", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updatePaymentMethod(
    methodId: string,
    payload: { key: string; name: string; active: boolean; sort_order: number },
  ): Promise<BackendPaymentMethod> {
    return this.request<BackendPaymentMethod>(`/payment-methods/${encodeURIComponent(methodId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async deletePaymentMethod(methodId: string): Promise<void> {
    await this.request<void>(`/payment-methods/${encodeURIComponent(methodId)}`, { method: "DELETE" });
  }

  async createProductCategory(payload: { id?: string; name: string; kind: BackendProductCategory["kind"] }): Promise<BackendProductCategory> {
    return this.request<BackendProductCategory>("/catalog/categories", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateProductCategory(categoryId: string, payload: { name: string; kind: BackendProductCategory["kind"] }): Promise<BackendProductCategory> {
    return this.request<BackendProductCategory>(`/catalog/categories/${encodeURIComponent(categoryId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
  }

  async deleteProductCategory(categoryId: string): Promise<void> {
    await this.request<void>(`/catalog/categories/${encodeURIComponent(categoryId)}`, { method: "DELETE" });
  }

  async listCashShiftSchedules(): Promise<BackendCashShiftSchedule[]> {
    return this.request<BackendCashShiftSchedule[]>("/cash-shifts/schedules");
  }

  async saveCashShiftSchedule(registerId: string, payload: Omit<BackendCashShiftSchedule, "register_id">): Promise<BackendCashShiftSchedule> {
    return this.request<BackendCashShiftSchedule>(`/cash-shifts/schedules/${encodeURIComponent(registerId)}`, {
      method: "PUT",
      body: JSON.stringify({ register_id: registerId, ...payload }),
    });
  }

  async publishTariff(tariffId: string): Promise<BackendTariff> {
    return this.request<BackendTariff>(`/catalog/tariffs/${tariffId}/publish`, { method: "POST" });
  }

  async archiveTariff(tariffId: string): Promise<BackendTariff> {
    return this.request<BackendTariff>(`/catalog/tariffs/${tariffId}/archive`, { method: "POST" });
  }

  async listDiscountRules(): Promise<BackendDiscountRule[]> {
    return this.request<BackendDiscountRule[]>("/catalog/discount-rules");
  }

  async createDiscountRule(payload: {
    category: string;
    percent_bps: number;
    priority: number;
    valid_from: string;
  }): Promise<BackendDiscountRule> {
    return this.request<BackendDiscountRule>("/catalog/discount-rules", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async getCatalogSnapshot(): Promise<BackendCatalogSnapshot> {
    return this.request<BackendCatalogSnapshot>("/catalog/snapshot");
  }

  async quote(
    durationMinutes: number,
    groupId: string | null,
    moment: string,
    discountCategory: string | null = null,
  ): Promise<BackendQuote> {
    return this.request<BackendQuote>("/catalog/quote", {
      method: "POST",
      body: JSON.stringify({
        duration_minutes: durationMinutes,
        group_id: groupId,
        moment,
        discount_category: discountCategory,
      }),
    });
  }

  async createReservation(
    payload: ReservationWritePayload,
    idempotencyKey: string,
  ): Promise<Reservation> {
    return this.request<Reservation>("/reservations", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    });
  }

  async checkReservationAvailability(
    payload: Pick<ReservationWritePayload, "workstation_ids" | "start_at" | "end_at">,
  ): Promise<ReservationAvailability> {
    return this.request<ReservationAvailability>("/reservations/check-availability", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async cancelReservation(reservationId: string): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}/cancel`, {
      method: "POST",
    });
  }

  async getReservation(reservationId: string): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}`);
  }

  async updateReservation(
    reservationId: string,
    payload: ReservationWritePayload,
  ): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async activateReservation(reservationId: string): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}/activate`, {
      method: "POST",
    });
  }

  async completeReservation(reservationId: string): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}/complete`, {
      method: "POST",
    });
  }

  async markNoShowReservation(reservationId: string): Promise<Reservation> {
    return this.request<Reservation>(`/reservations/${reservationId}/no-show`, {
      method: "POST",
    });
  }

  private async request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Content-Type", "application/json");
    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers });
    if ((response.status === 401 || response.status === 403) && retry && this.refreshToken && path !== "/auth/refresh") {
      if (await this.refreshAccessToken()) {
        return this.request<T>(path, init, false);
      }
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string;
        detail?: string;
        code?: string;
      };
      throw new ApiError(
        response.status,
        body.message ?? body.detail ?? "Не удалось выполнить запрос",
        body.code,
      );
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  private async requestBlob(path: string, retry = true): Promise<Blob> {
    const headers = new Headers();
    if (this.accessToken) {
      headers.set("Authorization", `Bearer ${this.accessToken}`);
    }
    const response = await fetch(`${this.baseUrl}${path}`, { headers });
    if ((response.status === 401 || response.status === 403) && retry && this.refreshToken && path !== "/auth/refresh") {
      if (await this.refreshAccessToken()) {
        return this.requestBlob(path, false);
      }
    }
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        message?: string;
        detail?: string;
        code?: string;
      };
      throw new ApiError(
        response.status,
        body.message ?? body.detail ?? "Не удалось выполнить запрос",
        body.code,
      );
    }
    return response.blob();
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.refreshToken) {
      return false;
    }
    if (!this.refreshInFlight) {
      const refreshToken = this.refreshToken;
      this.refreshInFlight = (async () => {
        try {
          const response = await fetch(`${this.baseUrl}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });
          if (response.status === 401) {
            this.clearSession();
            return false;
          }
          if (!response.ok) {
            return false;
          }
          const token = (await response.json()) as TokenResponse;
          if (!token.access_token || !token.refresh_token) {
            return false;
          }
          this.accessToken = token.access_token;
          this.refreshToken = token.refresh_token;
          this.persistRefreshToken();
          return true;
        } catch {
          // A temporary network/backend outage must not destroy a valid long-lived session.
          return false;
        }
      })().finally(() => {
        this.refreshInFlight = null;
      });
    }
    return this.refreshInFlight;
  }
}
