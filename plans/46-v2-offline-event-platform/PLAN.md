# План 46 — V2: автономная сессия, события и наблюдаемость

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `win-client/`, `frontend/`, `deploy/`
Ветка: `V2`
Зависимости: `04-auth-security`, `09-cash-shifts`, `11-analytics`, `30-entitlements-meter`, `31-settlement-reconciliation`, `34-durable-offline`, `37-platform-integration-evidence`, `42-test-overhaul`

## Цель

Перевести сессию игрового ПК на автономную событийную модель. После успешного
входа сервер выдаёт подписанный снимок клиента и правил. Windows-клиент может
без связи с сервером продолжать уже начатую сессию: расходовать бесплатное и
пакетное время, списывать поминутную стоимость, покупать известные пакеты из
сохранённого баланса и завершать сессию. Каждая перемена записывается на диск и
позднее доставляется серверу через Kafka.

Сервер сохраняет подтверждённые факты, строит финансовые и сессионные
проекции, публикует результаты и пополнения. Отдельно строятся read-only
аналитика и единая наблюдаемость: Grafana, Loki, Tempo, Prometheus и alerting.

## Почему это отдельная V2-граница

Текущие контракты используют gRPC heartbeat и server-backed расчёт времени,
пакетов и денег. V2 меняет владельца решений во время уже авторизованной
сессии. Это не рефакторинг транспорта: затрагиваются финансовые инварианты,
сессии, Windows-клиент, протоколы, аналитика и эксплуатация.

V2 выпускается атомарной заменой, а не поэтапным переключением ПК. В конечном
релизе существует только `v2_local_ledger`: Windows-клиент использует Kafka и
durable inbox/outbox после snapshot. V1 runtime, feature flag, fallback и
операторский переключатель удаляются из поставки. PostgreSQL с бизнес-данными
сохраняется; V1-сессия не переносится в V2 автоматически.

До фактического cutover V1 может временно существовать только в ветке
разработки как источник данных и предмет удаления. В тестовом контуре release
gate принудительно завершает все активные V1-сессии через server flow до
поставки V2-only; их нельзя переносить в V2 или смешивать с V2 debit.

## Зафиксированные решения V2

1. Kafka даёт доставку «как минимум один раз» (at-least-once), а не гарантию
   единственного выполнения. Дубли устраняют inbox, outbox, уникальные ключи и
   неизменяемый `operation_id`.
2. Клиент хранит постоянный локальный ledger, inbox и outbox. Операция не может
   существовать только в памяти; изменение локального состояния и запись в
   outbox выполняются одной локальной транзакцией.
3. Серверный inbox, доменный факт, финансовая проекция, audit и server outbox
   сохраняются одной PostgreSQL-транзакцией. Публикация Kafka выполняется после
   commit повторяемым publisher.
4. Пополнение создаётся только сервером. Клиент получает
   `BalanceCreditApplied` как идемпотентную дельту с `deposit_operation_id`, а
   не как абсолютное значение баланса.
5. Входной `OfflineSessionSnapshot` подписан, привязан к device и содержит
   balance, лимит долга, очередь пакетов, login grant, каталог доступных
   тарифов, их ценовые/зональные/временные снимки и версию правил.
6. Порядок гарантируется лишь внутри Kafka key `client_id/session_id` или
   `device_id`. Отдельный topic на клиента запрещён.
7. Heartbeat сообщает наличие устройства и watermarks inbox/outbox, но не
   подтверждает минуты, не списывает деньги и не заменяет журнал событий.
8. Аналитика и Grafana получают только подтверждённые серверные domain events.
   Сырые сообщения клиента не являются финансовой истиной.
9. Наблюдаемость использует OpenTelemetry: метрики в Prometheus, логи в Loki,
   трассы в Tempo, просмотр и alerts в Grafana. Ledger и audit остаются
   системами учёта, а не заменяются логами.
10. Каждый независимый consumer group имеет свой логический inbox. На старте
    это одна таблица с `consumer_name` в уникальном ключе, а не таблица на
    каждый event type. Отдельные физические таблицы допустимы позднее только
    при отличающихся retention, нагрузке или правах доступа.

## Обязательные инварианты

- Суммы — integer cents; цена, зона, временное окно и скидка фиксируются в
  событии debit/purchase как snapshot, не пересчитываются задним числом.
- Типы фактов различаются: `LOGIN_GRANT_CONSUME`, `LOGIN_GRANT_BURN`,
  `PACKAGE_PURCHASE`, `PACKAGE_CONSUME`, `PER_MINUTE_DEBIT`, `PACKAGE_BURN`,
  `SESSION_STOP`, `DEPOSIT_CREDIT`, `REFUND`, `CORRECTION`.
- `PER_MINUTE_DEBIT` — расход по поминутной ставке, а не покупка «минутного
  тарифа».
- Ранний выход сжигает только уже активный grant/package; не начатая очередь
  пакетов сохраняется. Ранее записанные поминутные debit не отменяются.
- Цепочка источников времени: login grant → активный пакет → следующий
  совместимый пакет → поминутное списание → `EXHAUSTED` и access-gate.
- Повторная доставка, crash между записью и publish, повторный click и restart
  не создают второе списание, пакет или пополнение.
- Клиент не создаёт внешний платёж без сервера. Пополнение, сделанное
  оператором пока ПК offline, станет видно только после доставки server event.
- Неподписанный snapshot, другой device, повторное использование sequence,
  разрыв цепочки и clock rollback переводят сессию в `NEEDS_REVIEW`; локальные
  новые финансовые действия блокируются до синхронизации.

## Декомпозиция и порядок

| Этап | Подплан | Результат | Зависит от |
| --- | --- | --- | --- |
| 0 | [00-contracts-decisions](00-contracts-decisions/PLAN.md) | утверждённые V2-правила, обновлённые product contracts и миграционная совместимость | — |
| 1 | [01-kafka-event-contracts](01-kafka-event-contracts/PLAN.md) | Kafka topics, envelope, schema, ACL, inbox/outbox ports | 0 |
| 2 | [02-client-local-ledger](02-client-local-ledger/PLAN.md) | локальный ledger, inbox/outbox, автономный session engine | 0, 1 |
| 3 | [03-server-reconciliation](03-server-reconciliation/PLAN.md) | server inbox, сверка фактов, snapshot и командные события | 0, 1 |
| 4 | [04-deposit-payments](04-deposit-payments/PLAN.md) | идемпотентное пополнение и доставка balance delta | 0, 1, 3 |
| 5 | [05-analytics-domain-events](05-analytics-domain-events/PLAN.md) | подтверждённые domain events и аналитический read-model | 1, 3, 4 |
| 6 | [06-observability-grafana](06-observability-grafana/PLAN.md) | OTel, Loki, Tempo, Prometheus, Grafana и alerts | 1, 2, 3, 4 |
| 7 | [07-migration-rollout](07-migration-rollout/PLAN.md) | атомарный V2 cutover, удаление V1 runtime и runbooks | 0–6 |
| 8 | [08-verification-evidence](08-verification-evidence/PLAN.md) | regression matrix и доказательства уровня production | 0–7 |

