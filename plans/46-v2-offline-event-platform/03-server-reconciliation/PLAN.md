# V2.03 — server inbox, reconciliation и снимки

Статус: `in_progress`
Владелец: `backend/`
Зависимости: `V2.00`, `V2.01`

## Цель

Принять факты локальной сессии безопасно, идемпотентно и объяснимо, не
возвращаясь к server minute confirmation.

## Задачи

1. [partial: additive migration `20260927_0063`, ServerInbox, ServerOutbox и
   atomic sequence/hash-chain checkpoint созданы; sync cursor, processing result
   и device/client V2 lease остаются] Добавить PostgreSQL schema для ServerInbox,
   ServerOutbox, sync cursor, reconciliation result и device/client V2 lease;
   миграции только additive.
2. [partial: отдельный V2 gRPC login, device auth, server-owned reader,
   signed snapshot, новая Session и exclusive lease/outbox создаются одной
   транзакцией; production key deployment и revoke остаются]
   Реализовать `LoginRequested →
   OfflineSessionSnapshotIssued`: device auth, exclusive V2 lease,
   balance/grants/packages/catalog snapshots, signature и snapshot version.
3. [partial: Protobuf/parser, persistent checkpoint и чистая sequence/hash-chain
   проверка реализованы и покрыты тестами; PostgreSQL application boundary
   атомарно принимает только allowed client facts. Отдельный FastStream worker
   передаёт факт в эту boundary, а invalid/conflict переносит в DLQ до offset
   commit. Нужны live Kafka proof, durable reject audit и financial projections]
   Реализовать server consumer: schema/auth/device
   validation, inbox dedupe, sequence/hash-chain checks и controlled reject.
4. [partial: inbox, immutable confirmed source fact, chain checkpoint, audit и
   ServerOutbox result уже пишутся одной PostgreSQL-транзакцией; финансовые
   projection и правила конкретных fact types ещё не реализованы] В одной транзакции писать inbox, immutable domain/financial fact,
   projection, audit и ServerOutbox result. Никаких publish-before-commit.
5. [ ] Принять allowed client facts без пересчёта прошлой минуты; проверить
   causal validity, пределы snapshot и источник времени, а не заменить факт
   новым server tick.
6. [ ] Возвращать `ReconciliationSnapshot`/per-operation result: accepted,
   duplicate, rejected, `NEEDS_REVIEW`; конфликт не перезаписывает ledger.
7. [ ] Реализовать server commands как versioned server events: block/lock/
   config/revoke. Команда не меняет локальный ledger молча.

## Проверки

- настоящая PostgreSQL: два consumer, duplicate, gap, race stop/debit/purchase;
- invalid snapshot/device/signature, stale/revoked lease, second device;
- recovery после DB commit до Kafka publish и после publish до offset commit.

## CP-018 — 2026-09-27: атомарное подтверждение клиентского факта

Выполнено:

- выявлена и исправлена ошибка исходной inbox-схемы: глобальный PK `event_id`
  запрещал один и тот же Kafka fact нескольким логическим consumer groups.
  Migration `0065` делает ключ `(consumer_name, event_id)`, сохраняя unique
  operation и sequence внутри каждого consumer;
- добавлен PostgreSQL reconciliation boundary. В одном commit он берёт
  advisory locks operation/session, проверяет allowed client event type,
  duplicate/conflict и sequence/hash-chain, после чего сохраняет inbox,
  immutable `v2_confirmed_client_facts`, checkpoint, audit и единственный
  `ReconciliationCompleted` в server outbox;
- этот путь не пересчитывает прошедшую минуту и не меняет финансовый баланс:
  он фиксирует фактическое утверждение до реализации отдельных projection
  поминутки/пакетов;
- migration `0065` применена к живой локальной Compose PostgreSQL. Настоящий
  PostgreSQL integration test подтвердил первый accepted, duplicate, следующий
  sequence и fan-out того же event в `analytics_projection`: 3 inbox rows,
  2 confirmed facts, 2 audit и 2 outbox result без второго side effect.

Осталось:

- FastStream worker подготовлен, а device/snapshot/lease validation выполняет
  существующая PostgreSQL boundary. Нужны live Kafka proof, durable reject
  audit и policy позднего факта;
