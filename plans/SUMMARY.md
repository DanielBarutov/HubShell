# GameClub / HubShell — сводка проекта

Дата среза: `2026-09-02`<br>
Назначение: быстрый вход в проект без загрузки всего репозитория в контекст.

Этот файл фиксирует фактическое состояние кода, планов и проверок на дату среза.
Он не заменяет исходный код и детальные планы: при изменении контракта сначала
обновляются соответствующий план и проверка, затем эта сводка.

## 1. Как пользоваться сводкой

Порядок чтения для новой задачи:

1. `CODEX.md` — обязательные архитектурные и security-правила проекта.
2. Нужный раздел этой сводки — граница модуля, путь к коду и текущий статус.
3. Детальный владеющий план: [`plans/`](./),
   [`frontend/PLAN.md`](../frontend/PLAN.md) или [`win-client/PLAN.md`](../win-client/PLAN.md).
4. [`VERIFICATION.md`](VERIFICATION.md) — что реально проверено и где находится
   граница доказательства.

Обозначения статуса:

- `реализовано` — код и основной сценарий присутствуют;
- `проверено` — есть соответствующий тест, live smoke или другой указанный чек;
- `source-level` — подтверждено чтением/статическим контрактным чеком, но не
  полноценным запуском целевой платформы;
- `осталось` — следующая работа или ограничение, которое нельзя считать закрытым.

## 2. Назначение и границы продукта

GameClub — операторская система игрового клуба: карта мест и состояние ПК,
клиенты и гости, бронирования, игровые сессии, тарифы, продажи, касса,
аналитика и Windows-клиент рабочего места.

Сейчас это **модульный асинхронный монолит backend**, а не набор отдельных
микросервисов. Границы модулей и публичные application-порты оставлены так,
чтобы выделение сервиса позже было возможным, но преждевременное дробление не
делается.

Основные внешние поверхности:

| Потребитель | Транспорт | Назначение |
| --- | --- | --- |
| Browser/operator UI | HTTP JSON через FastAPI BFF | dashboard, карта, CRM, каталог, продажи, касса, настройки, аналитика |
| Windows client | gRPC + Protobuf | MAC enrollment, device auth, heartbeat, команды, user portal и session gateway |
| Background workers | Dramatiq/Redis | billing reconciliation, reservation no-show, кассовое расписание |
| PostgreSQL/Redis | infrastructure adapters | долговременные факты/настройки и технический кэш/брокер |

Сравнение с обязательными продуктовыми контрактами выполнено и оформлено в
[`plans/29-contract-alignment/PLAN.md`](29-contract-alignment/PLAN.md). Текущий
срез добавляет durable entitlement queue и consumption с окнами/auto-next,
device login-grant, payment parts, guest paid-start prerequisite, entry
decision, one-active-client guard, session snapshot, transfer, offline replay и
portal/WinUI queue activation. Полное контрактное закрытие ещё не достигнуто:
не завершены cross-owner settlement UoW, heartbeat/read-model evidence, часть
operator UI и native Windows evidence. Остаток нарезан на планы
[`30–34`](30-entitlements-meter/PLAN.md), [`35`](35-frontend-contract-consumers/PLAN.md),
[`36`](36-winui-contract-consumers/PLAN.md) и [`37`](37-platform-integration-evidence/PLAN.md).

## 3. Карта репозитория

| Путь | Что находится внутри | Роль |
| --- | --- | --- |
| [`backend/`](../backend/) | Python-приложение, модули, миграции, proto, тесты | API, бизнес-правила и инфраструктура |
| [`backend/src/gameclub_backend/`](../backend/src/gameclub_backend/) | composition root, application, modules, jobs, HTTP/gRPC | реализация backend |
| [`backend/src/gameclub_backend/modules/`](../backend/src/gameclub_backend/modules/) | bounded contexts | домен, use cases, repositories, handlers |
| [`backend/proto/gameclub/v1/`](../backend/proto/gameclub/v1/) | source-of-truth `.proto` | native gRPC-контракты |
| [`backend/alembic/versions/`](../backend/alembic/versions/) | миграции `0001`…`0046` | схема PostgreSQL; текущая голова `20260902_0046` |
| [`backend/tests/`](../backend/tests/) | unit, API, contract, jobs, PostgreSQL checks | автоматические проверки backend |
| [`frontend/`](../frontend/) | React/Vite-приложение и nginx image | операторская web-оболочка |
| [`frontend/src/App.tsx`](../frontend/src/App.tsx) | текущий operator shell и основные flows | UI orchestration; бизнес-расчёты остаются в backend |
| [`win-client/`](../win-client/) | C# solution, WinUI, scripts, tests | клиент игрового ПК |
| [`win-client/src/GameClub.Client/`](../win-client/src/GameClub.Client/) | Domain/Application/Infrastructure/Presentation | Windows implementation |
| [`plans/README.md`](README.md) | общий индекс и зависимости | навигация по планам |
| [`plans/`](./) | детальные планы backend-модулей, Windows-lockdown и связанные контракты | единое хранилище implementation-планов |