Этапы 1–3 можно вести параллельно после этапа 0 только по согласованным
контрактам. Нельзя включать V2 на реальном workstation до выполнения этапов
4, 6 и 8.

## Checkpoints реализации

### CP-001 — 2026-09-27: контракты и V2 inbox foundation

Выполнено:

- в `CODEX.md` и трёх product contracts добавлена V2-граница: Kafka,
  автономная сессия после snapshot, delta пополнения, постоянные inbox/outbox
  и разделение V1/V2;
- подтверждено правило одной autonomous session на клиента;
- добавлен `modules/eventing_v2`: immutable V2 event envelope с canonical
  payload hash, in-memory inbox, duplicate/conflict boundary и 4 unit-теста;
- выполнены `pytest -q tests/test_v2_event_contract.py`, Ruff check/format и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- прямой Kafka transport, schema registry, TLS/SASL/ACL и PostgreSQL inbox/outbox;
- серверная сверка фактов, client ledger, deposit delivery, Grafana и Windows
  native evidence;
- ADR о device-facing Kafka/gateway и policy clock rollback.

### CP-002 — 2026-09-27: постоянный server inbox

Выполнено:

- добавлена additive Alembic migration `20260927_0063_v2_event_inbox` с
  уникальными `(consumer_name, producer_id, operation_id)` и
  `(consumer_name, producer_id, session_id, sequence)`;
- добавлен PostgreSQL adapter, который через `INSERT ... ON CONFLICT` возвращает
  фактически сохранённого победителя; поэтому второй consumer получает
  duplicate/conflict, а не второй accepted result;
- добавлен параллельный in-memory test для двух service instances;
- inbox теперь логически разделён по `consumer_name`: один факт может один раз
  пройти обработчик фактов клиентской сессии и один раз обработчик аналитики,
  без дублирования внутри каждой группы фоновых обработчиков;
- выполнены 5 focused unit-тестов, Ruff и `alembic heads` (`0063`).

Не выполнено и не выдано за готовое:

- настоящая PostgreSQL integration/concurrency проверка: в текущем окружении
  отсутствует `GAMECLUB_TEST_POSTGRES_DSN`;
- transactional ServerOutbox, business fact/projection в той же транзакции и
  Kafka publisher/consumer;
- client-side inbox/outbox, V2 snapshot и включение feature flag.

### CP-003 — 2026-09-27: логические inbox для групп обработчиков

Выполнено:

- `v2_event_inbox` и оба repository adapter разделены по `consumer_name`;
  уникальный ключ стал `(consumer_name, producer_id, operation_id)`;
- один event теперь может быть один раз обработан `client_session_facts` и
  один раз `analytics_projection`, но повтор внутри одной группы остаётся
  duplicate;
- в V2.01 описано начальное разделение групп обработчиков: факты сессии,
  внешние платежи, аналитика, уведомления и отчёты;
- выполнены 6 focused unit-тестов, Ruff и `alembic heads` (`0063`).

Не выполнено и не выдано за готовое:

- Kafka-группы обработчиков и внешние фоновые процессы ещё не подняты;
- серверный обработчик команд ещё не соединяет inbox с одним бизнес-сценарием,
  финансовой транзакцией и outbox;
- PostgreSQL concurrency test всё ещё требует `GAMECLUB_TEST_POSTGRES_DSN`.

### CP-004 — 2026-09-27: FastStream и постоянная server outbox

Выполнено:

- в backend закреплён `faststream[kafka]` и зависимость разрешена в `uv.lock`;
- добавлена миграция `v2_server_outbox`: подтверждённое server-to-client
  событие хранит неизменяемый конверт, Kafka topic/key, число попыток и статус;
- FastStream-адаптер публикует только запись из outbox и передаёт весь V2
  конверт без изменения `event_id` или `operation_id`;
- при ошибке Kafka запись остаётся `pending`, ошибка и число попыток сохраняются;
  `published` проставляется лишь после подтверждения отправки;
- подготовлена точка регистрации FastStream-группы
  `client_session_facts`: транспорт передаёт сообщение бизнес-обработчику, не
  содержит правил списания;
- выполнены 10 focused unit-тестов, Ruff, `alembic heads` (`0063`) и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- FastStream-процесс ещё не подключён к настоящим PostgreSQL и Kafka: требуется
  запустить его в отдельном окружении с реальным брокером;
- обработчик `client_session_facts` пока не реализует проверку подписи,
  сохранение inbox, финансового факта, audit и server outbox одной транзакцией;
- нет Kafka-групп обработчиков для платежей, аналитики, уведомлений и отчётов;
- TLS/SASL, ACL, трассировка Kafka headers, schema registry и проверка Compose
  остаются следующими задачами.

### CP-005 — 2026-09-27: полный V2-конверт и проверка входящих сообщений

Выполнено:

- V2-конверт дополнен `causation_id`, обязательным `correlation_id` и W3C
  `traceparent`; новый корневой факт получает отдельный trace context;
- постоянные `v2_event_inbox` и `v2_server_outbox` хранят эти поля вместе с
  фактом, поэтому повторная отправка не теряет связь логов и трасс;
- `V2Event.from_transport_payload()` строго проверяет UUID, версию схемы,
  timestamp с timezone, тип факта, sequence, traceparent и payload hash до
  передачи сообщения в бизнес-обработчик;
- FastStream publisher передаёт `traceparent` в Kafka headers;
- выполнены 13 focused unit-тестов, Ruff, `alembic heads` (`0063`) и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- parser пока не является сам по себе финансовым обработчиком: он не проверяет
  подпись snapshot, принадлежность device/session и допустимость списания;
- нет schema registry и проверки совместимости между настоящими Windows-клиентом
  и backend;
- нет реальной проверки Kafka headers, OpenTelemetry и broker restart.

### CP-006 — 2026-09-27: общий Protobuf-контракт Kafka

Выполнено:

- создан `backend/proto/gameclub/v2/events.proto` с единым
  `EventEnvelope`, типами V2-фактов и адресным `EventProcessingResult`;
- номера полей 1–16 зафиксированы, диапазон 17–31 зарезервирован: новые версии
  добавляют только новые поля и не переиспользуют удалённые номера;
- FastStream publisher теперь отправляет сериализованный Protobuf-конверт, а
  subscriber восстанавливает и валидирует V2-факт из bytes Kafka;
- V2 `.proto` подключён к C# transport-проекту Windows-клиента;
- выполнены 36 Python contract/unit-тестов, Ruff, `alembic heads` (`0063`),
  `git diff --check` и сборка C# transport-проекта на Linux без ошибок.

