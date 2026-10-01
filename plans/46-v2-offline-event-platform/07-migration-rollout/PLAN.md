# V2.07 — атомарный cutover на V2

Статус: `planned`
Владельцы: `backend/`, `win-client/`, `frontend/`, `deploy/`
Зависимости: `V2.00`–`V2.06`

## Цель

Поставить V2 единым релизом и удалить V1 runtime из поставляемого продукта.
Это не per-PC rollout и не coexistence: после cutover нет V1 feature flag,
V1 gRPC business-session path или fallback. PostgreSQL с клиентами, балансами,
пакетами, тарифами, местами и историей остаётся и служит server-owned источником
для V2 snapshot и read-only истории.

## Задачи

1. [partial: `session_mode` и V1/V2-переключатель уже существуют только как
   временная веточная реализация] Удалить их вместе с V1 gRPC business-session
   path, worker-ами, UI и тестами после полного V2 end-to-end proof.
2. [ ] Поставить migrations, topics, consumers, dashboards и V2-only Windows
   client одной совместимой версией до cutover.
3. [x] В тестовом контуре до переключения сервер принудительно завершает все
   активные V1-сессии через `POST /api/v1/sessions/cutover/terminate-v1` с
   `X-Cutover-Confirmation: terminate-v1-sessions`. Flow завершает только
   source, отличный от `v2_local_ledger`; повтор безопасен. Сначала закрываются
   V1 entry path, затем вызывается endpoint. Автоматически переносить такую
   сессию в V2 запрещено. Этот временный endpoint удаляется вместе с V1 runtime.
4. [ ] На изолированном стенде проверить полный V2 flow: enrollment, V2 login,
   offline ledger, Kafka delivery/retry, deposit delivery, reconciliation,
   analytics и восстановление после restart.
5. [ ] Подготовить rollback только до начала cutover. После принятия V2
   финансового факта удалять его для rollback нельзя; client outbox и ledger
   сохраняются для reconciliation.
6. [ ] Подготовить operator runbook: окно cutover, active V1 sessions, offline
   PC, stale outbox, duplicate, rejected event, deposit not delivered, device
   revoke и manual review.
7. [ ] Обновить deployment, backup/restore и capacity plan Kafka/telemetry;
   после release gate удалить V1 runtime из образов и конфигурации.

## Критерии готовности

- поставка не содержит поддерживаемого V1 business-session path, feature flag
  или переключателя режима;
- полный V2 сценарий прошёл на реальной PostgreSQL, Kafka и Windows-ПК;
- до начала cutover сервер принудительно завершил активные V1-сессии, а после
  начала финансовые V2-факты не удаляются ради rollback.