Ранее в корне существовали пустые каталоги `plans/00-foundation`…
`plans/06-win-client`, а фактические backend-планы находились в `backend/plans/`.
Теперь детальные планы перенесены в корневой `plans/`; старые пустые каталоги
удалены. `backend/PLAN.md`, `frontend/PLAN.md` и `win-client/PLAN.md` остаются
короткими owner-level входами без копирования детальных implementation-планов.

## 4. Технологический стек

### Backend

- Python `>=3.12,<3.13` и `uv`;
- FastAPI + Uvicorn — HTTP/BFF и health endpoints;
- gRPC `grpcio` + Protocol Buffers — native/internal transport;
- SQLAlchemy async + `asyncpg` — PostgreSQL access;
- Alembic — migrations;
- PostgreSQL `16-alpine` — источник истины бизнес-фактов;
- Redis `7-alpine` — Dramatiq broker, refresh-token storage и технический cache;
- Dramatiq — фоновые/retry-задачи;
- PyJWT — JWT access/refresh/device tokens;
- Pydantic Settings — конфигурация через `GAMECLUB_*`;
- pytest/pytest-asyncio/httpx — тесты; Ruff — lint и форматирование.

Основные ограничения зависимостей и версии находятся в
[`backend/pyproject.toml`](../backend/pyproject.toml). В domain нельзя импортировать
FastAPI, PostgreSQL, Redis, gRPC или Dramatiq; application работает через
`typing.Protocol`, SQL остаётся в infrastructure.

### Frontend

- React `19.1.x` + ReactDOM;
- TypeScript `5.9.x`;
- Vite `7.1.x`;
- Tailwind CSS `4.1.x` через `@tailwindcss/vite`;
- Lucide React `0.468.x`;
- Node `22-alpine` для build image;
- nginx `1.27-alpine` для раздачи и proxy `/api`.

### Windows client

- C# / .NET `8`;
- WinUI 3 через Microsoft Windows App SDK `1.6.240829007`;
- target `net8.0-windows10.0.19041.0`, minimum Windows build `17763`;
- `Grpc.Net.Client 2.66.0`, `Google.Protobuf 3.28.2`, `Grpc.Tools 2.66.0`;
- x86, x64 и ARM64; тестовый проект сейчас рассчитан на x64;
- xUnit и Microsoft.NET.Test.Sdk для unit-тестов.

### Локальная инфраструктура

Корневой [`docker-compose.yml`](../docker-compose.yml) поднимает:

`postgres:5432` → `redis:6379` → `backend-migrate` → `backend-http:8100`,
`backend-grpc:51051`, `worker`, `scheduler` и `frontend:80`. По умолчанию на
host опубликованы frontend `3100`, HTTP `8100`, gRPC `51051`, PostgreSQL `55432`
и Redis `56379`; значения можно переопределить через `.env`.

Frontend image проксирует `/api` в `backend-http`. Windows-клиент подключается к
опубликованному host-порту gRPC, а не к Docker-имени `backend-grpc`.

## 5. Архитектура и потоки

```text
Browser
  -> host :3100 -> frontend/nginx :80
  -> /api -> backend-http/FastAPI :8100
  -> application use case / public module port
  -> PostgreSQL (facts, ledgers, settings) + Redis (technical state/cache)

Windows client
  -> configured host gRPC endpoint :51051
  -> auth metadata / device identity
  -> Workstation, Session, Catalog, Reservation, Billing, Analytics services

scheduler -> Dramatiq/Redis broker -> worker -> reservation/billing/cash jobs
```

