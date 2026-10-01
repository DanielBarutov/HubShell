# V2.08 — проверка и доказательства

Статус: `planned`
Владельцы: `backend/`, `win-client/`, `frontend/`, `deploy/`
Зависимости: `V2.00`–`V2.07`

## Цель

Проверить V2 наблюдаемым поведением, а не только unit-тестами схем и DTO.

## Матрица обязательных сценариев

1. [ ] V2 login → server absent → 5-minute grant → package → auto-next →
   per-minute → exhaustion.
2. [ ] Local purchase одного и нескольких packages, double click, crash до/после
   local commit, crash до/после Kafka publish.
3. [ ] Early exit: burn active, preserve queue, no duplicate stop/restart.
4. [ ] Duplicate/out-of-order/replayed Kafka messages, payload hash mismatch,
   sequence gap, device mismatch и `NEEDS_REVIEW` UX.
5. [ ] Deposit before/during/after offline, retry payment, delayed delivery,
   pending local debit и server reconciliation.
6. [ ] Kafka/PostgreSQL/collector outage, consumer lag, dead-letter, recovery
   and replay without duplicate financial fact.
7. [ ] Analytics ledger reconciliation, Grafana metric→trace→log→audit
   drill-down and PII redaction.
8. [ ] V2-only cutover evidence: в release-образе отсутствуют V1
   business-session endpoint, worker, feature flag и UI-переключатель; legacy
   PostgreSQL-данные доступны только через явно описанные server-owned
   read/snapshot границы.

## Уровни доказательств

- Domain/Application: unit/property tests state machines и idempotency.
- PostgreSQL: настоящие transaction/lock/concurrency проверки с тестовым DSN.
- Kafka: Compose integration с реальным broker и restart consumers.
- API/contract: schema compatibility и consumer-driven fixtures.
- Frontend: browser smoke операторского deposit/sync/review UI.
- Windows: native x64 power loss, disk full, DPAPI/ACL, network loss, restart,
  widget/access-gate и Kafka reconnect.
- Operations: backup/restore, alert delivery и cutover runbook exercise.

## Definition of done

V2 не может быть помечен `done`, пока нет реальной PostgreSQL + Kafka проверки,
ручного browser scenario, native Windows evidence и выполненного cutover
runbook; Linux build, mock broker или source inspection сами по себе этого не
подтверждают.
