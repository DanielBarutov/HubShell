-- Run with psql -X -v ON_ERROR_STOP=1 -f backend/scripts/audit_bonus_balances.sql.
-- Pre-migration audit only. Exact bonus adjustments use the new bonus journal.
-- No identities or credentials are printed. Inspect anomalies before migration.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
WITH ledger AS (
    SELECT client_id, sum(bonus_amount::numeric) AS units
    FROM balance_operations
    GROUP BY client_id
), audit AS (
    SELECT c.id, c.balance_bonus, l.client_id, coalesce(l.units, 0) AS ledger_units
    FROM clients c FULL OUTER JOIN ledger l ON l.client_id = c.id
)
SELECT
    count(*) FILTER (WHERE id IS NOT NULL) AS clients,
    count(*) FILTER (WHERE balance_bonus <> 0) AS nonzero_bonus_clients,
    coalesce(sum(balance_bonus::numeric), 0) AS legacy_balance_units,
    coalesce(sum(ledger_units) FILTER (WHERE id IS NOT NULL), 0) AS legacy_ledger_units,
    count(*) FILTER (WHERE id IS NOT NULL AND balance_bonus <> ledger_units)
        AS clients_with_ledger_mismatch,
    count(*) FILTER (WHERE id IS NULL) AS orphan_ledger_clients,
    count(*) FILTER (WHERE balance_bonus < 0 OR ledger_units < 0) AS negative_bonus_records,
    count(*) FILTER (WHERE balance_bonus::numeric * 100 > 9223372036854775807)
        AS balances_exceeding_minor_unit_bigint
FROM audit;
COMMIT;