Слои backend: `presentation` переводит HTTP/gRPC в команды, `application`
оркестрирует use case и транзакционные границы, `domain` содержит правила,
`infrastructure` содержит PostgreSQL/Redis/JWT/broker adapters.

Ключевые правила:

- frontend не подключается к PostgreSQL, Redis или внутренним gRPC-портам;
- backend-модули не читают сырые таблицы друг друга;
- Redis не является источником истины денег, продаж, сессий или настроек;
- деньги — integer cents, без `float`, с ledger/snapshot и автором операции;
- изменяющие и финансовые операции защищаются idempotency key, audit и явным
  подтверждением;
- на одном ПК допускается только одна active session;
- reservation владеет бронью, Sessions — фактом игры, Catalog — тарифом,
  Billing — charge, Clients — профилем и balance ledger, Cash Shifts — наличным
  ledger, Sales — фактом продажи, Analytics — read-only агрегациями;
- Windows получает только allowlisted команды и темы; произвольные shell/system
  commands запрещены.

## 6. Backend: фактические модули

Код всех модулей находится в
[`backend/src/gameclub_backend/modules/`](../backend/src/gameclub_backend/modules/).
HTTP handlers находятся рядом с модулем в `presentation/http.py`, а сборка
зависимостей выполняется в
[`presentation/http/app.py`](../backend/src/gameclub_backend/presentation/http/app.py).

| Модуль | Что уже есть | Контракт / следующий шаг |
| --- | --- | --- |
| Foundation | async app, config, health, resources, error contract, audit, migrations, generated proto | план помечен `in_progress`; закрыть интеграционные и deployment-вопросы |
| Auth/Security | JWT access/refresh/logout, hash refresh storage, permissions, audit, gRPC auth/TLS policy, dev device bootstrap | production enrollment hardening, token/key rotation, secret storage и сертификаты |
| Workstations | registration по device/MAC, heartbeat, stale/offline state, groups/zones, themes, commands, ACK, expiry, lockdown policy, manager verifier, management CRUD, installation binding | rebind policy/rate limit и native kiosk checks |
| Clients/Guests | client CRUD/search, canonical phone, balance ledger/top-up, discount category/password flow, server portal registration/login, client-scoped JWT и истории; guest profile без balance и guest links | production credential rotation |
| Catalog/Time/Tariffs | categories, products, stock/purchase cost, tariff lifecycle, `block`/`per_minute`, discounts, quote, snapshot, publish/archive | entitlement package consumption, time windows and next-compatible auto-start |
| Reservations | availability preflight, conflict protection, lifecycle, multi-resource create, client/guest, async no-show sweep, HTTP/gRPC/timeline support, server `CheckEntry` with 30-minute lock | WinUI/operator decision consumer and PostgreSQL concurrency matrix |
| Sessions | active/completed lifecycle, start/get/list/stop/interrupt, workstation lock, idempotency, device gateway, tariff quantity, meter integration, entitlement consumption/auto-next, one active client guard, guest payment link, login grant и session snapshot | PostgreSQL package/debit UoW, transfer concurrency и heartbeat evidence |
| Billing | completed-session charge, quote/financial snapshot, atomic balance debit, reconciliation record/retry, metered billing with login-grant subtraction | entitlement-aware billing, guest direct settlement reconciliation; bonus/refund/reserve/external finance — отдельный backlog |
| Reports/Dashboard | read-only current revenue/dashboard data and audit-backed activity | расширенные reports/read models по нагрузке |
| Cash Shifts | open/close, cash ledger, movements, references, approvals, schedules, provider-neutral producer boundary | реальные provider/webhook producers и отдельные finance integrations |
| Product Sales | client/guest sale, stock reservation, price/cost/category snapshots, balance/cash settlement boundary, mixed payment parts, idempotency, HTTP API | atomic cross-part reconciliation, basket/order, returns, bonuses, external acquirer |
| Analytics | read-only overview/client analytics, daily/hourly dynamics, occupancy, zones/PC/tariffs/payment methods, margin, segments, CSV и gRPC read contract | фоновые отчёты через Dramatiq; retention/cohorts, heavy projections, XLSX/PDF |
| Payment Methods | CRUD `/api/v1/payment-methods`, validation, PostgreSQL repository, migration seeds `balance`/`cash`, settings UI | provider activation/settlement integrations добавляются отдельно |

