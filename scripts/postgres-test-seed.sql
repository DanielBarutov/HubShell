BEGIN;

INSERT INTO clients (
    id,
    nickname,
    phone,
    discount_category,
    balance_cents,
    balance_bonus,
    created_at,
    updated_at
) VALUES (
    '00000000-0000-0000-0000-000000000001',
    'seed-analytics-client',
    '+79990000001',
    NULL,
    700,
    0,
    '2026-09-20T08:00:00+00:00',
    '2026-09-20T10:00:00+00:00'
)
ON CONFLICT (id) DO UPDATE SET
    balance_cents = EXCLUDED.balance_cents,
    updated_at = EXCLUDED.updated_at;

INSERT INTO balance_operations (
    id,
    client_id,
    amount_cents,
    bonus_amount,
    reason,
    actor_id,
    idempotency_key,
    created_at,
    operation_type,
    payment_parts
) VALUES (
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000001',
    1000,
    0,
    'Seed deposit',
    'seed-script',
    'seed-balance-top-up',
    '2026-09-20T09:00:00+00:00',
    'top_up',
    '[{"method":"cash","amount_cents":1000,"reference":"seed-cash-1000"}]'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO balance_operations (
    id,
    client_id,
    amount_cents,
    bonus_amount,
    reason,
    actor_id,
    idempotency_key,
    created_at,
    operation_type,
    payment_parts
) VALUES (
    '00000000-0000-0000-0000-000000000012',
    '00000000-0000-0000-0000-000000000001',
    -300,
    0,
    'Seed tariff purchase from deposit',
    'seed-script',
    'seed-balance-debit',
    '2026-09-20T10:00:00+00:00',
    'debit',
    '[]'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO product_sales (
    id,
    product_id,
    product_name,
    product_category,
    client_id,
    guest_name,
    quantity,
    unit_price_cents,
    unit_cost_price_cents,
    total_price_cents,
    total_cost_price_cents,
    payment_method,
    cash_shift_id,
    status,
    sold_by,
    idempotency_key,
    created_at,
    completed_at,
    payment_parts,
    settlement_error
) VALUES (
    '00000000-0000-0000-0000-000000000021',
    '00000000-0000-0000-0000-000000000031',
    'Seed energy drink',
    'drinks',
    '00000000-0000-0000-0000-000000000001',
    NULL,
    1,
    400,
    150,
    400,
    150,
    'transfer',
    NULL,
    'completed',
    'seed-script',
    'seed-product-sale',
    '2026-09-20T11:00:00+00:00',
    '2026-09-20T11:00:00+00:00',
    '[{"method":"transfer","amount_cents":400,"reference":"seed-transfer-400"}]'::jsonb,
    NULL
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO guest_session_payments (
    id,
    workstation_id,
    tariff_id,
    tariff_quantity,
    guest_id,
    guest_name,
    total_price_cents,
    payment_parts,
    cash_shift_id,
    status,
    idempotency_key,
    created_at,
    created_by
) VALUES (
    '00000000-0000-0000-0000-000000000041',
    '00000000-0000-0000-0000-000000000051',
    '00000000-0000-0000-0000-000000000061',
    1,
    NULL,
    'Seed guest',
    500,
    '[{"method":"cash","amount_cents":500,"reference":"seed-guest-cash-500"}]'::jsonb,
    '00000000-0000-0000-0000-000000000071',
    'confirmed',
    'seed-guest-payment',
    '2026-09-20T12:00:00+00:00',
    'seed-script'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO client_entitlements (
    id,
    client_id,
    tariff_id,
    zone_id,
    duration_minutes,
    remaining_minutes,
    price_cents,
    queue_position,
    status,
    idempotency_key,
    purchased_at,
    activated_at,
    ended_at,
    burn_reason,
    time_restricted,
    sale_window_start_minute,
    sale_window_end_minute,
    usage_window_start_minute,
    usage_window_end_minute,
    window_timezone,
    audience,
    payment_parts,
    cash_shift_id,
    settlement_status,
    settlement_error,
    settlement_attempts,
    next_settlement_attempt_at
) VALUES (
    '00000000-0000-0000-0000-000000000081',
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000061',
    NULL,
    60,
    60,
    1200,
    1,
    'queued',
    'seed-entitlement',
    '2026-09-20T13:00:00+00:00',
    NULL,
    NULL,
    NULL,
    FALSE,
    NULL,
    NULL,
    NULL,
    NULL,
    NULL,
    'registered',
    '[{"method":"transfer","amount_cents":1200,"reference":"seed-entitlement-transfer-1200"}]'::jsonb,
    NULL,
    'settled',
    NULL,
    0,
    NULL
)
ON CONFLICT (id) DO NOTHING;

COMMIT;
