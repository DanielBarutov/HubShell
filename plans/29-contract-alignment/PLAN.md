# План 29 — выравнивание реализации с продуктовыми контрактами

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `frontend/`, `win-client/`
Зависимости: `00-foundation`, `01-workstations`, `02-clients-guests`,
`03-catalog-time-tariffs`, `04-auth-security`, `05-reservations`, `06-sessions`,
`07-billing`, `09-cash-shifts`, `10-product-sales`, `12-live-metered-billing`,
`13-payment-methods`, `22-windows-lockdown`, `23-device-enrollment`

## Цель

Закрыть подтверждённые разрывы между тремя `PRODUCT-CONTRACT.md`,
`CODEX.md` и фактическим кодом. План является сквозным: backend остаётся
источником истины, BFF и protobuf передают его решения, frontend и WinUI только
показывают DTO и вызывают явные команды.

Зафиксированное решение по окну WinUI: до server-backed авторизации действует
полноэкранный borderless access-gate; после авторизации клиент не заменяет
Windows shell, переходит к обычному Windows Desktop и показывает компактный
borderless-виджет сессии с возможностью скрытия в трей. App-level gate не
подменяет Assigned Access/Shell Launcher.

## Baseline аудита до текущего среза

### Уже имеется

- модульные async backend-контуры, integer money, client balance ledger и
  idempotency для базовых финансовых операций;
- отдельный persisted guest без клиентского баланса и ссылки guest в бронях и
  сессиях;
- catalog с тарифами `block`/`per_minute`, ценовыми snapshot-ами, остатками и
  текущим `free_minutes` параметром тарифа;
- reservations с конфликтами, client/guest identity и no-show sweep;
- lifecycle сессии, live metered billing для client balance и operator map;
- product sales с одним методом `balance` или `cash`, cash shifts и CRUD
  payment methods;
- enrollment по MAC с installation binding, device JWT, heartbeat, command ACK,
  access-gate и личный кабинет пользователя;
- frontend map/checkout/CRM/analytics/settings и WinUI heartbeat, reconnect,
  server commands и source-level publish/deployment scripts.

### Не имеется или имеется только частично

| Область контракта | Фактическое состояние | Целевой результат |
| --- | --- | --- |
| Пакеты и права времени | Durable queue, activation, window-aware consumption и auto-next добавлены; PostgreSQL concurrency/UoW ещё не доказаны | Очередь купленных пакетов в PostgreSQL, совместимость по зоне/окну, активация и consumption state с integration evidence |
| Login grant | Device-start получает отдельный 5-minute grant; portal-login event и durable cross-transport idempotency требуют уточнения | Однократный login grant с audit/idempotency и последующим per-minute charge |
| Session invariants | Application guard и PostgreSQL partial unique index добавлены; текущий DSN suite прошёл | Транзакционная уникальность и объяснимая ошибка; специализированные новые concurrency cases остаются в backlog |
| Гость и деньги | Guest fixed tariff требует подтверждённого direct payment и сохраняет payment link; guest metered billing отложен | Server decision после подтверждённой direct payment, без guest balance |
| Payment parts | Provider-neutral parts, mixed `balance`/`cash`, immutable snapshots и `needs_review` boundary добавлены | Общая cross-owner reconciliation/worker без повторного cash side effect |
| Reservation access | `CheckEntry` с 30-minute protection, named/guest matching и machine-readable reason добавлен в session start/HTTP/gRPC | Единый consumer в frontend/WinUI и heartbeat |
| Transfer | API/proto/use case, PostgreSQL owner transaction и client confirmations добавлены; concurrency/native ACK не доказаны | Явное подтверждение на новом ПК и атомарное сохранение session/meter/queue с integration evidence |
| Snapshot/offline | Snapshot/entry HTTP+gRPC, DPAPI journal и backend replay добавлены; heartbeat/read-model/native flow не закрыты | Snapshot, durable journal, sequence/idempotency и batch replay после reconnect |
| Operator web | Карта/panel получают queue/snapshot/entry decision, mixed payment, guest paid-start, transfer и stale/offline fields; headed matrix не закрыта | Карта и panels отражают только server DTO/decision с browser evidence |
| WinUI post-login | Post-auth desktop/widget/tray, package queue/activation, snapshot gateway, transfer и DPAPI journal добавлены на source-level; entry/native smoke не доказаны | Dynamic presentation, штатный widget/tray, server booking/snapshot/activation с native evidence |
| Native security | Native Windows build, обычный пользователь и kiosk не доказаны | Windows smoke и отдельный reversible Assigned Access/Shell Launcher rollout |