### HTTP BFF surface

Основные prefixes: `/api/v1/auth`, `/workstations`, `/workstation-groups`,
`/clients`, `/guests`, `/catalog`, `/reservations`, `/sessions`, `/billing`,
`/cash-shifts`, `/sales`, `/analytics`, `/payment-methods`, `/audit`.

Для browser это единственная бизнес-точка входа. Защищённые use case повторно
проверяют permissions независимо от видимости кнопок во frontend. В частности,
`settings.manage` нужен для payment methods и настроек групп, `analytics.read` —
для аналитики, а финансовые действия имеют отдельные права/approval boundary.

### gRPC source of truth

В [`backend/proto/gameclub/v1/`](../backend/proto/gameclub/v1/) определены:

`SystemService`, `WorkstationService`, `ClientService`, `ClientPortalService`, `CatalogService`,
`ReservationService`, `SessionService`, `BillingService`, `CashShiftService` и
`AnalyticsService`.

Generated Python находится в `backend/src/gameclub/v1/`, а C# project напрямую
подключает исходные `.proto`. Payment Methods и Product Sales в текущем срезе
имеют HTTP BFF-контракт; отдельного protobuf service для них нет.

### Background jobs

- `jobs/reservations.py` — no-show/sweep;
- `jobs/billing.py` — reconciliation и связанные billing retries;
- `jobs/cash_shifts.py` — расписания кассовых смен;
- `jobs/scheduler.py` — периодическая постановка задач.

Для каждой фоновой операции важны retry, идемпотентность, timeout и понятное
поведение после окончательной ошибки.

## 7. Frontend: операторская оболочка

Основной код сейчас компактно собран вокруг
[`frontend/src/App.tsx`](../frontend/src/App.tsx), с typed API boundary в
[`frontend/src/api.ts`](../frontend/src/api.ts), типами в `types.ts`, adapters/data
для локальных/отладочных сценариев и общими стилями в `index.css`.

Реализованные области:

- тёмный shell с постоянной навигацией, topbar, статусом соединения и доступными
  keyboard/focus/error states;
- dashboard и spatial map как главный workspace;
- карта с фиксированной карточкой места `112x84px`, восемью колонками,
  внутренним scroll-frame и отдельной легендой/панелью; grid не зависит от
  ширины окна так, как прежняя fluid-сетка;
- polling карты и операционных данных каждые 20 секунд; backend snapshot cache
  в Redis — ключ `gameclub:workstations:snapshot:v1`, bounded TTL 20 секунд;
- карта/панель ПК, старт/стоп/interrupt session, выбор клиента или анонимного
  гостя, тариф и товарный checkout;
- сохранение session/product idempotency keys в рамках одной попытки checkout,
  чтобы повторный запрос не создавал вторую сессию или второе списание;
- один retry через refresh token для BFF `401/403`; stale operator permissions
  восстанавливаются dev-refresh до выпуска нового access token;
- CRM, debounce-поиск от 3 символов ника или 4 цифр телефона, canonical phone,
  top-up и просмотр balance ledger;
- каталог: категории, товары, остатки, закупочная цена, draft/publish/archive
  тарифы и discount rules;
- reservations timeline, availability preflight и conflict states;
- кассовые смены, движения, approvals для correction/close discrepancy;
- настройки зон/ПК/тем Windows и CRUD способов оплаты: добавить, изменить,
  деактивировать или удалить;
- analytics overview/client view, KPI, динамика, occupancy, разрезы, margin,
  payment methods и CSV; ошибки показываются явно, без фиктивных чисел.

Бизнес-расчёты и финансовая истина не дублируются в React. Frontend отображает
ответы BFF и управляет operator flow; окончательные проверки конфликтов,
permissions, баланса, stock и идемпотентности выполняются backend.

Отложено на стороне frontend: полноценный realtime transport, расширенная
browser/device matrix, order checkout для смешанных тарифов сверх базовой
entitlement queue, production-scale UI для тяжёлых отчётов и native Windows
flows.

