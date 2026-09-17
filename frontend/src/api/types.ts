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
  active_session_id?: string | null;
  active_session_status?: string | null;
  session_server_time?: string | null;
  session_snapshot?: BackendSessionSnapshot | null;
};

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
  per_minute_price_cents: number;
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
  time_restricted?: boolean;
  sale_window_start_minute?: number | null;
  sale_window_end_minute?: number | null;
  usage_window_start_minute?: number | null;
  usage_window_end_minute?: number | null;
  window_timezone?: string | null;
  audience?: "all" | "guest" | "registered";
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
  status: "pending" | "confirmed" | "needs_review";
  idempotency_key: string;
  created_at: string;
  attempts: number;
  next_attempt_at: string;
  settlement_error: string | null;
};

export type BackendAuditEvent = {
  id: string;
  actor_id: string | null;
  action: string;
  resource_path: string;
  outcome: "success" | "failure" | "retryable" | "needs_review" | "cancelled" | "pending";
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
  time_restricted?: boolean;
  sale_window_start_minute?: number | null;
  sale_window_end_minute?: number | null;
  usage_window_start_minute?: number | null;
  usage_window_end_minute?: number | null;
  window_timezone?: string | null;
  audience?: "all" | "guest" | "registered";
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
  payment_method: "balance" | "cash" | "transfer" | "mixed";
  cash_shift_id: string | null;
  status: "pending" | "completed" | "cancelled" | "needs_review";
  sold_by: string;
  idempotency_key: string;
  created_at: string;
  completed_at: string | null;
  payment_parts: BackendPaymentPart[];
  settlement_error: string | null;
  attempts: number;
  next_attempt_at: string;
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

export type TokenResponse = {
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
  active_tariff: BackendSessionTariff | null;
  login_grant_remaining_minutes: number;
  allowed_actions: string[];
  device_id?: string;
};

export type BackendSessionTariff = {
  id: string;
  name: string;
  billing_mode: string;
  duration_minutes: number;
  quantity: number;
  elapsed_minutes: number;
  remaining_minutes: number;
};

export type BackendSnapshotEntitlement = {
  id: string;
  tariff_id: string;
  zone_id: string | null;
  duration_minutes: number;
  remaining_minutes: number;
  status: "queued" | "active" | "exhausted" | "burned";
  queue_position: number;
  time_restricted?: boolean;
  sale_window_start_minute: number | null;
  sale_window_end_minute: number | null;
  usage_window_start_minute: number | null;
  usage_window_end_minute: number | null;
  window_timezone: string | null;
  audience?: "all" | "guest" | "registered";
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