## Фактический прогресс текущего среза

Реализовано и проверено на memory/API/gRPC границе:

- миграции `20260902_0034`–`20260902_0046`: уникальность активной сессии
  клиента, `payment_parts`, durable `client_entitlements`, time-window
  snapshots, guest payment, login grant, transfer offers и offline operations;
- `PaymentPart` сохраняется в balance operation и product sale; backend
  проводит `balance`/`cash` mixed sale с точной суммой, idempotency и cash-shift
  boundary;
- guest fixed-price tariff проходит только через подтверждённую direct payment,
  после чего session хранит ссылку на payment;
- `CheckEntry` с 30-минутным защитным окном подключён к session start и
  опубликован в HTTP/gRPC;
- device-start получает 5 минут login grant, а metered billing вычитает его
  отдельно от `free_minutes`; одна активная client session защищена use-case
  guard и PostgreSQL partial unique index;
- client portal snapshot теперь содержит ordered entitlement queue, а WinUI
  имеет explicit activation RPC/UI; frontend получил typed BFF methods и mixed
  payment controls.
- session snapshot/entry HTTP+gRPC, PostgreSQL transfer owner transaction,
  backend offline replay с idempotency/checksum и frontend/WinUI consumers
  добавлены на source/unit-уровне; Compose migration/HTTP/gRPC/headed smoke
  подтверждены отдельно в `plans/VERIFICATION.md`.

Остаётся принципиально незакрытым: общий settlement/reconciliation UoW между
ledger owners, portal-login grant event, heartbeat/read-model fixtures,
PostgreSQL concurrency/fault injection, headed browser evidence и native Windows
build/runtime/kiosk/security evidence.

### Матрица результата текущего среза

| Требование контракта | Что есть сейчас | Доказательство | Следующий плановый шаг |
| --- | --- | --- | --- |
| Payment parts и mixed settlement | DTO, валидация суммы, balance/cash для product sale, cash-shift boundary и `needs_review` | unit/API tests, `128 passed`; DSN suite `141 passed` | атомарная cross-part reconciliation/worker и настройки payment methods |
| Guest fixed tariff | direct payment с idempotency и ссылка в session start | unit/API tests | reconciliation payment record и cash movement |
| Entry decision | backend `CheckEntry`, HTTP/gRPC и вызов из session start | unit/API/contract tests | одинаковый consumer в frontend/WinUI и heartbeat |
| One active client session | application guard и PostgreSQL partial unique index | unit/concurrency test source; DB test skipped без DSN | реальный PostgreSQL concurrency run |
| Entitlement queue | durable queue, purchase, ordering, explicit activation, window-aware session consumption и auto-next | unit и in-process gRPC smoke | PostgreSQL concurrency и общий debit/package transaction |
| Login grant | поле session, отдельное вычитание в meter, device-start grant | unit tests | grant на успешный portal login с durable audit/idempotency |
| Transfer/offline/snapshot | HTTP/gRPC snapshot/transfer/replay, WinUI gateway/journal и frontend consumers добавлены | source/unit tests | PostgreSQL/heartbeat/native integration evidence |

## Декомпозиция следующего среза

Чтобы не смешивать разные транзакционные и платформенные границы, остаток
разделён на дочерние планы. Реализация идёт в указанном порядке, но frontend и
WinUI подключаются только после публикации DTO владельцем backend:

1. [`30-entitlements-meter`](../30-entitlements-meter/PLAN.md) — state machine
   пакетов, consumption, time windows, auto-next и portal-login grant.
2. [`31-settlement-reconciliation`](../31-settlement-reconciliation/PLAN.md) —
   атомарные payment parts, cash/balance boundary и recovery.
3. [`32-session-snapshot-entry`](../32-session-snapshot-entry/PLAN.md) — единые
   `EntryDecision`, `SessionSnapshot`, heartbeat и read model.
4. [`33-session-transfer`](../33-session-transfer/PLAN.md) — offer/confirm,
   atomic session move, zone rules и old-PC restart.
5. [`34-durable-offline`](../34-durable-offline/PLAN.md) — постоянный journal,
   idempotent batch replay и offline safety.
6. [`35-frontend-contract-consumers`](../35-frontend-contract-consumers/PLAN.md) —
   карта, queue, guest decision, settlement states, transfer и stale PC.
7. [`36-winui-contract-consumers`](../36-winui-contract-consumers/PLAN.md) —
   snapshot, package lifecycle, transfer, offline и reconnect consumers.
8. [`37-platform-integration-evidence`](../37-platform-integration-evidence/PLAN.md) —
   PostgreSQL/Compose/browser/native Windows/kiosk/security evidence.

