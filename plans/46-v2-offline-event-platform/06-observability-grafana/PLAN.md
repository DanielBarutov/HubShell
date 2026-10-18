# V2.06 — Grafana, Loki, Tempo, Prometheus и alerting

Статус: `in_progress`
Владельцы: `backend/`, `win-client/`, `deploy/`
Зависимости: `V2.01`, `V2.02`, `V2.03`, `V2.04`

## Цель

Дать оператору и разработчику единую Grafana-точку расследования без хранения
секретов/PII в технической телеметрии.

## Задачи

1. [~] Добавить OpenTelemetry SDK в Windows client и backend: spans для local
   commit, outbox publish, Kafka consume, ServerInbox, financial transaction,
   analytics consume и payment result.
2. [~] Поднять OpenTelemetry Collector с redaction/enrichment policy; trace
   context передавать в Kafka headers.
3. [~] Развернуть Prometheus для приложений, Kafka, PostgreSQL и host metrics;
   Loki для structured logs; Tempo для traces; Grafana и Grafana Alerting.
4. [~] Запретить password/token/payment details/raw PII в logs/traces. Не
   использовать `client_id`, `session_id`, `operation_id` как Prometheus labels
   высокой кардинальности; для drill-down использовать trace/log fields.
5. [ ] Собрать landing dashboard: здоровье сервиса, активные/offline PCs,
   Kafka lag, oldest outbox age, inbox conflicts, reconciliation, payment and
   debit errors, DB/Kafka health.
6. [ ] Собрать linked панели: финансы/read-only analytics, session/source time,
   client sync, errors, traces. Из метрики должен открываться trace, затем
   безопасные логи и audit reference по `operation_id`.
7. [ ] Настроить alerts, routes, deduplication и runbooks для outbox SLO,
   consumer lag, no heartbeat, NEEDS_REVIEW spike, payment/debit failures,
   Kafka/PostgreSQL unavailable.
8. [ ] Задать retention, backup, RBAC и доступ к финансовым панелям/read-only
   datasource отдельно от обычного просмотра технических логов.

## Проверки

- искусственный duplicate, broker outage и payment retry видны во всех трёх
  сигналах: metric, trace и log;
- PII/secret scan telemetry payloads;
- alert delivery test и доказательство восстановления после outage.

## CP-016 — 2026-09-27: source-level контур наблюдаемости

Выполнено:

- в FastStream-процессе `v2-server-outbox` добавлены opt-in OpenTelemetry и
  Prometheus middleware; технические метрики намеренно не получают labels с
  идентификаторами клиента, сессии или операции;
- для Compose profile `v2` добавлены конфигурации и сервисы OpenTelemetry
  Collector, Prometheus, Loki, Tempo, Alloy и Grafana, а Grafana получает
  подготовленные datasource и стартовую панель V2;
- сбор docker-логов проходит через локальное правило маскирования типовых
  `password`/`token`/`authorization` значений до Loki;
- `docker compose config`, 42 backend contract-теста, Ruff и проверка формата
  diff прошли.

Осталось:

- образы наблюдаемости не были подняты: Docker daemon не может обратиться к
  Docker Registry по IPv6 (`network is unreachable`). Поэтому нет живого
  доказательства Grafana, Loki, Tempo, Prometheus, трассы или log redaction;
- не добавлены exporter-ы Kafka/PostgreSQL/host, alert rules, notification
  routes, RBAC, backup и Windows-клиентская instrumentation;
- сначала нужно устранить сетевую доступность Docker Registry и только затем
  выполнять e2e: outbox publish → metric/log/trace → Grafana drill-down.

## CP-031 — 2026-09-28: живой Compose-контур наблюдаемости

Выполнено:

- Compose-сервисы OpenTelemetry Collector, Prometheus, Loki, Tempo, Alloy и
  Grafana запущены. Для работоспособности исправлены: том Tempo теперь хранит
  данные в `/var/tempo`, OTLP-приёмники Collector и Tempo доступны внутри
  сети Compose, в Loki задано filesystem-хранилище delete requests, а Alloy
  получает Docker-цели через `discovery.docker`;
- Grafana отвечает на health-check, имеет datasource Prometheus/Loki/Tempo и
  панели `GameClub V2` и `GameClub V2 Event Platform`; Prometheus подтверждает
  состояние `up` у `v2-client-facts`;
- реальный факт Kafka дал два спана в Collector, одну трассу в Tempo и логи
  `Received`/`Processed` второго V2 worker в Loki.
- dashboard `GameClub — проблемные логи сервисов` содержит отдельные таблицы
  warning/error, HTTP 4xx и HTTP 5xx прикладных контейнеров `gameshell-*`,
  исключая Alloy, Prometheus, Grafana, Loki, Tempo и Pyroscope; уровень и
  HTTP-статус фильтруются в LogQL, поэтому видны и накопленные логи без нового
  label в Alloy.

Осталось:

- не выполнены secret-redaction test, metric→trace→log→audit drill-down по
  `operation_id`, Kafka/PostgreSQL/host exporter-ы, alert rules/routes, RBAC,
  backup и Windows instrumentation;
- production-параметры retention/доступа и проверка восстановления после
  outage остаются отдельной эксплуатационной работой.