## 8. Windows client

Основной проект: [`win-client/src/GameClub.Client/`](../win-client/src/GameClub.Client/).

| Слой | Содержимое |
| --- | --- |
| `Domain` | connection state, heartbeat, command/session snapshots, lockdown policy |
| `Application` | access-gate и session coordinators, ports для backend/token/executor |
| `Infrastructure` | gRPC adapter, bearer metadata, health, enrollment, token storage, Windows command/power adapters, endpoint policy |
| `Presentation` | WinUI `MainWindow`, `App`, `MainViewModel`, pre-auth fullscreen Locked gate и задел под post-auth widget |
| `tests` | access-gate, session coordinator, password verifier, command executor |

Уже реализовано в source-level срезе:

- borderless fullscreen locked gate; после авторизации compact borderless
  widget, always-on-top и hide/show tray button;
- MAC enrollment, installation identity в AppData, device JWT и bearer metadata;
- server-streaming command receiver с `expires_at`, ACK/NACK, reconnect backoff
  и ограниченным in-memory duplicate guard;
- allowlist `display.lock`, `theme.apply`, `session.start/stop` и структурный
  payload; произвольные shell-команды не принимаются;
- группы передают theme key через heartbeat; неизвестная тема возвращается к
  `standard`;
- locked startup/access-gate, manager maintenance через отдельный credential,
  idle relock, relock при auth 401/403;
- `Ctrl+Alt+P`, session locked/zero-balance handling и controlled restart после
  подтверждённого stop;
- installer/publish/kiosk preview scripts с backup/restore и явным `-Apply`;
  `build-portable-exe.ps1` собирает single-file self-contained EXE с заранее
  зашитыми non-secret HTTPS endpoint metadata для передачи на клиентский ПК.
- server-backed register/login/profile/history screen показывает баланс,
  операции, списания времени, товары, тарифы/сессии и доступное время; portal
  snapshot теперь передаёт ordered package queue и explicit activation RPC/UI.

Windows-клиент не хранит баланс и не выполняет финансовые операции. Сервер
остаётся источником истины сессии и billing.

Не закрыто: cross-owner settlement/reconciliation UoW, heartbeat/read-model
evidence, production hardening enrollment/rebind/token rotation, native
`dotnet restore/build/test`, запуск под обычным пользователем, реальный
reconnect/theme/restart smoke и Assigned Access/Shell Launcher с ограничением
Explorer/Alt+Tab/других приложений. App-level lock не считается заменой Windows
security boundary. Детали — в
[`win-client/docs/SUPPORT-MATRIX.md`](../win-client/docs/SUPPORT-MATRIX.md) и
[`plans/29-contract-alignment/PLAN.md`](29-contract-alignment/PLAN.md).

## 9. История сделанных срезов

Последовательность работы, зафиксированная планами и кодом:

1. Foundation: async backend, config, health, error/status conventions,
   repositories, migrations, generated protobuf и Compose.
2. Auth/Security: JWT access/refresh/logout, permissions, audit, gRPC auth/TLS
   policy и dev bootstrap для device.
3. Workstations: регистрация/heartbeat, состояние ПК, команды, группы, темы,
   management и lockdown policy.
4. Clients/Catalog/Reservations: профили, guests, canonical phone, ledger,
   товары/категории/остатки, тарифы/discounts, quote, бронирования и timeline.
5. Sessions/Billing: фактический lifecycle `active -> completed`, locks,
   idempotency, interrupt, charge snapshot, debit и reconciliation.
6. Cash Shifts: отдельный наличный ledger, approvals, schedules и producer
   boundary без смешивания с клиентским balance.
7. Operator redesign: единый dark shell, spatial map, sliding panels, checkout,
   CRM, catalog, cash desk и live BFF flows.
8. Product Sales/Analytics: товарные продажи со stock/settlement snapshots и
   read-only analytics по завершённым sessions, charges и sales.
9. Live metered billing: per-minute delta, grace minutes, insufficient-balance
   stop и sequential block quantity.