Критическая цепочка: `30 → 32 → 33/34 → 35/36 → 37`. План 31 может идти
параллельно планам 30 и 32, но его DTO и settlement states должны быть готовы
до завершения operator checkout.

## Архитектурные решения и ограничения

1. Все новые money, package, session и entry state хранятся в PostgreSQL и
   изменяются транзакционно. Redis остаётся cache/transport, не ledger.
2. Публичные DTO сначала фиксируются в versioned protobuf/BFF-контрактах. В
   UI и WinUI не переносится расчёт доступности, цены, совместимости, 30 минут,
   списания или выбора следующего пакета.
3. Каждая изменяющая команда имеет actor/device context, deadline, audit и
   idempotency. Offline replay использует sequence вместе с idempotency key и
   не создаёт новую сессию без успешной online-аутентификации.
4. Guest остаётся отдельным участником без balance/ledger. Его session start
   разрешается только после server-confirmed direct payment.
5. Сохранённый пакет на новом WinUI login не расходуется автоматически:
   совместимый пакет показывается и активируется отдельным подтверждением;
   после активации следующий совместимый элемент очереди стартует по правилам
   backend.
6. Вне этого плана остаются VNC/remote control, внешние эквайеры и webhooks,
   bonus spending/refunds/reserve, basket/order semantics, тяжёлые XLSX/PDF
   отчёты и выделение микросервисов.

## Этапы реализации

### 1. Зафиксировать сквозные DTO и terminology

- [x] Завести contract matrix с owner, source of truth, transport, idempotency,
  audit и verification evidence для каждого сценария.
- [ ] Описать versioned DTO: `PaymentPart`, `Package/Entitlement`, ordered
  queue item, package compatibility/activation result, `EntryDecision`,
  `SessionSnapshot`, `TransferOffer/Confirm`, offline operation batch/replay.
- [ ] Согласовать терминологию password/PIN между продуктовым контрактом,
  portal DTO и UI, не меняя security policy молча.
- [ ] Добавить protobuf compatibility tests и typed BFF methods до реализации
  consumers; generated Python/C# код обновляется одной изменяемой схемой.

### 2. Backend: entitlements, login grant и session core

- [ ] Спроектировать миграции и ownership для purchase/entitlement queue,
  activation, consumption, burn reason, zone/time-window compatibility и
  ordered state transitions.
- [ ] Добавить use cases покупки/очереди/явной активации и session snapshot с
  balance, active package, queue, zone, meter и server timestamps.
- [ ] Реализовать пять бесплатных минут на каждый успешный login с durable
  grant/idempotency; отделить их от tariff configuration `free_minutes`.
- [ ] Встроить queue selection в session start, metered charge, zone change,
  voluntary/operator stop, exhaustion и next-compatible auto-start по backend
  правилам; queued unstarted packages не сжигать.
- [x] Добавить database constraint/use-case guard на одну активную client
  session и тесты конкурентного старта.

### 3. Backend: access, reservations, transfer и offline protocol

- [x] Добавить отдельный `CheckEntry`/entry-decision use case: reservation
  interval, 30-minute lock, assigned client match, anonymous guest reservation,
  disabled/offline workstation и machine-readable refusal reason.
- [ ] Встроить entry decision в login/session start и сделать одинаковый результат
  для HTTP, gRPC и WinUI; UI default `now + 30m` не считать бизнес-правилом.
  Backend session start уже вызывает decision; WinUI transport/UI ещё не подключены.
- [ ] Реализовать transfer offer/confirm на новом ПК: explicit confirmation,
  atomic move of session/meter/queue, old-PC restart command и duplicate-safe
  ACK; несовместимый активный пакет обрабатывать по контракту с warning.
- [ ] Спроектировать durable client operation journal/batch с monotonic sequence,
  idempotency, replay result, conflict/reconciliation state и безопасным retry.
  До login offline не разрешать новую сессию.
- [ ] Расширить heartbeat/session snapshot и operator read model полями последнего
  клиента, session state, queue summary и last-seen, не раскрывая лишние PII.

### 4. Backend: unified settlement и guest paid start

- [x] Ввести provider-neutral settlement boundary с набором payment parts,
  method snapshot, amount, reference и cash-shift context; каждый part сохранять
  отдельно, общий total проверять транзакционно.
- [x] Подключить parts к client top-up, product sale и прямой оплате guest
  tariff/session. Balance part доступен только зарегистрированному клиенту;
  guest balance запрещён.