- нет financial/package/session projections по каждому allowed event type,
  проверки границ snapshot или authoritative reconciliation snapshot;
- нет retry/recovery test после Kafka publish/offset commit и нет серверных
  block/lock/config/revoke команд.

## CP-030 — 2026-09-28: отдельный FastStream worker для клиентских V2-фактов

Выполнено:

- в Compose profile `v2` добавлен самостоятельный `v2-client-facts` процесс,
  отдельный от server outbox. Он передаёт raw Protobuf в уже атомарную
  PostgreSQL reconciliation boundary: lease, snapshot, inbox, hash-chain,
  confirmed fact, audit и result outbox остаются единым commit;
- accepted/duplicate подтверждают Kafka offset только после этого commit;
  невалидный envelope и reconciliation conflict/gap сначала копируются в
  закрытый `v2.failed-events`, поэтому offset не теряется и нет второго
  финансового действия. В логах фиксируется лишь технический status/reason,
  без payload;
- worker собран и запущен в Compose, подключён к Prometheus/Grafana/Loki/Tempo.
  Настоящий Protobuf-факт прошёл Kafka → worker → PostgreSQL; consumer group
  `client_session_facts` имеет нулевой lag. Focused Python + PostgreSQL/Kafka
  проверки прошли: 29 тестов; Compose config и Ruff также прошли.

Осталось:

- проверена только accepted-ветка живой Kafka delivery. Остаются DLQ,
  restart между DB commit и Kafka offset, TLS/SASL/ACL и durable audit отказа.
  Конфигурация и unit/DSN проверки не заменяют эти доказательства.

## CP-019 — 2026-09-27: server-owned V2 lease в проверке фактов

Выполнено:

- migration `0066` добавляет неизменяемую серверную запись
  `v2_session_leases`: session, client, device, snapshot id/version, policy,
  срок и статус;
- reconciliation теперь до inbox проверяет активный, неистёкший lease с теми
  же client/device/session и берёт строку lease на lock в той же транзакции;
- PostgreSQL integration test создаёт активный lease и подтверждает, что
  обычная цепочка accepted/duplicate/fan-out не сломана этим guard.

Осталось:

- нет use case, который выдаёт lease только после device auth и реально
  подписанного `OfflineSessionSnapshot`; тест вставляет lease напрямую как
  подготовку infrastructure scenario;
- отсутствуют revoke/expiry workflow, unique active lease policy, проверка
  snapshot id в клиентском факте и публичный V2 login endpoint.

## CP-021 — 2026-09-27: автономный lease issuer и snapshot factory

Выполнено:

- migration `0067` делает expiry V2 lease optional: offline-сессия не
  отвергается лишь потому, что сервер долго отсутствовал. Отзыв должен быть
  явным server event/завершением сессии;
- добавлен lease issuer с PostgreSQL advisory locks. Один client или device
  не получает второй active V2 lease; точный повтор того же snapshot id
  возвращает существующий lease как duplicate;
- добавлен pure snapshot factory, который собирает новый V2 Protobuf payload
  из существующих server-owned Client, active Session, Entitlement и Tariff
  snapshots. Подпись по-прежнему остаётся за отдельным signer port;
- PostgreSQL integration и deterministic snapshot unit tests прошли.

Осталось:

- production signer и C# verifier, V2 login use case/endpoint, device auth,
  atomic связка «подписать snapshot → выдать lease → server outbox» и revoke
  workflow ещё не реализованы.

## CP-022 — 2026-09-27: реальная подпись snapshot и общая трактовка лимита долга

Выполнено:

- backend подписывает deterministic protobuf payload алгоритмом Ed25519. Raw
  32-byte private seed читается только из server settings
  `GAMECLUB_V2_SNAPSHOT_SIGNING_PRIVATE_KEY_B64`, а `key_id` — из
  `GAMECLUB_V2_SNAPSHOT_SIGNING_KEY_ID`; JWT-secret не переиспользуется;
- Windows transport получил verifier с набором публичных ключей по `key_id`.
  На ПК нет приватного ключа, поэтому одновременно могут приниматься старый и
  новый public key во время ротации;