Не выполнено и не выдано за готовое:

- отсутствие field number в тесте не заменяет внешний schema registry и
  совместимость с фактически выпущенной версией Windows-клиента;
- Linux-сборка C# доказывает генерацию типов, но не проверяет запуск Kafka,
  доступ к защищённому хранилищу или поведение на реальном Windows-ПК;
- server consumer пока не выполняет авторизацию устройства, финансовую
  транзакцию и controlled reject/DLQ.

### CP-007 — 2026-09-27: C#-ядро автономного local ledger

Выполнено:

- в `GameClub.Client.Core` добавлена чистая V2-модель локальной сессии без UI,
  сети и обращения к серверу;
- выбор источника времени реализует цепочку login grant → active/queued package
  → поминутное списание → `exhausted` и блокировку ПК;
- покупка использует только тариф и баланс из snapshot, учитывает лимит долга и
  добавляет пакет в очередь; неизвестный или несовместимый тариф отвергается;
- ранний выход создаёт явный факт сжигания только активного grant/package и
  `session_stopped`; неактивные queued packages сохраняются;
- server `BalanceCreditApplied` применяет только дельту и только один раз,
  поэтому не перезаписывает локальные поминутные списания;
- выполнены 36 Python-тестов и 56 C# тестов на Linux, включая сценарии V2
  ledger; `git diff --check` прошёл.

Не выполнено и не выдано за готовое:

- V2 ledger пока не хранится на диске и не пишет outbox атомарно с изменением
  состояния; текущий V1 `JsonlOfflineJournal` для этого не используется;
- локальная модель не подключена к Avalonia UI, snapshot signature, Kafka
  publisher или access-gate;
- Linux-тесты не доказывают DPAPI, filesystem recovery и kiosk-поведение на
  реальном Windows-ПК.

### CP-008 — 2026-09-27: постоянный V2 ledger и client outbox

Выполнено:

- добавлен `V2LocalLedgerCoordinator`: он сериализует действия клиента и
  сохраняет новый ledger вместе с фактами ClientOutbox до любой отправки;
- Windows-адаптер хранит один DPAPI-защищённый файл, пишет через временный файл
  с `WriteThrough`/flush и заменяет основной файл только после полного commit;
- после неполной первой записи storage восстанавливает временный файл, если
  основной ещё не существует; повреждённое содержимое не игнорируется молча;
- outbox может читаться и подтверждаться отдельно, не меняя уже записанный
  финансовый факт; серверное пополнение сохраняет только balance delta, без
  ложного client outbox event;
- выполнены 58 C# тестов, сборка Windows-проекта на Linux, 36 Python-тестов,
  Ruff и `git diff --check`.

Не выполнено и не выдано за готовое:

- watermarks и Kafka publisher/consumer ещё не используют coordinator;
- Linux-сборка только компилирует Windows DPAPI-код: нужно проверить запись,
  reboot, disk-full, ACL и recovery на реальном Windows-ПК;
- пока V2 coordinator не подключён к Avalonia, access-gate и подписанному
  `OfflineSessionSnapshot`.

### CP-009 — 2026-09-27: ClientInbox и transport-neutral outbox publisher

Выполнено:

- ClientInbox добавлен в тот же защищённый снимок, что ledger и ClientOutbox;
  `BalanceCreditApplied` запоминается по event/operation id до возврата успеха;
- повтор того же server event не прибавляет депозит, а повторное использование
  operation id с другим event id вызывает явную ошибку;
- фоновый отправитель outbox соблюдает sequence: после первой ошибки транспорта
  он оставляет текущий и все последующие факты на диске;
- local fact теперь сам содержит client/session/device/correlation/trace
  контекст; C# serializer переводит его в общий Protobuf `EventEnvelope` без
  повторного чтения изменяемого ledger;
- выполнены 61 C# тест, сборка Windows-проекта на Linux и `git diff --check`.

Не выполнено и не выдано за готовое:

- фактический Kafka client или device gateway не выбран и не подключён;
- не реализованы retry/backoff, heartbeat watermarks и commit offset настоящего
  брокера;
- ClientInbox пока применяет только `BalanceCreditApplied`, не все server events.

### CP-010 — 2026-09-27: signed OfflineSessionSnapshot contract

Выполнено:

- создан общий Protobuf-контракт `OfflineSessionSnapshotPayload` и wrapper с
  `signing_key_id`/`signature`; в snapshot входят ids, баланс, limit долга,
  login grant, packages, тарифные снимки и версия policy;
- подпись строится по deterministic serialization именно payload, а не по
  изменяемому wrapper; C# создаёт V2 ledger только после успешного verifier;
- каждый generated local fact содержит `snapshot_id` и `snapshot_version` в
  каноническом payload, поэтому server сможет проверять границы выданных правил;
- Python и C# используют один фиксированный fixture детерминированных Protobuf
  bytes; он предотвращает расхождение формата подписи;
- выполнены 37 Python-тестов, 64 C# теста, Linux-сборка Windows-проекта, Ruff
  и `git diff --check`.

Не выполнено и не выдано за готовое:

- backend ещё не читает реальные balance/packages/catalog и не выдаёт snapshot;
- нет production-реализаций Ed25519/key rotation/revocation и проверки
  device/TTL/policy; verifier пока является port;
- snapshot не подключён к реальному V2 login/Avalonia flow.

### CP-011 — 2026-09-27: server sequence/hash-chain guard

Выполнено:

- backend V2 domain получил модель checkpoint одной client/session/device
  цепочки и принимает только следующий `sequence` с hash предыдущего payload;
- пропуск sequence получает отдельный результат `gap`, а смена client/device/
  producer или неверный `previous_hash` — `conflict`;
- guard не пересчитывает минуту и не меняет баланс: он только отсекает
  недопустимый immutable факт до бизнес-обработчика;
- выполнены 39 Python contract/unit-тестов, Ruff и `git diff --check`.

Не выполнено и не выдано за готовое:

- checkpoint пока не хранится в PostgreSQL и не сравнивается атомарно с inbox,
  финансовым фактом и outbox;
- device auth, snapshot signature/bounds, controlled reject/DLQ и actual
  FastStream consumer остаются до реализации;
- нет настоящей Kafka/PostgreSQL конкурентной проверки.

### CP-012 — 2026-09-27: постоянный server chain checkpoint

Выполнено:

- `v2_session_chains` добавлена в ещё не применённую additive migration `0063`;
  она хранит client/device/producer scope, последний sequence, hash и timestamp;
- PostgreSQL adapter делает insert первого факта или compare-and-save update по
  предыдущему sequence, поэтому проигравший параллельный обработчик не
  продвигает checkpoint;
- application service использует тот же контракт в in-memory проверке и не
  считает конфликт принятым фактом;
- выполнены 40 Python-тестов, Ruff, `alembic heads` (`0063`) и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- текущие inbox, chain и outbox repositories открывают собственные сессии:
  один общий PostgreSQL unit of work с финансовым фактом ещё не реализован;
