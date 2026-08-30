# GameClub backend

Асинхронный backend модульного монолита. Сейчас доступны базовые вертикальные
срезы Workstations, Clients/Guests, Catalog, Reservations, Sessions и Billing, а foundation проверяет
границы слоёв, конфигурацию, health endpoints, gRPC и подключения к инфраструктуре.

## Локальный запуск

Требуется `uv`. Для PostgreSQL и Redis используется Docker Compose.

Для запуска всего dev-стека из корня проекта (PostgreSQL, Redis, миграции,
HTTP, gRPC, worker, scheduler и frontend) используйте [`DOCKER.md`](../DOCKER.md).
Compose в этой папке оставлен как infra-only вариант для backend-разработки.

```text
cp .env.example .env
export GAMECLUB_DB_PASSWORD='set-a-local-password'
docker compose up -d
uv sync
uv run python scripts/generate_proto.py
uv run alembic upgrade head
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

При заданном `GAMECLUB_POSTGRES_DSN` приложение выбирает PostgreSQL-репозитории;
без него используется in-memory адаптер для быстрых unit/API тестов.

HTTP-приложение запускается командой `make run-http` и предоставляет:

- `GET /health/live` — процесс запущен;
- `GET /health/ready` — проверка настроенных PostgreSQL/Redis dependencies.

В dev-режиме при заданных `GAMECLUB_DEV_OPERATOR_USERNAME` и
`GAMECLUB_DEV_OPERATOR_PASSWORD` endpoint `POST /api/v1/auth/token` выдаёт
короткоживущий access JWT и одноразовый refresh token. Refresh токены ротируются
через `POST /api/v1/auth/refresh`, а logout отзывает текущий refresh token. При
заданном `GAMECLUB_REDIS_URL` они хранятся в Redis; без Redis используется
memory-адаптер только для локальной разработки.

При заданном `GAMECLUB_DEVICE_BOOTSTRAP_TOKEN` endpoint
`POST /api/v1/auth/device-token` выдаёт device JWT только с permission
`workstations.connect`. Это временный bootstrap-контур для интеграции агента;
для production нужны per-device enrollment, защищённое локальное хранилище,
rotation/revocation токенов и TLS.

Операторские изменения для ПК доступны через защищённый HTTP BFF, включая
`POST /api/v1/workstations/{workstation_id}/commands` с заголовком
`Idempotency-Key`. Разрешены только типизированные безопасные команды из
application-слоя; произвольные системные команды не принимаются. Статус команды
читается через `GET /api/v1/workstations/{workstation_id}/commands/{command_id}`;
queued-команды имеют TTL `GAMECLUB_WORKSTATION_COMMAND_TTL_SECONDS` и после него
переходят в `expired` без доставки.
Группы ПК и их темы настраиваются через защищённые
`GET /api/v1/workstation-groups` и `PUT /api/v1/workstation-groups/{group_id}`.
Поддерживаются темы `standard`, `vip`, `neon`, `minimal`; выбранная тема входит
в ответ workstation heartbeat и применяется Windows-клиентом после подключения.

Каталог доступен через защищённые `GET /api/v1/catalog/tariffs` и
`GET /api/v1/catalog/products`; для клиентов также есть единый
`GET /api/v1/catalog/snapshot` с опубликованными тарифами и активными discount rules.
Тарифы и quote рассчитываются в application-слое.
Тарифы имеют стабильный ключ, атомарную версию и lifecycle `draft/published/archived`,
а расширяемые discount rules применяются по категории клиента, приоритету и периоду.
Бронирование поддерживает защищённые create/list/get/cancel и базовые переходы
`activate`, `complete`, `no-show`; конфликт ресурсов проверяется в application-слое
и повторно внутри PostgreSQL-транзакции. No-show разрешается после grace period из
`GAMECLUB_RESERVATION_GRACE_PERIOD_MINUTES` (по умолчанию 15 минут после начала).
История операций баланса доступна оператору через защищённый
`GET /api/v1/clients/{client_id}/balance-operations?limit=50`; endpoint возвращает
тип, сумму в копейках, бонус, причину, автора, idempotency key и дату в порядке от
новых операций к старым. Для нативных клиентов тот же read-only контракт доступен
через `ClientService.ListBalanceOperations`.
Профили гостей не имеют баланса и доступны через защищённые
`GET/POST /api/v1/guests`, `GET /api/v1/guests/{guest_id}` и
`GET /api/v1/guests/search?q=...&field=nickname|phone`. `guest_id` можно назначить
на бронь или игровую сессию; backend проверяет профиль и сохраняет его nickname
как display snapshot, а разовый `guest_name` остаётся legacy-режимом.
Игровые сессии доступны через защищённый `POST /api/v1/sessions` с
`Idempotency-Key`, `GET /api/v1/sessions` и `POST /api/v1/sessions/{session_id}/stop`.
Для досрочного завершения оператор использует отдельный
`POST /api/v1/sessions/{session_id}/interrupt` с `Idempotency-Key` и причиной;
повторное завершение безопасно, а само действие не изменяет баланс.
Они фиксируют фактический `active`/`completed` lifecycle и сами не изменяют баланс;
PostgreSQL запрещает две активные сессии на одном ПК в конкурентных запросах. Для
завершённой сессии с клиентским профилем
доступен защищённый `POST /api/v1/billing/sessions/{session_id}/charge` с
`Idempotency-Key` и чтением через `GET /api/v1/billing/sessions/{session_id}/charge`.
Billing списывает только `balance_cents`, сохраняет tariff/discount snapshot и не
создаёт второй debit при повторной доставке; `balance_bonus`, внешние платежи и
связь с кассовым ledger остаются отдельными финансовыми срезами. Перед debit создаётся durable
reconciliation record; при сбое после debit запись получает retryable-состояние,
а worker повторяет charge с тем же ledger key. Оператор может посмотреть такие
записи через `GET /api/v1/billing/reconciliation`. Дизайн следующего финансового
среза для бонусов, кассы, возвратов и внешних платежей описан в
[`plans/07-billing/FUTURE-FINANCE.md`](../plans/07-billing/FUTURE-FINANCE.md).
Read-only выручка за период доступна через защищённый
`GET /api/v1/billing/revenue?start_at=...&end_at=...`; она агрегирует только
сохранённые `SessionCharge` в полуоткрытом UTC-интервале и возвращает сумму в
копейках и количество списаний; read-only доступ защищён permission
`dashboard.read`. Для gRPC-клиентов предусмотрен
`BillingService.GetRevenue`.
Расширенная read-only аналитика клуба и клиента доступна через
`GET /api/v1/analytics/overview` и `GET /api/v1/analytics/clients/{client_id}`.
Для native-клиентов зафиксирован versioned gRPC-контракт
`AnalyticsService.GetOverview`/`GetClient`; оба метода требуют `analytics.read`,
принимают aware UTC-период и возвращают выручку, загрузку, временные ряды,
разрезы зон/ПК/тарифов/оплат и клиентские показатели без доступа к внутренним
таблицам.
Кассовые смены реализованы отдельным модулем и не изменяют клиентский баланс:
`GET /api/v1/cash-shifts` показывает смены, `POST /api/v1/cash-shifts` открывает
смену, `POST /api/v1/cash-shifts/{shift_id}/movements` записывает `cash_in`,
`cash_out` или signed `correction`, а
`POST /api/v1/cash-shifts/{shift_id}/close` закрывает её по фактическому остатку.
Изменяющие запросы требуют `cashier.manage` и `Idempotency-Key`, чтение —
`cashier.read`; signed-корректировка дополнительно требует `cashier.correct`.
Корректировка и закрытие с расхождением требуют отдельного supervisor approval,
который создаётся через `POST /api/v1/cash-shifts/{shift_id}/approvals` с правом
`cashier.supervise` и привязывается к target idempotency key.
Денежные значения передаются в integer cents, а PostgreSQL
защищает одну открытую смену на register. Подтверждённые Billing settlements и
внешние payment captures входят через application producers с immutable reference;
конкретный provider остаётся заменяемым.
Общий контракт ошибок, request ID, дедлайнов и отмены описан в
[`docs/ERRORS.md`](docs/ERRORS.md).

Последние административные операции доступны оператору через защищённый
`GET /api/v1/audit/events?limit=20` с permission `audit.read`. Read-модель не
содержит payload запросов и персональные данные, которых нет в audit event.

gRPC-сервер запускается командой `make run-grpc` на `127.0.0.1:50051`. В dev
insecure transport разрешён только для локальной разработки; в окружении `prod`
или `production` сервер требует `GAMECLUB_GRPC_TLS_CERT_FILE` и
`GAMECLUB_GRPC_TLS_KEY_FILE`. mTLS можно включить через
`GAMECLUB_GRPC_TLS_CLIENT_CA_FILE` и
`GAMECLUB_GRPC_TLS_REQUIRE_CLIENT_CERTIFICATE=true`. Клиент использует `https://`
адрес для TLS-соединения. Источником истины для health и бизнес-контрактов являются
versioned файлы в `proto/gameclub/v1/`; Python-типы генерируются командой `make proto`.

