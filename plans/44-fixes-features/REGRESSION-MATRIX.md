# План 44 — regression matrix фазы 0

Дата baseline: 2026-09-17  
Статус: `phase-0-in-progress / early P0 implementation`

Этот документ фиксирует наблюдаемое поведение и границы доказательств до
реализации фиксов. Существующие passing tests не означают, что пользовательский
баг закрыт: для каждой строки нужен тест на public entry point или отдельный
platform smoke.

## Baseline

Из корня checkout выполнены:

```text
uv run --directory ./backend pytest -q tests/test_metered_billing.py tests/test_snapshot_transport_contract.py tests/test_api_reservations_sessions_billing.py
24 passed

npm --prefix ./frontend run test -- --run
19 passed

dotnet test win-client/GameClub.Client.sln -p:Platform=x64
34 passed
```

Baseline подтверждает текущие unit/API/portable consumer tests. Он не
подтверждает PostgreSQL/Redis DSN, live Compose, headed browser, Windows native
restart/access-gate или Windows sound/toast.

## Матрица поведения

| ID | Воспроизводимый сценарий | Ожидаемое поведение | Минимальное доказательство | Текущее состояние |
| --- | --- | --- | --- | --- |
| F-01 | Клиент с положительным балансом запускает пакет на 1 минуту; следующий server tick исчерпывает пакет; пакета в очереди нет | пакет получает `exhausted`, остаток `0`, начинается per-minute и списывается только новая delta | backend application + DSN transaction test, затем Compose session smoke | `test_exhausted_package_falls_back_to_per_minute_with_positive_balance` проходит; недостаточный баланс и group debt policy остаются |
| F-01b | То же при недостаточном балансе и группе без долга | debit отклоняется, meter/session переходят в завершённое состояние без повторного списания | unit + PostgreSQL rollback/state test | `_debit_meter_delta` переводит meter в exhausted при ошибке; end-to-end session result не зафиксирован |
| F-02 | Server snapshot показывает 3 минуты, локальное время проходит; следующий snapshot приходит с корректировкой | local countdown уменьшается плавно; polling исправляет drift и не увеличивает остаток в рамках источника | deterministic Win Core test с injected clock; затем Windows visual smoke | `SessionTimeProjectionTests` проходят; projection подключён к `MainViewModel` и 1-секундному UI loop; native visual smoke ещё не выполнен |
| F-03 | Пользователь нажимает «Выйти»; backend подтверждает stop; клиент должен открыть access-gate и отправить restart | порядок stop ack → lock/access-gate → allowlisted restart; ошибка этапа видима, повтор безопасен | Core state-machine test + Windows native x64 smoke | `LogoutWaitsForServerStopBeforeApplyingRestartPolicy` проходит на Core; native gate/restart ещё не доказаны |
| F-04 | Активный зарегистрированный клиент, оператор выбирает карту/наличные/депозит/mixed | авторизация на ПК не сужает разрешённые operator methods | backend API + frontend checkout test | frontend сейчас принудительно оставляет balance для tariff при active session |
| F-05 | Один tariff/order оплачивается несколькими parts | сумма частей равна order total, части сохранены, retry идемпотентен, partial failure не оставляет ложный success | payment domain/API/DSN tests | mixed parts есть у product sale/top-up; entitlement tariff path требует отдельного доказательства |
| F-06 | Во время session оператор пополняет депозит | следующий snapshot содержит новый balance/time; package source не заменяется преждевременно | API/portal polling test + Win Core test | snapshot/polling есть; отдельный top-up → time regression отсутствует |
| F-07 | Deposit открыт из busy PC с registered client | клиент предвыбран, отображён, смена получателя явная и подтверждённая | frontend component/browser test | `DepositPanel` умеет `initialClient`, входной путь должен быть проверен end-to-end |
| F-08 | Клиент в группе с разрешённым долгом достигает лимита | backend позволяет только утверждённый долг; за пределом отказывает; UI не является security boundary | domain/API/DSN debit tests | client group и policy ещё не реализованы в коде |
| F-09 | Создаётся новый registered client после выбора default group | assignment происходит транзакционно; существующие клиенты не меняются | repository/API migration test | настройки default group отсутствуют |
| F-10 | Guest-only tariff продаётся на busy PC с active registered client | selector фиксирован на active client; backend отклоняет guest sale; Win self-service не показывает operator-only | backend API + frontend browser + Win catalog test | audience есть; отдельный sale channel и active-client guard требуют проверки |
| F-11 | В очереди есть active/queued/exhausted/burned packages | Win Client показывает только active/queued, локализует статусы; balance-time скрыт при active package | Win Core/ViewModel test + visual smoke | snapshot содержит statuses, UX-фильтрация не подтверждена |
| F-12 | Настроены пороги 30/5 минут и reconnect | каждое событие один раз воспроизводит звук/toast по rule | backend rule/API + Win adapter test + Windows smoke | текущая notification infrastructure есть, admin rules/dedupe contract не реализованы |
| F-13 | На карте active session с package и balance/credit | tooltip показывает server snapshot, stale marker и не показывает UUID; формулу кредита не считает frontend | frontend component/browser + live map smoke | карта polling есть, полного tooltip нет |

## P0 reproduction protocol

### F-01 — package → per-minute

1. Подготовить зарегистрированного клиента с балансом выше одной минутной
   ставки и опубликованный per-minute tariff зоны.
2. Купить и активировать короткий package tariff, запустить session через
   public session service.
3. Выполнить server meter tick после полного package duration.
4. Проверить persisted entitlement status, meter source, client balance и
   session status; повторить tick с тем же временем.

Current result: сценарий сначала воспроизводил отсутствие fallback, затем был
исправлен в `BillingService`; targeted test и связанный backend slice проходят.
Это не закрывает F-01b с отрицательным балансом.

### F-02 — timer polling

1. Зафиксировать snapshot с остатком 3 минуты и server time.
2. Продвинуть deterministic monotonic clock на короткие интервалы.
3. Подать snapshots `2`, затем `1`, затем `0` с controlled drift.
4. Проверить, что отображение не увеличивается и не скачет при каждом poll; при
   переходе source проверить явное server state change.

Current result: deterministic Core tests покрывают injected clock и sequence of
snapshots. Linux/portable test не заменяет Windows visual proof.

### F-03 — stop/access-gate/restart

1. Запустить authenticated session через client coordinator.
2. Нажать public logout action.
3. Зафиксировать backend stop acknowledgement, access-gate state и restart
   command/ack в recording platform ports.
4. Повторить при backend error и при недоступном power controller.

Current result: Core test подтверждает порядок server stop → restart policy;
полный access-gate/restart на native Windows всё ещё требует smoke. Live local
integration test является opt-in и в baseline не запускался.

## Решения и блокеры

- F-01b/F-08: до Phase 1 нужно утвердить, какие debit types могут использовать
  отрицательный баланс; контракт пока фиксирует policy fields и server boundary.
- F-04/F-05: нужно утвердить, как внешняя или mixed оплата привязывается к
  entitlement order активного клиента; не расширять product sale path молча.
- F-10: нужно утвердить transport field для operator/self-service channel.
- F-12: нужны лимит, MIME allowlist, хранение и permission для mp3/wav.
- F-13: нужна формула доступного времени и stale threshold для credit.
- Последняя строка `fixes.md` оборвана на «разрешенный креди», поэтому F-13 не
  закрывается до уточнения текста.