- настоящая PostgreSQL concurrency-проверка требует задать
  `GAMECLUB_TEST_POSTGRES_DSN`; в текущем окружении переменной нет;
- FastStream consumer всё ещё не использует этот service в рабочем процессе.

### CP-013 — 2026-09-27: server snapshot signing boundary

Выполнено:

- backend получил adapter для deterministic Protobuf bytes snapshot и port
  `V2OfflineSnapshotSigner`; V2 use case не получает приватный ключ;
- подписанный wrapper содержит только payload, key id и bytes signature;
  C# verifier использует те же payload bytes из CP-010;
- выполнен тест, подтверждающий, что signer получает именно deterministic bytes,
  а не сериализацию wrapper или изменяемый объект;
- выполнены 41 Python-тест, Ruff и `git diff --check`.

Не выполнено и не выдано за готовое:

- нет production-адаптера Ed25519/key rotation/revocation и защищённого
  хранилища server private key;
- server пока не собирает snapshot из фактических client/balance/package/tariff
  данных и не выдаёт его при V2 login;
- нет device auth/V2 lease и реальной C# проверки ключом клуба.

### CP-014 — 2026-09-27: V2 Kafka Compose и живой FastStream outbox-процесс

Выполнено:

- в отдельном Compose profile `v2` добавлен single-node Kafka KRaft для
  локального контура и отдельный одноразовый сервис создания четырёх
  versioned topics: `v2.client-events`, `v2.server-events`,
  `v2.confirmed-domain-events`, `v2.failed-events`;
- добавлен `v2-server-outbox`: FastStream открывает PostgreSQL, запускает
  повторяемую доставку только после подключения к Kafka и ставит `published`
  лишь после подтверждения брокером;
- запуск V2 изолирован от V1: без `--profile v2` существующие сервисы не
  зависят от Kafka; брокер на host доступен только через `127.0.0.1:29092`;
- Compose config, 42 focused Python contract-теста, Ruff и `git diff --check`
  выполнены.

Не выполнено и не выдано за готовое:

- dev Kafka намеренно plaintext single-node; для production не готовы TLS/SASL,
  ACL, quota, retention/backup и multi-broker отказоустойчивость;
- `v2-server-outbox` не является серверным consumer: `client_session_facts`
  нельзя включать, пока одна PostgreSQL-транзакция inbox+financial/audit/outbox
  и controlled reject/DLQ не готовы;
- нет сквозной отправки реального server event и нет Kafka/Windows client
  transport, observability и Grafana evidence.

### CP-015 — 2026-09-27: сквозная Compose-проверка server outbox → Kafka

Выполнено:

- реальные `kafka` (healthy), `postgres` (healthy) и `v2-server-outbox`
  запущены через Compose; Alembic применил additive migration `0063` и
  проверены таблицы `v2_event_inbox`, `v2_server_outbox`, `v2_session_chains`;
- инициализатор создал все V2 topics: `v2.client-events`,
  `v2.server-events`, `v2.confirmed-domain-events`, `v2.failed-events`;
- в постоянный server outbox добавлен один изолированный smoke-факт. Worker
  повторил доставку, сохранил `published` только после ответа Kafka, а
  отдельный `aiokafka` consumer прочитал и валидировал исходный Protobuf
  envelope, key и payload;
- во время smoke найдены и исправлены две production-конфигурационные ошибки:
  в образе отсутствовал extra `faststream[cli]`, а Kafka key передавался
  строкой вместо bytes. Обе покрыты зависимостью/контрактным тестом; сбойная
  запись не потерялась и была доставлена после перезапуска.

Не выполнено и не выдано за готовое:

- это доказательство только ветки server outbox → Kafka. Нет безопасного
  consumer client events, финансовой обработки, топ-апа, клиентского Kafka
  транспорта, tracing/metrics/log collection и Windows проверки;
- dev broker остаётся single-node plaintext: TLS/SASL/ACL, quorum, backup,
  retention/compaction и production monitoring не выполнены.

### CP-016 — 2026-09-27: source-level контур наблюдаемости

Выполнено:

- `v2-server-outbox` получил opt-in OpenTelemetry/Prometheus middleware без
  высококардинальных технических labels; в Compose добавлены Collector,
  Prometheus, Loki, Tempo, Alloy и Grafana с datasource и стартовой V2-панелью;
- docker-логи до отправки в Loki проходят через локальную маскировку типовых
  `password`/`token`/`authorization` значений;
- `docker compose config`, 42 focused Python contract-теста, Ruff и
  `git diff --check` выполнены.

Не выполнено и не выдано за готовое:

- Docker daemon не смог скачать образы наблюдаемости из-за недоступного IPv6
  пути к Docker Registry. Поэтому сервисы не запущены, живые metric/log/trace,
  Grafana и redaction ещё не проверены;
- нет Kafka/PostgreSQL/host exporter-ов, alert rules/routes, RBAC/backup и
  instrumentation Windows-клиента;
- реальная e2e-проверка нужна после восстановления доступа Docker к registry:
  outbox publish → metric/log/trace → Grafana drill-down.

### CP-017 — 2026-09-27: атомарное server popолнение и delivery facts

Выполнено:

- добавлены migration `0064` и V2 application/infrastructure boundary для
  серверного `payment_operation_id`: request hash отличает разрешённый retry
  от другого запроса с тем же ключом;
- в одном PostgreSQL commit сохраняются баланс и существующий
  `balance_operations` ledger, payment parts, движение открытой cash shift,
  audit, immutable `v2_deposit_credits` и два outbox-факта — client delivery
  и confirmed domain event для дальнейшей аналитики;
- на Kafka клиент получает только идемпотентную delta/currency/deposit id и
  типы способов оплаты, без абсолютного balance и payment reference;
- migration применена к живой Compose PostgreSQL. Реальный smoke подтвердил
  exactly-once effect при retry и доставку двух Protobuf events в
  `v2.server-events` и `v2.confirmed-domain-events`. Ошибка несуществующей
  cash shift откатила ledger, balance, deposit и outbox вместе;
- выполнены 46 focused Python тестов, Ruff, `alembic heads` (`0064`) и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- нет публичного operator endpoint, авторизации и server-owned разрешения
  target V2 session/device; input пока должен строить доверенный backend;
- нет глобального `ledger_version`, refund/correction, operator pending UI,
  analytics consumer и C# Kafka inbound dispatcher;
- успешная ветка cash shift пока не имеет отдельного live smoke;
- Docker image текущего worker не пересобран после последних source changes:
  Docker Registry недоступен по IPv6. Уже работающий generic publisher
  доставил outbox, но это не заменяет пересборку образа и полный e2e после
  восстановления registry.

### CP-018 — 2026-09-27: атомарное принятие client session facts

Выполнено:

- migration `0065` исправляет физическую inbox-границу: один Kafka event
  теперь законно имеет строку в нескольких логических consumer groups, потому
  что primary key — `(consumer_name, event_id)`, а не один глобальный event id;
- добавлена PostgreSQL reconciliation application boundary. Она берёт locks
  operation/session, проверяет допустимый тип client fact, duplicate/conflict
  и hash-chain, а затем одной транзакцией пишет inbox, immutable confirmed
  fact, chain checkpoint, audit и `ReconciliationCompleted` в server outbox;
- на живой Compose PostgreSQL integration test доказал accepted/duplicate/
  следующий sequence и fan-out: 3 inbox rows для двух consumers, но только
  2 confirmed facts, audit и outbox results. Повтор не создаёт второй side
  effect;
- migration `0065`, 47 focused Python тестов, Ruff, Compose config и
  `git diff --check` выполнены.

Не выполнено и не выдано за готовое:

- FastStream consumer всё ещё не подключён к этой boundary: нет device auth,
  signed snapshot/lease validation, controlled reject/DLQ и consumer-offset
  recovery policy;
- confirmed source fact ещё не построил financial/package/session projection;
  сервер не подтверждает минуты, но и не выполняет финальную бизнес-проверку
  допустимости этих фактов;
- нет server command events, authoritative reconciliation snapshot и
  production Kafka security/observability evidence.

### CP-019 — 2026-09-27: lease guard для client facts

Выполнено:

- migration `0066` добавляет server-owned V2 lease с client/device/session,
  snapshot id/version, policy, сроком и статусом;
- до записи inbox reconciliation блокирует и проверяет active non-expired
  lease, совпадающий с client/device/session факта. Без него факт не может
  стать confirmed source fact или породить outbox side effect;
- живая PostgreSQL integration проверка с подготовленным active lease прошла.

Не выполнено и не выдано за готовое:

- lease пока не выпускается production use case после device auth и
  подписанного OfflineSessionSnapshot; нет revoke/expiry workflow, unique
  active lease policy, snapshot-id binding в факте и V2 login endpoint;
- Kafka consumer остаётся выключенным до закрытия этих входных проверок.

### CP-020 — 2026-09-27: lease guard для V2 deposit

Выполнено:

- V2 popолнение теперь требует тот же active non-expired lease по
  client/device/session до изменения баланса; нет lease — нет ledger, audit,
  deposit и outbox side effect;
- PostgreSQL integration test подтверждает отказ без lease, один commit после
  matching lease и duplicate-safe повтор. Всего V2 focused suite: 48 тестов.

Не выполнено и не выдано за готовое:

- пока отсутствуют V2 login/signed snapshot/lease issuer и операторский V2
  endpoint, поэтому это защищённая application boundary, не подключённая к UI;
- прежний V1 top-up остаётся совместимым маршрутом и не создаёт V2 events.

### CP-021 — 2026-09-27: issuer автономного lease и V2 snapshot factory

Выполнено:

- migration `0067` разрешает бессрочный active lease: длительный offline не
  прекращает автономную сессию сам по себе;
- lease issuer исключает вторую active V2-сессию у client или device и
  идемпотентно возвращает тот же snapshot lease;
- snapshot factory собирает V2 Protobuf payload из текущих server-owned
  Client/Session/Entitlement/Tariff данных, сохраняя deterministic bytes для
  отдельного signer port.

Не выполнено и не выдано за готовое:

- нет production signing key, C# public-key verifier, device-authenticated
  V2 login, atomic issue+lease+outbox и revoke flow. Поэтому новый V2 login
  ещё нельзя включить в реально работающем клиенте.

### CP-022 — 2026-09-27: Ed25519 signer и public-key verifier

Выполнено:

- server signer принимает только raw 32-byte Ed25519 private seed из отдельной
  secret-настройки и выдаёт подпись deterministic snapshot payload. Это не JWT
  secret и не значение, которое может попасть на Windows PC;
- C# verifier выбирает public key по `signing_key_id`, поэтому будущая ротация
  может держать два публичных ключа без доступа клиента к private key;
- проверены известный Ed25519-вектор и реальный полный protobuf payload между
  Python и C#. Одновременно исправлена семантика `debt_limit_cents`: предел
  долга всегда неотрицательный и одинаково проверяется сервером и client ledger.

Не выполнено и не выдано за готовое:

- private key пока не интегрирован с production secret storage, а набор public
  keys ещё не выдаётся через deployment config Windows-клиента;
- login snapshot ещё не создаётся из реального device-authenticated запроса и
  не выдаёт lease/outbox атомарно.

### CP-023 — 2026-09-27: атомарное хранение signed snapshot

Выполнено:

- migration `0068` хранит exact signed snapshot bytes, `key_id` и payload hash
  вместе с lease. Повторный запрос возвращает исходные bytes, а не новый
  snapshot с другим временем или балансом;
- один PostgreSQL commit фиксирует exclusive lease, `LoginSnapshotIssued` в
  server outbox и audit; реальная PostgreSQL-проверка доказала один результат
  после повтора;
- server reconciliation теперь требует, чтобы `snapshot_id` и
  `snapshot_version` в local fact совпали с active lease. Несовпадение
  останавливается до inbox/chain/audit/outbox side effect.

Не выполнено и не выдано за готовое:

- Windows access-gate пока не получает snapshot этим путём;
- отсутствуют production key deployment/rotation и revoke-команда клиента.

### CP-024 — 2026-09-27: режим ПК и отдельный V2 login

Выполнено:

- `0069` хранит явный режим ПК: по умолчанию `v1_server_owned`, V2 включается
  только выбором `v2_local_ledger` через операторское обновление ПК;
- новый `OfflineSessionService.Login` требует совпадающую device identity и
  пароль клиента, создаёт только новую сессию `v2_local_ledger` и возвращает
  signed snapshot из server-owned client/session/package/tariff данных;
- при повторе после потери ответа PostgreSQL возвращает сохранённые bytes
  исходного snapshot без второго login outbox/audit. Это подтверждено unit,
  gRPC и настоящими PostgreSQL-проверками.

Не выполнено и не выдано за готовое:

- новый gRPC-контракт подключён в C# transport, но access-gate его пока не
  вызывает; public key deployment, ротация и revoke отсутствуют;

### CP-025 — 2026-09-27: атомарный V2 login

Выполнено:

- узкий public transaction writer Sessions скрывает таблицу `gaming_sessions`,
  но позволяет V2 boundary сохранить уже проверенную новую Session внутри
  PostgreSQL-транзакции V2;
- новая Session, signed snapshot, exclusive lease, audit и login outbox теперь
  фиксируются одним commit. Конфликт lease после подготовки Session откатывает
  Session вместе с остальными изменениями;
- это подтверждено настоящей PostgreSQL-проверкой rollback и существующими
  unit/gRPC-проверками V2 login.