10. Последний прикладной срез по запросам пользователя:
    - исправлены fixed-size map cards, отдельный scroll-frame и polling 20 s;
    - добавлен Redis snapshot cache с TTL 20 s;
    - checkout защищён от повторного session/product submit;
    - stale permissions при BFF `403` обновляются через refresh;
    - в Settings добавлен CRUD payment methods;
    - analytics BFF/live flow проверен после исправления authorization path.
11. Deployment-подготовка Windows-клиента:
    - внешние host-порты Compose разделены с системными default-портами;
    - добавлен unpackaged single-file self-contained publish для одного EXE;
    - endpoint defaults клиента синхронизированы с новым HTTP/gRPC-профилем.
12. Автоматическое подключение и user portal:
    - MAC enrollment с installation binding, `pending/approved/disabled` и
      миграциями `0032/0033`;
    - `ClientPortalService` в gRPC с device-scoped registration/login и
      client-scoped JWT, histories и available time;
    - WinUI pre-auth fullscreen gate и server-backed login/register/profile/history;
    - portable publish получил baked HTTPS endpoint parameters и не требует
      env/bootstrap/token/PIN setup на игровом ПК.
    - enrollment получает понятный rejected-state при конфликте installation id;
      уже привязанное место нельзя случайно изменить на другой MAC без отдельной
      rebind-операции.
    - добавлен in-process gRPC smoke для portal registration/snapshot с проверкой
      client/device scope.

Детальные задачи и решения: [`plans/README.md`](README.md) и таблица
проверок ниже. В README есть небольшое расхождение: Product Sales уже имеет
`plans/10-product-sales/PLAN.md` со статусом `done`; индекс обновлён и больше
не использует старый путь `backend/plans/`. Для фактического доказательства
приоритет у кода, детального плана и `VERIFICATION.md`.

## 10. Чекапы и границы доказательства

### Уже выполнено на текущем checkout

| Чекап | Результат | Что именно доказывает |
| --- | --- | --- |
| `cd backend && uv run pytest -q` | `128 passed, 13 skipped` без DSN; `141 passed` с dev PostgreSQL/Redis DSN (повторено 2026-09-02) | unit/API/contract/jobs и memory-backed + текущие PostgreSQL flows, включая package windows/auto-next, locked delta, snapshot, transfer, offline replay, payment review, entry decision, guest paid-start и login grant |
| `cd backend && uv run ruff check .` | успешно (повторено 2026-09-02) | lint backend |
| `cd backend && uv run ruff format --check <затронутые Python-файлы>` | успешно | форматирование текущего среза; полный checkout дополнительно содержит 2 старых неформатированных файла |
| `cd frontend && npm run typecheck` | успешно (повторено 2026-09-02) | TypeScript compile/type boundary |
| `cd frontend && npm run build` | успешно (повторено 2026-09-02) | production Vite build |
| `docker compose config --quiet` | успешно | Compose syntax/config |
| `docker compose up -d --build` | успешно в текущем прогоне 2026-09-02 | full local stack собран и поднят; PostgreSQL/Redis healthy, migrations применены до `20260902_0046`, HTTP/frontend smoke прошёл; native Windows client в compose не входит |
| live `POST /api/v1/auth/device-enrollment` без назначенного MAC | `202 pending` | опубликованный BFF enrollment route и безопасный ответ без device/operator token |
| Live HTTP smoke | успешно | fresh operator token, `/auth/me`, payment methods, analytics 200, sales 200, auth-aware error path |
| Redis cache smoke | TTL около `16 s` сразу после чтения | cache key created with bounded 20 s TTL; Redis не заменяет DB |
| Playwright headed smoke | успешно | login, map fixed card/scroll-frame, checkout retry behavior, payment CRUD, analytics without 403 |
| Product/catalog smoke | `PUT` существующего товара → `200` | regression after backend rebuild |

### Чеки, которые ещё нужны

