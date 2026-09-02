# План 32 — session snapshot и reservation entry decision

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `frontend/`, `win-client/`
Зависимости: `01-workstations`, `04-auth-security`, `05-reservations`,
`06-sessions`, `23-device-enrollment`,
[`29-contract-alignment`](../29-contract-alignment/PLAN.md)

## Цель

Сделать единый server-backed результат перед входом и после входа: backend
возвращает `EntryDecision` и `SessionSnapshot`, а HTTP, gRPC, heartbeat,
frontend и WinUI используют одни и те же DTO без локального вычисления
доступности, 30-минутного lock или остатка времени.

## Контрактная граница

Источник правил: product contracts всех трёх частей.

- Перед входом проверяются workstation state, reservation interval, named
  client match, guest semantics и 30-minute protection window.
- WinUI не принимает решение самостоятельно.
- При входе WinUI получает balance, active package и queue.
- Operator map сохраняет последний client, session state, queue summary и
  last-seen для offline/stale ПК, не раскрывая лишнюю PII.

## Текущее состояние

`CheckEntry` уже существует в backend и вызывается из session start. HTTP/gRPC
поверхности для entry и snapshot, server-owned snapshot builder и typed
consumers добавлены; heartbeat теперь передаёт active session и nested snapshot
в HTTP read model и gRPC response.

## Реализовано в текущем срезе

Добавлены versioned `SessionSnapshot`/entry DTO, HTTP endpoints и protobuf RPC,
snapshot с balance, active entitlement, queue, meter, login grant, server time и
allowed actions. Frontend запрашивает snapshot при открытой карточке ПК, а
WinUI обновляет snapshot через gateway/heartbeat callback. Workstation response
теперь различает `online/stale/offline`, а transport fixture сравнивает HTTP,
gRPC и heartbeat outputs; добавлены проверки entry refusal в frontend и
backend unit/API slice.

## Входит в план

- versioned DTO `EntryDecision`, `EntryReason` и `SessionSnapshot`;
- единый application use case для operator/device/portal входа;
- HTTP BFF, protobuf и heartbeat fields;
- last-known workstation read model с явным stale/offline timestamp;
- PII minimization и permission/device scope;
- compatibility tests для одинакового результата разных транспортов.

## Не входит

- реализация transfer/offline journal;
- расчёт тарифов в клиенте;
- realtime transport вместо polling без отдельного решения;
- VNC/remote control.

## Порядок задач

1. [x] Зафиксировать DTO fields, enum reasons, versioning и mapping ошибок;
   отдельно определить `allowed`, `reservation`, `workstation` и `stale`.
2. [x] Перенести все session-start entry points на один application port;
   исключить обход decision через legacy handler.
3. [x] Собрать `SessionSnapshot`: identity, zone, tariff/package, meter,
   login grant, balance, queue, server timestamp и allowed actions.
4. [x] Расширить heartbeat response и workstation read model; snapshot не должен
   становиться источником финансовой истины.
5. [x] Добавить HTTP endpoints/BFF и gRPC RPC с auth/device/actor scope.
6. [x] Добавить contract tests, которые сравнивают HTTP/gRPC/device outputs на
   одинаковом fixture и проверяют stale/offline semantics.
7. [x] Подготовить consumer fixtures для frontend и WinUI без UI-правил.

## Критерии готовности

- любой вход получает тот же `EntryDecision` независимо от транспорта;
- UI может показать machine-readable reason без повторного локального check;
- snapshot не содержит balance/PII вне разрешённого scope;
- stale/offline не маскируется под available;
- запись snapshot содержит server time и версию DTO.

## Остаток и release blocker

Остаётся native Windows compile/runtime и проверка device login entry на
целевой машине. Общая mapping-fixture и stale/offline semantics закрыты на
backend source/unit уровне; PostgreSQL permission/concurrency и headed
frontend/Windows smoke относятся к плану 37.

## Проверки и evidence

- backend unit/API/gRPC contract tests;
- reservation boundary tests на `now`, `now+30m`, named/guest и disabled PC;
- permission/device-scope tests;
- PostgreSQL read-model/concurrency tests;
- headed frontend и Windows checks после подключения consumers.

## Открытые решения

- имя и версия конкретных RPC;
- минимальный набор PII для operator map;
- TTL last-known snapshot и политика отображения stale.
