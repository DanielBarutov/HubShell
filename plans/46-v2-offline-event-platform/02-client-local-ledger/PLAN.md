# V2.02 — локальный ledger, автономная сессия и Windows lifecycle

2026-10-11: исправлен вход в аккаунт после завершённого гостевого V2 ledger:
повторный stop использует guest endpoint с payment ID, не account endpoint с пустым client ID.
Сохранён отказ при PermissionDenied; журнал не очищается. Иконки access-gate выровнены
в фиксированных Canvas/Viewbox. Проверено: 133 .NET unit/headless теста и Skia-рендер;
живой повторный вход и Windows smoke не выполнены.


Статус: `in_progress`
Владелец: `win-client/`
Зависимости: `V2.00`, `V2.01`

## Цель

Сделать Windows-клиент самостоятельным владельцем V2 session decisions после
валидного snapshot, с восстановлением после crash/power loss.

## Задачи

1. [partial: защищённый Windows file store содержит state, ClientInbox и
   ClientOutbox одним снимком; checkpoint и проверка ACL/DPAPI на Windows остаются]
   Выбрать и реализовать локальное постоянное хранилище для state, ledger,
   inbox, outbox и checkpoint; ключ/ACL/шифрование защитить Windows boundary.
2. [partial: coordinator последовательно записывает state mutation + immutable
   fact + ClientOutbox одной операцией временный файл → flush → atomic replace;
   crash/reboot/disk-full проверка на Windows остаётся] Реализовать atomic local
   transaction: state mutation + immutable ledger fact + ClientOutbox. Crash не
   оставляет применённое списание без события или событие без списания.
3. [partial: общий signed snapshot Protobuf-контракт, deterministic payload,
   C# signature-verifier port и создание ledger после успешной проверки
   реализованы; server signer, ключи, device/TTL/policy проверка и хранение
   snapshot остаются] Валидировать `OfflineSessionSnapshot`: подпись, device,
   version, режим, TTL нового входа и policy правила; хранить tariff snapshots,
   а не mutable catalog reference.
4. [partial: чистая C# state machine реализована и покрыта unit-тестами;
   подключение к persistent storage/access-gate остаётся] Реализовать source
   state machine: login grant → active package → compatible queued package →
   per-minute → exhausted/access-gate.
5. [partial: чистая C# модель проверяет тариф snapshot, зону, баланс и лимит
   долга, создаёт queued package и факт; atomic disk commit остаётся]
   Реализовать `PACKAGE_PURCHASE` из локального balance: один click — один
   operation id, атомарный debit и новый queued/active TimeGrant.
6. [partial: чистая C# модель реализует per-minute debit, debt limit,
   `EXHAUSTED` и локальное требование блокировки; timer и durable commit
   остаются] Реализовать per-minute debit на границе минуты, с local debt
   limit и тарифным snapshot; `EXHAUSTED` немедленно фиксирует stop и закрывает
   доступ.
7. [partial: чистая C# модель фиксирует early exit и отдельный факт burn для
   grant/package, сохраняя queue; persistent commit остаётся] Реализовать early
   exit: burn active grant/package, сохранить queue, записать `SESSION_STOP`;
   не выполнять фиктивный refund.
8. [partial: порядок outbox и подтверждение удаления после ответа транспорта,
   transport-neutral worker с retry/backoff и адресный processor server event
   уже реализованы; реальный Kafka transport, host wiring, lifecycle и
   watermarks остаются] Запустить outbox worker и Kafka consumer на всём
   lifecycle приложения: retry/backoff, online state, heartbeat watermarks,
   ClientInbox до offset commit.
9. [ ] Реализовать UI: pending sync, offline, delivery error, needs review,
   без показа секретов и технических ID пользователю.

## Проверки

- unit/property tests всех переходов времени;
- crash между local commit/publish и consume/offset commit;
- Windows native disk-full, reboot, clock rollback, no network и reconnect;
- ручный access-gate/widget smoke на целевом Windows ПК.

## CP-029 — 2026-09-28: безопасное применение адресного server event

Выполнено:

- `V2ServerEventProcessor` получает Protobuf `EventEnvelope` и принимает
  только `BalanceCreditApplied` от server producer для текущих
  client/session/device; несовпадение возвращает controlled `Rejected` без
  изменения локального ledger;
- payload проверяется по каноническому SHA-256, `deposit_operation_id`
  сравнивается с envelope operation, а credit сохраняется через прежнюю
  локальную ClientInbox-транзакцию. Повтор возвращает `Duplicate`, не создавая
  второе зачисление;
- Linux-проверка `dotnet test ./win-client/tests/GameClub.Client.Tests.csproj
  --no-restore` прошла: 69 тестов, включая отклонение изменённого payload при
  совпадающей цели.

Осталось:

- processor пока не вызван живым Kafka consumer и его `EventProcessingResult`
  ещё не передаётся серверу. Поэтому UI всё ещё не может доказать оператору
  фактическое получение пополнения Windows-клиентом;
- нужны retry/backoff, controlled reject/DLQ, commit Kafka offset после disk
  commit и native Windows проверки storage/reconnect.