| Направление | Почему не закрыто |
| --- | --- |
| PostgreSQL integration/concurrency | 12 тестов пропускаются без `GAMECLUB_TEST_POSTGRES_DSN` и Redis DSN; memory tests не доказывают database locks/constraints |
| Windows native | Linux не запускает WinUI 3 `XamlCompiler.exe`; source-level contract не заменяет build/runtime; `dotnet` отсутствует в PATH |
| Kiosk security | Assigned Access/Shell Launcher, обычный пользователь, edition, Explorer/Alt+Tab, recovery и restore требуют целевой Windows-машины |
| Browser matrix/realtime | сейчас подтверждён локальный headed smoke; полноценный набор браузеров и realtime transport не выполнялись |
| Production security | нужны real secret storage, enrollment rate-limit/rebind, TLS/mTLS certificates, rotation/revocation, backups и deployment policy |
| Heavy analytics | текущий overview/client/CSV синхронный read model; фоновые отчёты с retry/status/file ещё не сделаны |

## 11. Следующие задачи

### P0 — доказать текущий MVP

0. Дочерние планы [`30`](30-entitlements-meter/PLAN.md)–[`36`](36-winui-contract-consumers/PLAN.md)
   реализованы на source/unit-уровне и остаются в `in_progress` до закрытия
   своих integration/native критериев. Следующий обязательный шаг —
   [`37`](37-platform-integration-evidence/PLAN.md): PostgreSQL/Compose,
   headed browser, Windows native/kiosk и security evidence.

1. Запустить backend suite с реальными `GAMECLUB_TEST_POSTGRES_DSN` и
   `GAMECLUB_TEST_REDIS_URL`, затем закрыть или документировать каждый skipped
   integration/concurrency test.
2. На Windows выполнить:

   ```powershell
   cd win-client
   .\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
   ```

   После этого вручную проверить access-gate, обычного пользователя,
   reconnect, theme, session stop/restart и отсутствие секретов в файлах/логах.
   Для передачи на клиентский ПК собрать portable-файл:

   ```powershell
   .\scripts\build-portable-exe.ps1 -Architecture x64 -Configuration Release
   ```
3. Проверить основной browser flow в поддерживаемых браузерах и определить
   порог нагрузки/частоту polling; при необходимости перейти от polling к
   согласованному realtime transport.
4. Реализовать плановую задачу Analytics по background reports через Dramatiq:
   status, retry, хранение результата и безопасная выдача файла.

### P1 — production readiness

- hardening per-device enrollment: rebind policy, rate limit, pairing, rotation;
- access/refresh key rotation, revocation policy и полноценный secret storage;
- production HTTPS/gRPC TLS, при необходимости mTLS, certificate issuance/rotation;
- Windows Credential Manager hardening и kiosk provisioning Assigned Access/
  Shell Launcher с обратимой политикой;
- backup/restore, deployment/observability policy и load checks.

### Product backlog

- внешние payment provider/webhook integrations;
- basket/returns и order-семантика сверх entitlement queue из P0-плана;
- bonus spending, reservations of funds, refunds и guest cashier flow;
- retention/cohort/LTV и тяжёлые read projections, XLSX/PDF reports;
- notifications, employees/roles, расширенный audit;
- только после подтверждённой нагрузки — выделение модулей в deployment units.

## 12. Повторяемые команды

Из корня:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend-http
```

Backend:

```bash
cd backend
uv sync
uv run python scripts/generate_proto.py
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
uv run ruff format --check src tests alembic/versions/20260830_0031_payment_methods.py
```

Интеграционные проверки требуют DSN:

```bash
cd backend
GAMECLUB_TEST_POSTGRES_DSN=... GAMECLUB_TEST_REDIS_URL=... uv run pytest -q
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run build
```

Windows — только PowerShell на Windows:

```powershell
cd win-client
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
dotnet test GameClub.Client.sln --configuration Debug -p:Platform=x64
```

Для solution используется `-p:Platform=x64`; `--arch` для solution не является
эквивалентом и приводит к ошибке SDK `NETSDK1134`.

## 13. Правила обновления Summary

После каждого substantive-среза обновлять минимум:

1. фактический статус нужного детального плана;
2. соответствующую строку/раздел `VERIFICATION.md` с границей доказательства;
3. этот файл: историю, изменённые контракты, новые пути и открытые задачи;
4. migration head/protobuf/API surface, если они изменились;
5. список чекапов — отдельно для unit, PostgreSQL/Redis integration, Compose,
   browser visual/live и Windows native.

Не считать задачу закрытой только потому, что она есть в плане или UI-кнопка
видна: нужен проверяемый backend use case и подходящий чек уровня требования.
