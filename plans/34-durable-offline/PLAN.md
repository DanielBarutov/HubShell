# План 34 — durable offline journal и batch replay

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `win-client/`
Зависимости: `04-auth-security`, `06-sessions`, `12-live-metered-billing`,
`23-device-enrollment`, `27-portable-deployment`,
`32-session-snapshot-entry`

## Цель

Переживать временный offline во время уже начатой сессии без ложного успеха и
без повторного списания. WinUI хранит постоянный журнал допустимых операций,
после reconnect отправляет batch, backend идемпотентно фиксирует факты и
возвращает reconciliation result.

## Контрактная граница

Источник: backend и WinUI product contracts.

- До входа offline новая сессия запрещена.
- Во время active session используется последний server snapshot.
- Локальный journal persistent, sequence monotonic, операции имеют idempotency.
- Известный пакет/баланс расходуется до безопасного локального лимита; при
  исчерпании клиент завершает сессию и блокирует ПК.
- Operator map показывает last client, time и offline status.

## Входит в план

- schema `OfflineOperation` и `OfflineBatch` с protocol version;
- Windows durable storage boundary и encryption/ACL policy;
- monotonic sequence, idempotency, checksum и recovery после crash;
- backend batch validation/replay/conflict/reconciliation result;
- allowed operations: meter delta, stop, lock/status; никаких новых offline
  session start, payment или package purchase;
- duplicate-safe retry и cleanup только после подтверждённого server ACK.

## Реализовано в текущем срезе

Добавлен backend offline module с allowlist операций, protocol version, batch
validation, sequence/idempotency/checksum, per-operation result и memory/Postgres
repositories. WinUI получил DPAPI-protected JSONL journal, durable sidecar для
sequence, recovery/ACK cleanup, gateway replay и coordinator snapshot/replay
связку. Backend unit tests покрывают duplicate, checksum conflict, stop, gap,
server-clock при skewed device time и неизвестную session; PostgreSQL DSN test
подтверждает параллельную повторную доставку без второго debit.

## Не входит

- offline login и новая session;
- offline cash/balance payment, purchase или transfer;
- Redis-only queue/journal;
- ручная коррекция конфликтов без supervisor flow.

## Порядок задач

1. [x] Зафиксировать operation allowlist, sequence scope, batch size, retention
   и conflict states; запретить неописанные offline commands.
2. [x] Выбрать Windows storage (Credential Manager/DPAPI-protected file или
   другой approved boundary), threat model и отсутствие PII в логах.
3. [x] Добавить backend replay port, idempotency table/result и reconciliation
   record; повторный sequence не применяет side effect второй раз.
4. [x] Встроить meter/stop replay с server snapshot version и проверкой, что
   сессия была online-authorized до потери сети.
5. [x] Реализовать reconnect batch, partial result, retry/backoff и manual
   review; journal очищать только по подтверждённым sequence.
6. [x] Подключить operator stale read model и WinUI offline/reconnecting UI.
7. [x] Добавить contract-level crash/restart boundary и tests для clock-skew,
   duplicate и out-of-order; journal использует WriteThrough/atomic sidecar,
   backend отклоняет неизвестную session, а native power-loss/disk-full smoke
   остаётся отдельной Windows-проверкой.

## Критерии готовности

- power loss не удаляет неподтверждённые операции;
- batch повторяется безопасно и даёт per-operation result;
- offline-before-login не открывает рабочий сценарий;
- server projection после replay объяснимо совпадает с журналом или получает
  `needs_review`;
- никакие offline facts не хранятся только в RAM/Redis.

## Остаток и release blocker

Не доказаны native power-loss/disk-full/restart сценарии и production security
inspection. Reconnect partial-result/cleanup и backoff закрыты source-level,
operator map различает stale/offline; server-authorized offline local limit и
native recovery остаются release blockers.

## Проверки и evidence

- backend unit/API/concurrency tests;
- PostgreSQL replay/idempotency tests;
- Windows native disk/restart/reconnect smoke;
- security inspection storage/ACL/logs;
- operator headed smoke stale/offline status.

## Открытые решения

- точный local limit для offline meter и политика clock drift;
- допустимый размер/срок хранения journal;
- нужен ли отдельный operator reconciliation screen в MVP.
