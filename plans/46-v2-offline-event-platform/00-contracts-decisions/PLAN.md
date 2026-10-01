# V2.00 — контракты, решения и модель доверия

Статус: `planned`
Владельцы: `backend/`, `win-client/`, `frontend/`
Зависимости: —

## Цель

Заменить противоречащие V2 формулировки «backend всегда считает минуты» на
явную двухрежимную модель, не оставив старые и новые правила одновременно
источниками истины.

## Задачи

1. [x] Обновить `CODEX.md`: Kafka для V2 Windows-session transport, локальный
   ledger как временный владелец решения после подписанного snapshot,
   observability и запрет прямого финансового решения по логам.
2. [x] Обновить `backend/PRODUCT-CONTRACT.md`: V2 event acceptance,
   reconciliation, deposit delta, подтверждённые DomainEvent и целевой
   атомарный cutover без V1 feature mode. Исторические V1-ответы не получают
   новый смысл задним числом и не становятся частью V2 runtime.
3. [x] Обновить `win-client/PRODUCT-CONTRACT.md`: локальная state machine,
   durable inbox/outbox, allowed operation list, clock rollback, reconnect и
   `NEEDS_REVIEW` UX.
4. [x] Обновить `frontend/PRODUCT-CONTRACT.md`: операторское пополнение,
   V2-sync status, reconciliation screen и read-only Grafana links без PII.
5. [ ] Создать ADR: прямое подключение device к Kafka или device gateway,
   аутентификация SASL/mTLS, topic ACL, key rotation и device revoke.
6. [x] Утвердить single-device lease: один `client_id` может иметь только одну
   V2 autonomous session; параллельное устройство получает отказ.
7. [ ] Утвердить policy времени: trusted server anchor, monotonic clock во
   время запуска, persistent last-seen wall time и реакция на rollback/large
   forward jump.

## Критерии готовности

- три product contracts описывают один и тот же порядок grant/package/per-minute;
- в них нет одновременного требования server tick и client tick для V2;
- принятые ADR содержат угрозы, владельца, rollback и последствия отказа.