## CP-038 — 2026-09-28: V2-only client login boundary

Выполнено:

- `OfflineSessionService` получил V2 `Login` и `Register`: оба требуют device
  identity и возвращают signed V2 snapshot; регистрация создаёт профиль в
  сохраняемой PostgreSQL, но не создаёт V1 portal-сессию;
- новые V2-методы C# `GrpcBackendClient` вызывают только V2 RPC с device bearer
  token и проверяют snapshot до передачи ledger application-слою;
- `V2OfflineLoginCoordinator` не открывает доступ, пока проверенный ledger не
  записан с пустыми inbox/outbox. Тесты проверяют отказ snapshot другого ПК.

Остаётся:

- production keyring/rotation и wiring этого coordinator в Windows access-gate;
- durable resume существующего V2 ledger, minute timer, outbox lifecycle и
  native Windows proof. Поэтому V1 runtime пока не удаляется из ветки и V2
  release не объявляется готовым.

## CP-039 — 2026-09-28: durable minute boundary и следующий V2 вход

Выполнено:

- signed snapshot сохраняет UTC activation anchor, а ledger после каждого
  локального списания сохраняет `LastConsumedMinuteUtc` вместе с outbox fact;
- `V2MinuteLedgerRunner` догоняет только ещё не применённые minute boundaries.
  Restart и rollback wall clock не создают второй debit;
- новый signed snapshot заменяет только завершённый ledger того же ПК и только
  после доставки всех старых client facts. Активный ledger и pending outbox
  никогда не перезаписываются.

Остаётся:

- подключить runner и recovery к Windows access-gate, затем проверить timer,
  restart и power loss на реальном Windows ПК;
- delivery/retry outbox и controlled handling server reject до следующего
  V2-входа.

## CP-040 — 2026-09-28: Windows V2 access-gate composition

Выполнено:

- production Windows host создаёт `V2OfflineLoginCoordinator`, protected
  ledger, minute runner и Ed25519 verifier из deployment public keyring;
- user Login/Register в `MainViewModel` выбирают V2 RPC, открывают доступ лишь
  после durable ledger commit, а Stop создаёт local `SESSION_STOP` вместо V1
  server stop;
- Windows host не запускает старый V1 command-loop, поскольку тот мог создать
  server-owned сессию. Unit test подтверждает V2 Login → Stop без V1 session
  gateway; Linux static build не заменяет native Windows smoke.

Остаётся:

- V2 device heartbeat/command transport уже подключён, а Kafka outbox worker и
  recovery orchestration пока остаются отдельной host/transport boundary; до
  неё V2 host не готов к release proof;
- перед Windows deployment задать `GAMECLUB_V2_SNAPSHOT_PUBLIC_KEYS` или
  MSBuild metadata `GameClubV2SnapshotPublicKeys` c public keys клуба.

## CP-044 — 2026-09-29: durable outbox worker и recovery snapshot

Выполнено:

- `V2ClientOutboxPublisher.TryPublishPendingAsync` возвращает число
  подтверждённых и оставшихся фактов вместе с ошибкой транспорта; при ошибке
  текущий факт и вся последующая цепочка остаются в durable outbox;
- `V2ClientOutboxWorker` повторяет доставку строго с первого pending-факта,
  применяет экспоненциальную задержку и сбрасывает её после успешной попытки;
  отмена процесса не превращается в скрытую потерю факта;
- `V2LocalLedgerRecoveryCoordinator` читает ledger, ClientInbox и ClientOutbox
  одним storage snapshot, восстанавливает только ledger назначенного device и
  различает active, completed и completed-pending-delivery состояния;
- добавлены поведенческие тесты failure retention, retry 1→2→poll и recovery
  для чужого device; Linux-проверка C# прошла: 88 тестов, Windows V2 host
  build прошёл без warning/error.

Остаётся:

- native Windows device publisher smoke и live доставка `EventProcessingResult`
  обратно в ClientInbox ещё не доказаны; HTTP ingress/publisher, адресный
  server polling/ack boundary, processor и retry worker покрыты кодом и
  Linux-тестами;
- heartbeat watermarks и native Windows crash/power-loss/reconnect
  доказательства.

## CP-045 — 2026-09-29: server events обратно в V2 ClientInbox

Выполнено:

- `V2HttpServerEventConsumer` получает device-scoped envelopes, сверяет
  `event_id`/`operation_id` с protobuf, вызывает `V2ServerEventProcessor` и
  подтверждает только `Accepted`/`Duplicate`;
- `V2ServerEventWorker` запускается Windows host рядом с client outbox worker,
  применяет bounded exponential retry и не удаляет отклонённые события;
- rejected server events сохраняются в защищённом local snapshot с причиной,
  временем и числом повторов; `MainViewModel` восстанавливает `needs review`
  после restart и показывает delivery status в Avalonia UI;
- отдельный V2 transport test project проверяет commit balance + ClientInbox
  до ack и отсутствие ack для другой сессии; 2 теста зелёные.

Остаётся:

- native Windows доказательство с настоящим HTTP backend, DPAPI, crash/power
  loss и reconnect;
- UI pending-sync detail, heartbeat watermarks и production monitoring
  delivery lag.

## CP-046 — 2026-09-29: durable delivery status и needs-review UI

Выполнено:

- local snapshot хранит `V2ServerEventIssue` с адресом события, причиной,
  временем первого/последнего отказа и числом попыток; старый snapshot без
  этого поля продолжает читаться как пустой список;
- `MainViewModel` различает transport failure и business reject, восстанавливает
  `needs review` после restart и показывает оба статуса в Avalonia access-gate.
- Причина ошибки восстановления local V2-сессии теперь записывается в лог;
  при ошибке access-gate остаётся заблокированным, а durable ledger сохраняется.
- Восстановление/обновление гостевого ledger не обращается к кабинету аккаунта;
  вход и регистрация проверяют активный local ledger до серверного запроса.

Остаётся:

- heartbeat watermarks и серверный delivery-lag мониторинг;
- native Windows DPAPI, crash/power-loss и reconnect proof.

### 2026-10-11 — V2 grant → per-minute и ошибка локального ledger

Исправлен состав нового signed snapshot: пакетные тарифы имеют
`per_minute_price_cents=0`; единственную поминутную ставку выбирает существующий
`CatalogService.find_per_minute_tariff`. Клиент после ошибки minute commit
сохраняет ссылку на ledger, приостанавливает новые списания, журналирует исходное
исключение и разрешает явное завершение даже при закрытом access-gate.
Защита от замены активного ledger и pending outbox сохранена.

Linux воспроизводит ошибку старого snapshot с двумя положительными ставками:
grant списывается, следующий debit бросает исключение, ledger остаётся Active.
Это подтверждает дефект данных, но не устанавливает причину конкретного
Windows-инцидента без исходного snapshot/исключения. Старый сохранённый snapshot
не переписывается: завершить прежнюю сессию и получить новый signed snapshot.

2026-10-11: `v2.minute` логирует успешные minute commits и ошибку
`ConsumeV2DueMinutesAsync` с этапом, session/snapshot ID, состоянием до/после,
grant, балансом, UTC boundaries, числом совместимых ставок и stack trace.
Нет записей для пустых секундных ticks, токенов, паролей и полного snapshot.

### 2026-10-12 — отрицательный баланс и пакетные V2-проекции

- Поминутная reconciliation использует сохранённый signed debt limit; debit
  и подтверждение остаются одной транзакцией. Повтор не списывает деньги вновь.
- Package consume/burn обновляет entitlement через публичный transaction writer
  владельца пакетов. Проверяются клиент, тариф, settlement, текущий остаток и
  единственный active пакет; неоднозначный legacy UUID возвращает conflict.
- Поле баланса активной клиентской сессии читает локальный ledger и обновляется
  после minute commit, не дожидаясь portal snapshot.
- Онлайн-покупка выдаёт подписанный пакет с реальным entitlement ID и ключом
  покупки, поэтому тариф, созданный после входа, можно применить без замены
  ledger. Protobuf расширен: `OfflinePortalSnapshot.purchased_package = 15`,
  `OfflineSessionSnapshotPayload.purchase_idempotency_key = 32`.
- Linux: 49 backend checks с настоящей временной PostgreSQL, 72 C# checks;
  один live Kafka test пропущен. Windows host Release build на Linux: 0 ошибок,
  0 предупреждений. Ruff, format и diff checks проходят.
- Rollout: сначала backend-gRPC и v2-client-facts, затем клиент. Production
  data, старые confirmed facts/DLQ и активные ledger не переписывались. Их
  расхождения требуют отдельной сверки исходных событий; эти тесты не
  подтверждают восстановление прежней продовой цепочки или Windows runtime.

2026-10-12: исправлено прерывание гостевой сессии оператором: существующий guest poll применяет подтверждённый server stop, сохраняет ledger и блокирует клиент. Проверяются чужое устройство, повторное завершение, сбой локальной записи и ошибки связи. Проверка на Linux; live Kafka/Windows smoke не выполнены.

### 2026-10-19 — ночная активация и окно расходования

Причина: ActivateEntitlement обновлял portal snapshot, но не локальный ledger;
следующая минута оставалась `per_minute_debit`. Постоянный тест воспроизвёл
ошибку до исправления и проверяет реальный ViewModel → coordinator → engine.

Реализовано: signed `active_package` при активации/refresh, применение в текущий
ledger без повторной оплаты, дедупликация без увеличения остатка, восстановление
после потерянного ответа. Package snapshot несёт usage window/timezone/срок;
закрытая очередь пропускается, закрытие активного окна сохраняет burn/stop.
Signed receipt покупки также переносит срок и включает расход пакета.

Проверки Linux и оставшиеся ограничения записаны в plans/VERIFICATION.md.
Rollout: backend-gRPC перед клиентом; активные журналы и старые финансовые
факты не переписывать. Native Windows/live Kafka и реальная проблемная сессия
требуют отдельной проверки; старые лишние списания автоматически не возвращаются.