Не выполнено и не выдано за готовое:

- нужно поднять и проверить Docker-контейнеры приложения с новой сборкой и
  вручную пройти V2 gRPC-сценарий. Текущие PostgreSQL-тесты не доказывают, что
  новый код находится в пользовательском контейнере.

### CP-026 — 2026-09-27: операторская граница режима ПК

Выполнено:

- режим `v1_server_owned` / `v2_local_ledger` проходит через HTTP API и
  операторский редактор ПК; карта показывает текущий режим;
- backend не позволяет переключить режим при active session, даже если запрос
  был отправлен не через UI. Операторский select отключён в таком состоянии;
- TypeScript typecheck, 11 frontend-тестов и backend unit/PostgreSQL V2
  проверки прошли.

Не выполнено и не выдано за готовое:

- нужно открыть интерфейс в обычном браузере и вручную проверить создание
  V1- и V2-ПК, блокировку переключателя у active session и текст ошибки backend.
  Автоматические frontend-тесты не проверяют конечное расположение и
  читаемость элементов на экране.

### CP-027 — 2026-09-27: HTTP V2-пополнение

Выполнено:

- отдельный защищённый операторский маршрут V2-пополнения создаёт стабильный
  payment operation из `client_id` и `Idempotency-Key`, требует target
  session/device и проходит server-owned lease validation;
- результат возвращает только финансовые/доставочные identifiers и
  `pending_delivery`, а PostgreSQL boundary по-прежнему создаёт ledger, audit
  и клиентское/подтверждённое outbox события одной транзакцией;
- API и PostgreSQL-тесты прошли.

Не выполнено и не выдано за готовое:

- на этом checkpoint операторский экран ещё не выбирал V2 target; эта
  интеграция добавлена следующим CP-028. Ручная browser-проверка всё ещё
  обязательна.

### CP-028 — 2026-09-28: V2-пополнение из операторской панели

Выполнено:

- пополнение из панели занятого V2 ПК теперь передаёт его активные
  `session_id` и `device_id` в отдельный V2-маршрут. Получатель фиксирован,
  поэтому тот же экран не может случайно пополнить другого клиента или уйти в
  V1 `top-up`;
- после server commit UI остаётся открытым и показывает «пополнение принято
  сервером; событие ожидает доставки на ПК». Это `pending_delivery`, а не
  ложное утверждение, что Windows-клиент уже применил delta;
- TypeScript typecheck, component test адресации/статуса и frontend production
  build прошли.

Не выполнено и не выдано за готовое:

- нет server read-model, сообщающего оператору о фактическом применении
  конкретного события на Windows-клиенте; пока отображается только начальный
  pending status;
- нужно открыть интерфейс в обычном браузере и вручную пройти сценарий с
  настоящими V2 lease и сервером. Сборка и component test не подтверждают
  расположение UI, сетевую доставку или работу контейнеров с новым кодом.

### CP-029 — 2026-09-28: локальная проверка и применение server event

Выполнено:

- Windows-клиент получил Protobuf-обработчик `BalanceCreditApplied`: до записи
  проверяются server producer, payload hash и точное совпадение
  client/session/device. Затем delta сохраняется через ClientInbox; duplicate
  не увеличивает баланс второй раз;
- несовпадающее событие возвращает controlled `Rejected` и не меняет ledger;
- `dotnet test ./win-client/tests/GameClub.Client.Tests.csproj --no-restore`
  прошла на Linux: 69 тестов, включая отказ при подмене payload.

Не выполнено и не выдано за готовое:

- это пока не живой Kafka consumer, результат не отправляется server-side и
  не обновляет операторский delivery status. Нужны Kafka lifecycle, commit
  offset после disk commit, controlled DLQ и native Windows проверка.

### CP-030 — 2026-09-28: серверный FastStream consumer client facts

Выполнено:

- Compose profile `v2` получил отдельный worker `v2-client-facts`; он не
  пересчитывает минуты, а отдаёт факт существующей atomic reconciliation
  boundary с lease/snapshot/inbox/hash-chain guard;
- accepted/duplicate доходят до Kafka offset только после PostgreSQL commit;
  невалидный или конфликтный факт до подтверждения offset копируется в
  закрытый `v2.failed-events`. Добавлены Prometheus и Grafana/Loki source
  configuration для второго worker;
- worker собран и работает в Compose. Настоящий Protobuf-факт прошёл Kafka →
  worker → PostgreSQL; у consumer group `client_session_facts` нулевой lag.
  Focused Python + PostgreSQL/Kafka-проверки: 29 passed; Ruff и Compose config
  прошли.

Не выполнено и не выдано за готовое:

- проверена только accepted-ветка живой Kafka delivery. Нужны live DLQ,
  restart между DB commit и offset, TLS/SASL/ACL, durable audit reject и
  Windows Kafka transport.

### CP-031 — 2026-09-28: живой контур наблюдаемости V2

Выполнено:

- подняты Compose-сервисы OpenTelemetry Collector, Prometheus, Loki, Tempo,
  Alloy и Grafana. Исправлены их реальные runtime-настройки: хранилище Tempo
  перенесено с entrypoint `/tempo` в `/var/tempo`, OTLP-приёмники доступны
  внутри сети Compose, Loki получил хранилище delete requests, а Alloy получает
  Docker-цели через `discovery.docker`;
- Grafana отвечает и содержит datasource Prometheus/Loki/Tempo и обе V2
  панели. Prometheus видит `v2-client-facts` как `up`;
- настоящий Kafka-факт дал два спана в Collector, одну трассу в Tempo и
  записи `Received`/`Processed` в Loki для `gameshell-v2-client-facts-1`.

Не выполнено и не выдано за готовое:

- нет проверки маскирования на специально созданном секрете, exporter-ов
  Kafka/PostgreSQL/host, alert rules/routes, RBAC/backup и Windows
  instrumentation;
- metric → trace → log доказан для worker-факта, но drill-down до audit по
  `operation_id` и отказные/восстановительные сценарии остаются подплану 08.

### CP-032 — 2026-09-28: server-only payment breakdown для V2 аналитики

Выполнено:

- confirmed `BalanceCreditApplied` для `v2.confirmed-domain-events` получил
  суммы по методам оплаты. Сообщение на Windows не изменено: в нём остаются
  только delta и типы методов, без ссылок платёжного провайдера;
- application-граница переводит только server-confirmed deposit в
  идемпотентные analytics outbox facts по способам оплаты. Replayed факт не
  удваивает `deposit_income_cents`, raw client event отклоняется. Добавлен
  отдельный логический inbox `confirmed_analytics` с безопасным повтором;
- контрактные проверки пополнения и переводчика прошли: 6 тестов, Ruff и
  `git diff --check`.

Не выполнено и не выдано за готовое:

- projection/backfill и метрики расходования депозита ещё не реализованы.

### CP-033 — 2026-09-28: отдельный consumer подтверждённой V2-аналитики

