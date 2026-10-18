# V2.01 — Kafka, versioned events и inbox/outbox

Статус: `in_progress`
Владельцы: `backend/`, `win-client/`, `deploy/`
Зависимости: `V2.00`

## Цель

Определить надёжный событийный транспорт без обещания несуществующего exactly-once.

## Контракт

Общий envelope: `event_id`, `operation_id`, `event_type`, `schema_version`,
`producer_id`, `client_id`, `session_id`, `device_id`, `sequence`, `occurred_at`,
`causation_id`, `correlation_id`, `traceparent`, `payload_hash`, `prev_hash`,
`payload`. Деньги передаются только в minor units.

Topics: `v2.client-events`, `v2.server-events`, `v2.confirmed-domain-events`,
`v2.dead-letter`. Key — `client_id/session_id` для клиентских фактов и
`device_id` для адресных серверных. Один topic на client/device запрещён.

Группы фоновых обработчиков на старте: `client_session_facts` принимает факты
клиентской сессии; `external_payment_events` принимает события внешней оплаты;
`analytics_projection`, `notifications` и `reporting` независимо читают только
подтверждённые доменные факты. Их inbox разделяется `consumer_name`, поэтому
одна доставка нескольким обработчикам не создаёт повторного финансового
действия. Несколько экземпляров одной группы масштабируют partitions, но не
являются разными владельцами бизнес-правил.

Python-транспорт V2 использует FastStream поверх Kafka. FastStream отвечает
только за запуск отправителя и обработчика сообщений и подтверждение доставки: правило сессии,
списание, финансовая операция и запись inbox остаются в application-сценарии.
Подписчик возвращает управление FastStream только после успешной транзакции;
тогда offset можно подтвердить. Ошибка оставляет сообщение для повторной
доставки Kafka.

### `PER_MINUTE_DEBIT` payload (schema version 1)

Клиентский факт поминутного списания содержит только значения из подписанного
snapshot и локального ledger:

- `amount_cents` — обязательная положительная сумма одного списания в копейках;
- `tariff_id` — обязательный идентификатор поминутного тарифа из snapshot;
- `balance_after_cents` — баланс локального ledger после списания; это
  техническое значение не публикуется в подтверждённую аналитику;
- `snapshot_id` и `snapshot_version` добавляются общим envelope payload binding
  и должны совпадать с активным server lease.

Поле `debit_delta_cents` не является полем V2 payload. Оно относится к старому
server-owned meter и не принимается как замена `amount_cents` в V2.
После принятия факта сервер может опубликовать отдельный
`server:reconciliation` `PER_MINUTE_DEBIT` в `v2.confirmed-domain-events`.
Его payload содержит только `amount_cents`, `tariff_id`, ссылку на исходный
event/hash и server confirmation time. Это не команда изменить balance и не
признание новой выручки: analytics учитывает его только как расходование уже
пополненного депозита.

## Задачи

1. [partial: выбран Protobuf `gameclub.events.v2.EventEnvelope`; неизменяемые
   номера полей, reserved range и генерация для Python/C# проверяются тестами.
   Внешняя schema registry и политика публикации версий остаются] Выбрать
   Protobuf/совместимую schema registry policy и написать compatibility tests
   отправителя/обработчика.
2. [partial: доменные типы, обязательные envelope-поля, канонический payload hash,
   W3C trace context, строгий transport parser и in-memory inbox boundary
   реализованы; schema registry, retryability и ownership всех полей остаются]
   Описать event types, required
   fields, retryability, expected server result и ownership каждого поля.
3. [partial: server-side persistent outbox, повторный publisher и FastStream
   adapter реализованы; отдельный V2 Compose-процесс проверен с настоящими
   PostgreSQL и Kafka: доставляет server outbox в Kafka после broker
   confirmation. Отдельный `v2-client-facts` worker принимает клиентские
   факты через PostgreSQL reconciliation и переносит reject в DLQ. Client
   outbox остаётся; Windows transport теперь публикует неизменяемый envelope
   через authenticated backend ingress, а broker credentials остаются на
   сервере]
   Реализовать client/server persistent outbox с состояниями
   `pending/published/acknowledged/failed`; publisher не меняет payload/id.