Threat model, JWT policy, secret handling и границы доверия описаны в
[`plans/04-auth-security/THREAT-MODEL.md`](../plans/04-auth-security/THREAT-MODEL.md).

Фоновый worker запускается командой `make worker`. Сейчас он предоставляет
идемпотентные async-срезы массового no-show и billing reconciliation для
PostgreSQL: брони перечитываются
под блокировкой строки перед переходом состояния, поэтому повторный запуск или
гонка с активацией не перезаписывают актуальный статус, а charge retry использует
session-derived ledger key. Для worker нужны
`GAMECLUB_POSTGRES_DSN` и `GAMECLUB_REDIS_URL`.
Периодическая постановка sweep-задач запускается отдельно командой
`make reservation-scheduler`; интервал задаётся через
`GAMECLUB_RESERVATION_SWEEP_INTERVAL_SECONDS`.

## Структура

```text
src/gameclub_backend/
  presentation/    # HTTP/gRPC transport
  application/     # use cases and ports
  domain/          # общие доменные соглашения
  repository/      # общие repository boundaries
  infrastructure/  # PostgreSQL/Redis adapters and runtime resources
  modules/         # bounded contexts по слоям
proto/             # source-of-truth protobuf contracts
tests/             # foundation tests
```

Секреты в `.env` не коммитятся. `.env.example` содержит только примерные локальные значения.