Выполнено:

- `v2-confirmed-analytics` читает `v2.confirmed-domain-events` отдельной
  группой `confirmed_analytics`; raw client event, повреждённый payload и
  conflict сначала переносятся в `v2.failed-events`, а временная ошибка не
  подтверждает Kafka offset;
- repository одной PostgreSQL-транзакцией записывает logical inbox и
  idempotent analytics outbox. Worker не изменяет balance, session или
  entitlement;
- Compose/Prometheus/Grafana получили worker и его наблюдаемость. 6 focused
  тестов, Ruff, Compose config и `git diff --check` прошли; живой Compose
  Kafka → worker → PostgreSQL и Prometheus `up = 1` подтверждены.

Не выполнено и не выдано за готовое:

- projection/backfill и метрики расходования депозита; следующий набор
  confirmed facts для списаний, пакетов, сессий, возвратов и корректировок.

### CP-034 — 2026-09-28: projection confirmed V2-фактов

Выполнено:

- scheduler ставит read-only `analytics-projection`, а отдельный
  `analytics-worker` обслуживает только analytics queues, не смешиваясь с
  billing/session workers;
- worker применяет immutable analytics outbox в existing projection и логирует
  число фактов без discarded Dramatiq result;
- живой Compose-путь Kafka → confirmed analytics inbox/outbox → Dramatiq
  projection подтвердил `analytics_projection_events`. 6 integration и
  11 unit-проверок прошли.

Не выполнено и не выдано за готовое:

- backfill и метрики расходования депозита; следующие confirmed facts для
  списаний, пакетов, сессий, возвратов и корректировок.

### CP-035 — 2026-09-28: confirmed поминутное списание для аналитики

Выполнено:

- `PER_MINUTE_DEBIT` получил единый V2 payload: `amount_cents` и `tariff_id`
  обязательны, а legacy `debit_delta_cents` не принимается;
- только после server reconciliation в том же PostgreSQL commit добавляется
  новый server-owned факт в `v2.confirmed-domain-events`. Он не содержит
  `balance_after_cents` и не меняет balance/session/entitlement;
- отдельный analytics consumer записывает `wallet_debit_cents`, не добавляя
  `revenue_cents` или повторный доход от пополнения. Настоящая Compose-проверка
  прошла цепочку client Kafka → server outbox → confirmed analytics →
  Dramatiq projection.

Не выполнено и не выдано за готовое:

- не реализованы backfill, package/session/refund/correction facts, TLS/SASL/ACL
  и Windows Kafka transport. Нужно отдельно определить их финансовую семантику
  и проверить на реальном Windows-ПК; Linux/Compose-проверка этого не доказывает.

### CP-036 — 2026-09-28: persistent backfill confirmed debit facts

Выполнено:

- PostgreSQL хранит cutoff/cursor/status исторического backfill и durable skip
  для legacy/повреждённого факта; одна порция атомарно пишет analytics outbox и
  продвигает cursor;
- `debit_delta_cents` не интерпретируется как V2-сумма. Только актуальный
  `amount_cents` даёт `wallet_debit_cents`, без дополнительной выручки;
- настоящий PostgreSQL-тест подтвердил resume при одинаковом времени,
  legacy skip и идемпотентный completion.

Не выполнено и не выдано за готовое:

- Docker image с CP-036 пока не собран: Docker Hub временно недоступен.
  Нужно пересобрать и перезапустить analytics-worker/scheduler после
  восстановления сети; проверка PostgreSQL не доказывает запуск нового actor
  в контейнере.

### CP-037 — 2026-09-28: решение об атомарном V2 cutover

Зафиксировано решение продукта:

- V2 поставляется одной заменяющей версией, без per-PC rollout, pilot,
  coexistence, V1 fallback и режима `v1_server_owned`;
- PostgreSQL с клиентами, балансами, пакетами, тарифами, местами и историей
  сохраняется. Это не означает сохранение V1 runtime или автоматический перенос
  active V1 session в V2;
- перед удалением V1 runtime нужен полный V2 end-to-end proof и отдельный
  runbook. В тестовом контуре он принудительно завершает active V1 sessions
  через `POST /api/v1/sessions/cutover/terminate-v1` с явным header-confirmation
  до V2-only release. Тот же одноразовый endpoint затем переводит все
  неархивные workstation records в `v2_local_ledger`; он не переносит V1
  session или ledger и безопасен при повторе. Сначала runbook закрывает V1
  entry path, а временный cutover endpoint удаляется вместе с V1 runtime.
- `SessionService` и command service на доменной границе отвергают V1 action
  для `v2_local_ledger` (и обратное несовпадение V2 action/V1 place), поэтому
  скрытие V1 UI не является единственной защитой.
- В test Compose фактически выполнен cutover: до операции active V1 sessions
  было `0`, V1 workstations — `6`; endpoint перевёл `6` мест. После операции
  все `6` неархивных мест — `v2_local_ledger`. Live probes V1 session start и
  V1 `session.stop` вернули `409 conflict` и не создали session.

Исторические CP-024 и CP-026 описывают временную реализацию в ветке и не
являются целевым поведением поставляемого продукта.

### CP-041 — 2026-09-28: V2 device bootstrap и heartbeat

Выполнено:

- добавлен отдельный `DeviceControlService` V2: public health, enrollment по
  MAC/`installation_id` и device-authenticated heartbeat;
- enrollment выдаёт только device JWT с `workstations.connect`; pending,
  disabled и привязка к другому installation остаются явными состояниями;
- heartbeat передаёт конфигурацию места и lockdown policy, но структурно не
  содержит active session или server-meter snapshot;
- Windows V2 host использует V2 gRPC для health, enrollment и heartbeat; в его
  пути больше нет HTTP `/api/v1/auth/device-enrollment`, V1 system RPC или V1
  workstation heartbeat;
- Windows release ссылается на отдельные `GameClub.Client.Avalonia.V2` и
  `GameClub.Client.Transport.V2.Grpc`; проверенный `HubShell.deps.json` содержит
  только эти V2 assemblies и не содержит V1 transport/protobuf dependency;
- в тестовом Compose пересобран и перезапущен только `backend-grpc`; живой
  `DeviceControlService.GetHealth` на `127.0.0.1:51051` вернул
  `gameclub-backend | ok | 2.0.0`;
- выполнены 27 focused backend-тестов, Ruff, 82 C# теста и Linux build Windows
  project. Это не native Windows runtime proof.

Не выполнено и не выдано за готовое:

- V2 command transport для operator lock/restart/revocation ещё не реализован;
  V2 host поэтому не запускает V1 command loop;
- Linux development host запускает V2 gRPC/HTTP composition с plaintext dev
  ledger для ручного тестирования; Windows production по-прежнему использует
  отдельную DPAPI composition;
- отсутствует end-to-end proof против собранного V2 backend и нативная проверка
  enrollment, DPAPI ledger, reboot, locking и reconnect.

