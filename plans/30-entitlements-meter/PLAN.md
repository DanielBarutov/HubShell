# План 30 — entitlement lifecycle и session meter

Статус: `in_progress`
Приоритет: `P0`
Владелец: `backend/`
Зависимости: `03-catalog-time-tariffs`, `06-sessions`, `07-billing`,
`12-live-metered-billing`, `23-device-enrollment`,
[`29-contract-alignment`](../29-contract-alignment/PLAN.md)

## Цель

Связать уже созданную durable-очередь `client_entitlements` с реальным
жизненным циклом сессии и meter. Пакет должен расходоваться только после
server-backed активации, сохранять остаток между визитами и автоматически
передавать управление следующему совместимому пакету по правилам backend.

## Контрактная граница

Источник правил: [`backend/PRODUCT-CONTRACT.md`](../../backend/PRODUCT-CONTRACT.md)
и [`win-client/PRODUCT-CONTRACT.md`](../../win-client/PRODUCT-CONTRACT.md).

- Пакет содержит tariff/zone/duration/price и при необходимости локальное
  временное окно; обычные пакеты доступны сразу, ночные — только в окне.
- Пока активен совместимый пакет, баланс не списывается.
- При исчерпании автоматически стартует следующий совместимый пакет.
- Новый пакет при пустой очереди активной сессии стартует сразу.
- При добровольном или операторском stop остаток начатого пакета сгорает;
  не начатые элементы очереди сохраняются.
- После нового входа сохранённый пакет только предлагается к явной активации.
- Каждый успешный login получает отдельные 5 минут `login_grant`, не связанные
  с tariff `free_minutes`.

## Текущее состояние

Уже есть migration `20260902_0036`, purchase/order/activation use cases,
portal queue DTO и отдельное поле `login_grant_minutes` в session. Не хватает
отдельного audit/idempotency evidence для повторного device session start;
account-portal login без игровой сессии grant не выдаёт по текущему контракту.

## Реализовано в текущем срезе

Добавлены migrations `0040`–`0043`, timezone-aware окна, repository operations
для activation/consume/burn, auto-next, immediate activation при пустой
очереди, monotonic meter package state и server snapshot. Device session
получает durable `login_grant_minutes=5`; portal activation остаётся отдельным
явным действием. Unit/API slice подтверждён 130 тестами; полный DSN suite после
concurrency-коррекции прошёл 146 тестов.

## Входит в план

- уточнение state machine `QUEUED → ACTIVE → EXHAUSTED/BURNED`;
- совместимость пакета с зоной, локальным временным окном и текущим моментом;
- атомарный consume по монотонной delta meter;
- автоматический переход к следующему compatible entitlement;
- burn только для уже начатого пакета при explicit voluntary/operator stop;
- durable session grant/idempotency на device session start;
- `SessionSnapshot` с активным пакетом, очередью, grant, meter и server time;
- session/billing/portal unit и PostgreSQL concurrency checks.

## Не входит

- изменение tariff `free_minutes`;
- guest balance или guest package ledger;
- external payment providers, refunds, bonuses и reservation of funds;
- локальный расчёт следующего пакета во frontend/WinUI.

## Порядок задач

1. [x] Зафиксировать domain state machine, transition table, причины burn и
   правила завершения при `EXHAUSTED`, `INSUFFICIENT_BALANCE` и stop.
2. [x] Добавить time-window value object с timezone policy и тестами границ
   `start/end`; не использовать время устройства как источник истины.
3. [x] Добавить application port `consume/activate-next/burn` с блокировкой
   session и очереди; повторный command должен вернуть тот же результат.
4. [x] Встроить выбор источника времени в meter: активный пакет → следующий
   совместимый пакет → login grant/free minutes → zone per-minute balance.
5. [x] Реализовать новый пакет во время active session: immediate activation
   только при пустой очереди, иначе ordered queue.
6. [x] Перевести device login/session start на durable `login_grant` с
   повторным безопасным ответом; account-portal authentication не считается
   игровым входом и не создаёт grant.
7. [x] Расширить HTTP/gRPC snapshot DTO и versioned compatibility tests.
8. [ ] Добавить PostgreSQL transaction/concurrency tests для двух meter ticks,
   auto-next, stop и параллельной активации.

## Критерии готовности

- ни один tick не расходует `QUEUED` пакет без activation;
- параллельные ticks не теряют минуты и не активируют два пакета;
- несовместимый или ещё не наступивший пакет остаётся в очереди;
- остаток текущего пакета burn-ится только в предусмотренном stop-сценарии;
- повторный login/consume не создаёт второй grant или debit;
- snapshot полностью объясняет клиенту источник текущего времени и остаток.

## Проверки и evidence

- unit tests domain/application;
- PostgreSQL locks, unique constraints и migration upgrade;
- API/gRPC contract tests snapshot и idempotency;
- meter integration с balance и package source;
- negative tests для zone/time-window/stop/offline-before-login.

## Открытые решения

- точный формат recurring/local time window и timezone клуба;
- нужен ли отдельный audit read-model для повторного device session start;
- нужно ли показывать оператору burn reason до подтверждения stop.

## Остаток и release blocker

Нужно подтвердить оставшиеся PostgreSQL-переходы auto-next/stop/activation и
общий transaction/UoW для debit плюс package consume. Отдельно требуется
довести fallback на поминутную ставку после исчерпания всех пакетов для session
без явно выбранного per-minute tariff и добавить dedicated grant audit test.
