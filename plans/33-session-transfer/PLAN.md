# План 33 — атомарный transfer игровой сессии

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `win-client/`
Зависимости: `01-workstations`, `04-auth-security`, `06-sessions`,
`12-live-metered-billing`, `30-entitlements-meter`,
`32-session-snapshot-entry`

## Цель

Позволить клиенту с активной сессией перейти на другой ПК после явного
подтверждения на новом устройстве. Перенос сохраняет session, meter и queue,
меняет workstation/zone по правилам контракта и безопасно перезапускает старый
ПК.

## Контрактная граница

Источник: [`backend/PRODUCT-CONTRACT.md`](../../backend/PRODUCT-CONTRACT.md) и
[`win-client/PRODUCT-CONTRACT.md`](../../win-client/PRODUCT-CONTRACT.md).

- Обычный второй вход не создаёт вторую сессию.
- Новый ПК показывает offer и требует explicit confirm.
- Перенос атомарен; старый ПК получает restart после server result.
- Между зонами перенос разрешён, для per-minute применяется ставка новой зоны.
- Активный несовместимый пакет сгорает после предупреждения; queued
  несовместимый пакет сохраняется.

## Входит в план

- `TransferOffer`, `TransferConfirm`, result и expiry;
- ownership/session lock при переносе;
- смена workstation/zone, meter baseline и package compatibility;
- duplicate-safe old-PC restart command;
- audit, actor/device scope и idempotency;
- WinUI new-device confirmation и error/retry states.

## Реализовано в текущем срезе

Добавлены offer/confirm DTO и application flow с token, expiry, idempotency и
проверкой target workstation. PostgreSQL repository получил owner-side
`commit_transfer` с блокировками offer/session/source/target в одной транзакции,
а также advisory lock для offer key и корректный conflict при двух разных
confirm keys; frontend и WinUI умеют создать offer и явно подтвердить перенос.
Добавлены audit operations, source-level duplicate-safe mapping и реальный
PostgreSQL concurrency test.

## Не входит

- перенос без онлайн-аутентификации;
- VNC, remote process migration и копирование пользовательских файлов;
- автоматический upgrade/reprice пакета;
- offline transfer.

## Порядок задач

1. [x] Описать state machine offer `pending/confirmed/expired/rejected` и
   одноразовый transfer token, привязанный к session/client/new device.
2. [x] Реализовать backend offer с проверкой active session, target workstation,
   reservation/entry decision и совместимости зоны.
3. [x] Реализовать atomic confirm: lock old/new workstation и session, смена
   ownership, meter baseline, queue и audit в одной транзакции.
4. [ ] Добавить warning/explicit confirmation для burn несовместимого active
   package; не менять queued packages.
5. [x] Опубликовать versioned HTTP/gRPC DTO и идемпотентные retry semantics.
6. [ ] После commit отправлять old-PC restart с correlation/idempotency key;
   transport failure не откатывает уже подтверждённый transfer молча.
7. [x] Подключить WinUI offer/confirm/result и operator read-only status.
8. [ ] Добавить fault/concurrency tests для двух подтверждений и двух target PCs.

## Критерии готовности

- одновременно существует только один owner активной session;
- повтор confirm возвращает тот же result и не создаёт вторую сессию;
- при отказе до commit исходный ПК продолжает сессию;
- queued packages не теряются;
- restart старого ПК не является условием записи transfer;
- клиент видит server result, а не локальное предположение об успехе.

## Остаток и release blocker

Нужно завершить атомарную политику burn несовместимого active package, old-PC
restart ACK и реальные PostgreSQL lock/concurrency tests. Memory fallback пока
сохраняет offer и session последовательно, а native transfer smoke не выполнен.

## Проверки и evidence

- unit/application state-machine tests;
- PostgreSQL lock/concurrency and rollback tests;
- HTTP/gRPC contract tests;
- device command duplicate/reconnect tests;
- Windows native manual transfer smoke.

## Открытые решения

- сколько живёт offer и как новый ПК находит его без утечки PII;
- нужен ли operator override для зависшего старого ПК;
- точная политика окончания active package при смене зоны.