- [x] Возвращать явный server payment confirmation, который является предусловием
  guest session start; повторная доставка не должна повторить sale или unlock.
- [ ] Не смешивать настройку payment methods с проведением платежа: активность,
  порядок и display name валидируются в settings, settlement — в owner-модулях.

### 5. Frontend: операторская реализация контрактов

- [ ] Показать на карте текущий tariff/session snapshot и краткую ordered queue;
  все статусы, 30-minute lock и причины отказа брать из backend DTO.
- [ ] Переделать guest flow в явную цепочку: workstation → guest tariff →
  payment/mixed payment → confirmed sale → session start/unlock. Не стартовать
  гостя из одного клика по свободному ПК.
- [ ] Добавить payment method/parts в top-up, product sale и guest sale с явным
  подтверждением и сохранением idempotency по всей попытке.
- [ ] Добавить reservation entry decision/banner, named-client match и guest
  anonymous semantics; не вычислять блокировку локально.
- [ ] Добавить transfer UI с offer/confirm/result и отображением offline ПК,
  last client/time/status. VNC и remote control не добавлять.

### 6. WinUI: post-login widget, snapshot и offline behavior

- [x] Разделить window presentation по состояниям: fullscreen gate до auth,
  normal desktop + compact borderless widget после auth; убрать fullscreen-only
  assumption и добавить tray hide/show с собственной кнопкой. Native smoke
  остаётся отдельной проверкой этапа 7/8.
- [ ] Отображать station, server entry decision/banner, active session snapshot,
  queue и explicit package activation; booking получать только из backend.
- [ ] Добавить самостоятельное завершение сессии, logout и restart policy в
  соответствии с server result; уведомления должны быть self-closing через три
  секунды и иметь явную кнопку закрытия.
- [ ] Реализовать device/client token storage и durable offline journal по
  approved Windows storage boundary; replay только через backend batch protocol.
- [ ] Добавить transfer confirmation на новом ПК и проверку повторной доставки;
  WinUI не рассчитывает тариф, деньги или совместимость.

### 7. Production hardening и native boundary

- [ ] Закрыть enrollment rebind/rotation/rate limit, token expiry/revocation,
  TLS/mTLS policy, Credential Manager и отсутствие секретов в логах/AppData.
- [ ] Проверить native build/test, обычного ограниченного пользователя,
  автозапуск/recovery, post-login desktop/widget/tray и restart на целевой
  Windows-машине.
- [ ] Отдельно подготовить reversible provisioning Assigned Access/Shell
  Launcher; app-level access-gate не считать доказательством kiosk security.

### 8. Сквозная проверка

- [ ] Backend unit/application tests и PostgreSQL concurrency tests для каждого
  invariant; проверка migration upgrade/downgrade.
- [ ] Proto generation/compatibility и BFF contract tests для HTTP и gRPC.
- [ ] Frontend typecheck/build и headed smoke guest payment, top-up parts,
  reservation decision, queue и transfer.
- [ ] Windows native smoke: offline current session, reconnect batch duplicate,
  login gate, package activation, widget/tray, restart и no-new-session offline.
- [ ] Обновить `plans/VERIFICATION.md` и `plans/SUMMARY.md` только фактическими
  результатами, разделяя source-level, runtime, visual и native evidence.

## Порядок и зависимости

Сначала фиксируются DTO и terminology (этап 1). Затем backend entitlements и
settlement (этапы 2 и 4), после чего backend access/transfer/offline (этап 3).
Frontend и WinUI подключаются только к опубликованным контрактам (этапы 5 и 6).
Native hardening и полный smoke (этапы 7 и 8) завершают релизный срез.

## Критерии готовности

- Три продуктовых контракта и `CODEX.md` не противоречат планам и transport DTO.
- У каждой обязательной функции есть backend owner, idempotency strategy и
  evidence из соответствующего типа проверки.
- Клиент не стартует гостя до подтверждённой оплаты, не расходует пакет без
  активации и не создаёт вторую активную сессию клиента.
- Перенос, offline replay, payment parts и reservation entry decision атомарны,
  повторяемы и объяснимы оператору/пользователю.
- WinUI до входа locked, после входа widget-mode соответствует контракту; native
  kiosk явно отделён и проверен отдельным evidence.

## Открытые решения

- Точные названия protobuf RPC и версий, а также формат transfer confirmation.
- Набор payment method types, который будет доступен в MVP после provider-neutral
  boundary; продуктовый контракт не фиксирует конкретные внешние providers.
- Границы и Windows API tray/widget/offline storage при native smoke.
- Политика отображения минимального snapshot/PII на operator map и в WinUI.