4. [partial: server-side V2 inbox schema, PostgreSQL adapter и concurrency-safe
   in-memory boundary с unique `(consumer_name, producer_id, operation_id)`
   реализованы; client inbox и сохранение business result в той же транзакции
   остаются] Реализовать client/server inbox с unique `(producer_id,
   operation_id)` и хранением `payload_hash`/ранее подготовленного результата.
5. [partial: `v2-client-facts` подтверждает offset только после PostgreSQL
   transaction accepted/duplicate либо подтверждённого переноса raw envelope
   в закрытый `v2.failed-events`; временная ошибка не скрывается и не
   подтверждает offset. Нужны live Kafka proof, ACL/TLS и durable reject audit]
   Подтверждать Kafka offset только после успешной транзакции inbox + business
   state; неавторизованный/несовместимый event идёт в controlled reject/DLQ
   без утечки PII.
6. [ ] Настроить topic ACL, TLS/SASL, quotas, retention, compaction policy,
   backup и мониторинг lag. Не давать устройству право читать чужие события.
7. [partial: V2-конверт валидирует `traceparent`, а FastStream publisher передаёт
   его в Kafka headers; получение и связывание с OpenTelemetry остаются]
   Передавать W3C trace context в Kafka headers.

## Проверки

- duplicate, out-of-order, payload-hash mismatch, publish-after-crash;
- совместимость старого/нового schema version;
- ACL test: одно устройство не читает/не пишет чужой key;
- Kafka integration в Compose с настоящим server outbox publisher; consumer
  включается только вместе с готовой business transaction inbox+state.

## CP-016 — 2026-09-29: authenticated client-fact ingress

Выполнено:

- backend HTTP получил `/api/v2/events/client-facts`: только device JWT может
  отправить protobuf `EventEnvelope`, а `device_id` и `producer_id` обязаны
  совпадать с subject токена;
- ingress сохраняет исходные protobuf bytes, использует key
  `client_id:session_id` и публикует их в `v2.client-events`; broker запускается
  лениво и не раскрывается Windows-клиенту;
- V2 Windows transport получил `V2HttpClientEventPublisher`, а host включает
  outbox worker только при заданном
  `GAMECLUB_V2_EVENTS_HTTP_ADDRESS`. Без endpoint worker не создаёт ложный
  online transport;
- focused backend contract: 25 тестов; live HTTP smoke после пересборки
  backend: `/health/live` — 200, неавторизованный ingress — 401.

Остаётся:

- client-side native Windows publisher smoke и live доставка до реального
  `ClientInbox` остаются непроверенными на Windows; transport-neutral HTTP
  polling/ack boundary и Linux C# tests уже добавлены;
- Kafka ACL/TLS/SASL, client watermarks и native Windows reconnect/crash proof.

## CP-017 — 2026-09-29: адресная server-event доставка V2

Выполнено:

- server outbox получил терминальный статус `acknowledged`; выдача
  `/api/v2/events/server` фильтрует только `published` события конкретного
  device JWT, а `POST .../acknowledge` повторяем и device-scoped;
- Windows V2 transport получил HTTP consumer и retry worker: protobuf сначала
  проходит `V2ServerEventProcessor`, который атомарно меняет ledger и
  `ClientInbox`, и только затем отправляется ack;
- malformed, mismatched и `rejected` envelopes не подтверждаются и остаются
  доступными для controlled review;
- backend HTTP/in-memory contract: 25 тестов; отдельный V2 C# transport
  contract: 2 теста.

Остаётся:

- native Windows smoke с реальным DPAPI store, reconnect и power-loss;
- Kafka ACL/TLS/SASL и перенос polling на production transport policy, если
  HTTP boundary будет заменён прямым Kafka consumer.

Live test-contour proof:

- ephemeral V2 registration на назначенном `pc-001` создала signed snapshot и
  active lease после добавления test-only server key в ignored `.env`;
- один protobuf fact дважды прошёл authenticated ingress с `202`; Kafka
  consumer создал ровно одну `client_session_facts` inbox-запись;
- reconciliation создал два server-outbox result-факта, а после restart
  `v2-server-outbox` оба перешли в `published`. Повтор не создал второй
  financial/inbox side effect;
- факт без lease был отдельно принят ingress и переведён consumer в controlled
  conflict/DLQ.