- Python и C# подтвердили один и тот же Ed25519 test vector, а C# дополнительно
  проверил подпись полного deterministic protobuf snapshot, созданную Python;
- `debt_limit_cents` зафиксирован как неотрицательный предел разрешённого
  долга. Ранее snapshot factory позволял отрицательное значение, несовместимое
  с проверкой локального ledger; это исправлено и покрыто тестом.

Осталось:

- ключ пока не подключён к production secret storage и Windows deployment
  config: перед реальным V2 login нужно выдать public-key set клиенту безопасным
  способом, задать процесс ротации и не включать V2 при пустом server secret;
- V2 login, device auth, одна PostgreSQL-транзакция для lease/outbox и revoke
  workflow по-прежнему не реализованы.

## CP-023 — 2026-09-27: atomic signed snapshot → lease → outbox

Выполнено:

- migration `0068` сохраняет exact deterministic payload, подпись, `key_id` и
  SHA-256 payload hash рядом с server-owned V2 lease. Это позволяет повторному
  запросу вернуть исходный signed snapshot, а не создать второй;
- PostgreSQL repository под advisory locks одной транзакцией создаёт exclusive
  lease, `LoginSnapshotIssued` в server outbox и audit. Повтор с теми же байтами
  возвращает duplicate без нового side effect;
- reconciliation теперь извлекает `snapshot_id`/`snapshot_version` из каждого
  client fact и до inbox проверяет точное совпадение с active lease. Старый или
  чужой snapshot получает явный conflict и не меняет chain, audit или outbox;
- настоящая PostgreSQL-проверка прошла для обычной цепочки, неправильного
  snapshot и атомарной выдачи signed snapshot.

Осталось:

- нет доставки/применения V2 snapshot в access-gate, public-key deployment и
  revoke server event.

## CP-024 — 2026-09-27: отдельный V2-вход и режим ПК

Выполнено:

- migration `0069` добавляет каждому ПК явный режим `v1_server_owned` или
  `v2_local_ledger`; существующие ПК остаются V1. Оператор может переключить
  режим через обычное обновление ПК, а V2 вход на V1-ПК отклоняется;
- добавлен отдельный `OfflineSessionService.Login`. Он требует совпадающую
  device identity и пароль клиента, создаёт новую сессию с источником
  `v2_local_ledger`, собирает client/balance/package/tariff snapshot через
  публичные application services и сохраняет signed snapshot, lease, audit и
  outbox существующей атомарной PostgreSQL boundary;
- при потере gRPC-ответа повтор с тем же ключом сессии возвращает уже
  сохранённый signed snapshot без второго outbox/audit side effect. Это
  проверено на настоящей PostgreSQL; unit и gRPC-тесты также проверяют отказ
  V1-режима и привязку device identity;
- C# transport подключает новый общий Protobuf-контракт, но access-gate пока
  его не вызывает.

Осталось:

- private key всё ещё берётся только из server environment. Нужны production
  secret storage, выдача набора public keys Windows-клиенту, ротация и revoke;
- нужно вручную проверить сценарий на тестовой базе с настоящей PostgreSQL,
  запущенным gRPC-сервером и собранным контейнером: локальные тесты не
  доказывают, что новый исходный код уже находится в пользовательском образе.

## CP-025 — 2026-09-27: единая транзакция V2 login

Выполнено:

- Sessions module открыл узкий transaction writer: V2 не читает и не изменяет
  его таблицу напрямую, но может сохранить уже проверенную новую Session в
  транзакции, которой владеет V2 login boundary;
- PostgreSQL boundary теперь одной транзакцией сохраняет новую Session, exact
  signed snapshot, exclusive lease, audit и `LoginSnapshotIssued` outbox. При
  повторе idempotency key возвращает ранее выданный snapshot;
- настоящая PostgreSQL-проверка принудительно создаёт конфликт lease после
  подготовки Session и подтверждает rollback: строка новой Session не остаётся
  в `gaming_sessions`.

Осталось:

- нужен собранный контейнер с этим кодом и ручной V2 gRPC-сценарий на тестовой
  базе; текущая проверка PostgreSQL вызывает application boundary напрямую и
  не доказывает пользовательский контейнерный маршрут.