### CP-042 — 2026-09-28: V2 device revocation

Выполнено:

- disabled workstation возвращает V2 heartbeat controlled `ALREADY_EXISTS`;
  V2 transport переводит его в typed `DeviceEnrollmentDisabledException`;
- heartbeat loop прекращается, сообщает offline и вызывает access-gate lock.
  Локальный V2 ledger не удаляется и не получает ложный server stop;
- проверены backend gRPC status и клиентское поведение: 28 focused backend
  тестов, 83 C# теста и Windows build на Linux.

Не выполнено и не выдано за готовое:

- V2 operator command/restart transport и его Windows proof остаются отдельной
  работой. Переносить V1 `session.start`/server meter в него запрещено.

### CP-043 — 2026-09-28: V2 operator device commands

Выполнено:

- отдельный V2 operator HTTP route
  `POST /api/v2/workstations/{workstation_id}/device-commands` требует
  `workstations.manage`, `Idempotency-Key` и принимает только
  `v2.display.lock` либо `v2.system.restart`;
- `DeviceControlService` получил отдельные authenticated
  `WatchCommands/AcknowledgeCommand`. Он фильтрует persistent command store по
  V2 vocabulary, поэтому сохранённая V1 `session.start/stop` не может попасть
  в V2 Windows binary или быть подтверждена им;
- V2 Windows transport читает этот stream, подтверждает результат, а отдельный
  `V2WindowsCommandExecutor` умеет только lock application shell и lock +
  scheduled restart. У него отсутствует session gateway;
- covered backend gRPC test dispatches both legacy `session.stop` and V2 lock,
  observes only V2 lock, rejects acknowledgement of the legacy command, then
  acknowledges V2 lock. Focused backend suite: 29 tests; 84 C# tests and V2
  Windows build succeed on Linux.

Не выполнено и не выдано за готовое:

- native Windows proof нужен для реального lock, restart, redelivery after lost
  acknowledgement and reconnect. Linux build не доказывает эти сценарии.

Дополнительно в operator frontend:

- новые места создаются только с `v2_local_ledger` и V2 capabilities; ручной
  selector V1/V2 удалён;
- V2 PC panel не получает V1 session meter, не показывает V1 stop/charge/
  transfer actions и отправляет только V2 lock/restart на versioned route;
- 63 frontend tests, TypeScript typecheck и production build прошли.

Проверка после фактического test cutover:

- backend HTTP и gRPC, а также frontend Compose services пересобраны без reset
  PostgreSQL; оба backend healthchecks healthy, live V2 health ответил
  `gameclub-backend|ok|2.0.0`;
- `pytest` без baseline convention-only test: 298 passed, 32 skipped. Skips
  требуют отдельный `GAMECLUB_TEST_POSTGRES_DSN` либо Kafka/Redis настройки и
  не считаются доказательством DSN-интеграции;
- полный `pytest` дополнительно падает только на уже существующем convention
  check: он требует русские docstring у множества старых тестов. Новые V2 tests
  имеют русские описания; массовая правка несвязанных test docstrings не входит
  в cutover.

### CP-044 — 2026-09-30: регрессия V2-поминутки и гостевых тарифов

Выполнено:

- добавлены 22 поведенческих C# теста для локального V2 ledger и minute runner:
  переход после пяти бесплатных минут на поминутный тариф, списание каждой
  минутной границы, задержка/повтор/откат часов, лимит долга, exhaustion,
  пакетный приоритет, покупка, идемпотентность, server credit и early exit;
- добавлены 11 Python тестов гостевой продажи: наличные, перевод, смешанная
  оплата, идемпотентность, количество, аудитория, канал продажи, занятое место,
  зона и обязательная кассовая смена;
- полный C# набор прошёл 113 тестов, backend billing/catalog slice — 53 теста,
  новый гостевой набор — 11 тестов;
- ручной Linux V2 smoke подтвердил принятие сервером пяти `login_grant`, трёх
  `per_minute_debit` по 100 копеек и `session_stopped` после нулевого баланса
  для session `582467e4-6726-4d5a-8c09-0b69e00b90f0`.

Граница доказательства: это подтверждает переносимую логику и текущий Linux
контур. Настоящая PostgreSQL concurrency-проверка через отдельный DSN,
fault-injection и native Windows runtime timer остаются отдельными проверками.

## Границы работы

Входит:

- замена Windows business-session gRPC-потока на Kafka topics и события;
- автономная локальная логика времени/пакетов/поминутки после login snapshot;
- inbox/outbox на клиенте и сервере, сверка фактов и обработка конфликтов;
- серверное пополнение, возвраты/корректировки как финансовые факты;
- event-driven analytics, audit reference и Grafana observability;
- атомарный cutover, удаление V1 runtime, документация и эксплуатационные
  сценарии.

Не входит без отдельного плана:

- приём банковского платежа непосредственно Windows-клиентом;
- обслуживание неизвестного клиента или новый вход без ранее полученного
  snapshot;
- работа одного клиента одновременно в двух автономных сессиях;
- доверие к скомпрометированному игровому ПК как к финансово безопасному узлу;
- выделение bounded contexts в независимые микросервисы.

## Риски и ограничения

Автономный клиент означает, что управляемый игровой ПК временно получает право
принять финансовое решение по заранее выданному балансу. Kafka и подпись не
защищают от администратора, изменившего приложение или диск ПК. Для V2 нужен
явный threat model: доверенное устройство, защищённое хранение ключей, kiosk
policy, device revocation, audit и ручная обработка конфликтов. Если такая
модель неприемлема, автономная покупка пакетов и поминутка невозможны по
определению.

## Критерии готовности master-плана

- на тестовом PC можно отключить сервер после V2 login и пройти grant,
  package, auto-next, per-minute, purchase, early exit и exhaustion;
- после reconnect каждый локальный факт применяется сервером ровно один раз
  либо явно виден как `NEEDS_REVIEW`;
- server-side top-up, сделанный до/during/after offline, один раз увеличивает
  локальный balance после доставки и не стирает pending local debits;
- Grafana позволяет от `operation_id` найти trace, безопасные логи, состояние
  outbox/inbox и подтверждённый analytics/audit факт;
- V1 clients продолжают работать без изменения текущего поведения;
- выполнены отдельные PostgreSQL, Kafka, Compose, browser и native Windows
  проверки из подплана 08; source-level тесты не выдаются за production proof.

## Первые действия после утверждения

1. Выполнить подплан 00 и обновить три product contracts, `CODEX.md`,
   `plans/README.md` и `plans/SUMMARY.md` как V2-решение.
2. Создать versioned V2 schema registry/contract package и test fixtures до
   первого producer/consumer.
3. Поднять изолированный dev Compose-контур Kafka + observability и проверить
   один сквозной `DepositCredit` без переключения реального workstation.
