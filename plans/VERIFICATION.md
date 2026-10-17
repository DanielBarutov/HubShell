# Verification matrix

### 2026-10-17 — отдельная бонусная аналитика

План 49: read-only owner-порт Clients, защищённый API и отчёт во вкладке
«Продажи»: потоки за период отдельно от текущих остатков; бонусы отдельно от
денежной выручки. 99 backend tests passed, 4 skips; 2 новых frontend tests и
production build проходят. Прежний AnalyticsView.test.tsx:215 падает отдельно.
Рабочая БД не менялась; ручная browser/Avalonia и Kafka проверка остаётся.


### 2026-10-17 — совместимость сессий и операторская корректировка

159 scoped backend tests passed / 5 skipped с отдельной PostgreSQL 17.
Memory/PostgreSQL: чтение старой сессии не принимает текущие ставки, повторный
begin сохраняет её disabled policy, новая сессия явно фиксирует программу.
Старый lease не получает новый grant. HTTP: активная V2-игра допускает точную
корректировку свободных бонусов, попытка затронуть резерв отклоняется, денежный
баланс не меняется. 16 frontend scenarios passed: сотые бонуса, причина,
подтверждение отрицательной суммы, сохранение payload/key при потере ответа,
история с автором/дельтой и отсутствие округления legacy целого поля.
Production build, scoped Ruff/format/diff проходят. Рабочая база не менялась;
браузерные/native Windows/live broker проверки и аналитика ещё не завершены.

### 2026-10-17 — переключатель поминутки и отмена неопределённого запроса

177 scoped backend tests passed / 6 skipped с отдельной PostgreSQL 17.
Проверены cancel до/после enable, запрет позднего enable, подтверждённый
checkpoint перед release, отсутствие повторного release нового резерва,
audit клиента/времени/ключа, сохранение прежнего offline бюджета при потере
ответа на увеличение. Quote учитывает свой резерв и fractional source carry;
пакетный quote не тратит резерв. Миграция 0082 дополнена cancelled marker до
выпуска, тестовая пустая история безопасно downgrade/upgrade; рабочая БД не менялась.
186 client tests passed на Linux: durable отмена после restart, отказ
повторного включения до cancel ack, refresh не включает отменённый запрос,
quote не резервирует и переключатель по умолчанию выключен. Headless Avalonia
проверяет наличие/начальное состояние панели. Windows-host Release build:
0 warnings / 0 errors; в тестовом проекте прежнее xUnit1031 предупреждение.
Ручные Linux developer-host/browser/native Windows и live Kafka/Redis ещё
не выполнены. Политика старых сессий, операторская точная корректировка и
бонусная аналитика остаются открытыми пунктами плана.

### 2026-10-17 — ядро бонусной поминутки V2

160 backend tests passed / 6 skipped с реальной отдельной PostgreSQL:
20/100% split, signed цена и зона, полный rollback обеих частей после wallet
write, конкурентный повтор без повторного debit, GAP до disable, ordered
release и stop, отсутствие денежной выручки при полной бонусной оплате.
Серверный quote не резервирует бонусы. 184 client tests passed на Linux:
подпись/checkpoint, durable запрос после потери ответа, непрерывность ledger,
неповторяемый расход и локальное отключение. Windows-host Release build:
0 warnings / 0 errors. Ruff/format изменённых файлов и diff проходят.
Пока не подключён видимый переключатель поминутки и отмена pending выдачи;
браузер, native Windows и live Kafka/Redis не проверены. Аналитика бонусов
остаётся незавершённой. Полная бонусная программа ещё не готова.

### 2026-10-17 — выдача бонусного V2-резерва

113 scoped backend tests passed / 5 skipped. Реальная тестовая PostgreSQL:
выдача/повтор/конкурентный повтор grant, snapshot/device/checkpoint guard,
откат резерва и замены активной версии при сбое сохранения. Миграция 0082
применена только к отдельной тестовой БД. Проверены server stop/interrupt и
повторный stop: резерв остаётся до ordered confirmed client stop. Ruff/format
и diff проходят, Windows-host Release build на Linux проходит. Local minute
split, C# применение grant/подписи и сквозной Kafka flow ещё не реализованы
или не подтверждены; этот срез не означает готовность бонусной поминутки.

### 2026-10-17 — бонусная покупка пакета и подтверждение в UI

Дополнение: точный wallet добавлен в V2 portal и основной Avalonia-виджет;
после этих изменений 31 backend portal/JWT/gRPC test и 180 client tests прошли.
Проверены отдельные суммы pending/reserve/available и сохранение копеек.

- Backend: 190 passed / 5 skipped, включая реальную отдельную PostgreSQL 17.
  Проверены 20/100% бонусной оплаты, скидка до расчёта, отсутствие денежного
  debit при нулевой части, stale quote, конкурентные ключи и полный rollback
  пакета/денег/бонусов/начисления. Миграции до `20261017_0081`, constraint суммы
  и явного выбора. Публичные HTTP и настоящий loopback gRPC/JWT: quote,
  повтор, неизменность денежной/бонусной частей и Ed25519 подпись receipt.
  Четыре memory-случая требуют PostgreSQL; live Kafka test пропущен без брокеров.
- Клиент: 179 tests passed на Linux, включая headless Avalonia, выключенный
  переключатель, блокировку подтверждения до ответа, durable pending выбор,
  запрет изменённого receipt, применение только денежной части без замены ledger.
  Windows-host Release build на Linux: 0 warnings / 0 errors. В тестовом проекте
  остаётся прежнее xUnit1031 предупреждение.
- Frontend: 29 scoped tests passed; полный прогон 103 passed / 1 failed
  (`AnalyticsView.test.tsx:215`, отсутствует ожидаемый текст состояния данных
  после переключения на продажи; отдельно повторяется, эти файлы не менялись).
  Production build проходит; предупреждение о bundle >500 KB остаётся.
- Ruff check/format проходят для 46 изменённых Python-файлов, diff check проходит.
  Общие Ruff-команды также проверяют generated protobuf и прежние исходники:
  там остаются нарушения, соседние файлы не переформатированы.
- Рабочие БД и приложение не обновлялись. Браузер, Kafka/Redis и native Windows
  не проверены; Linux build/headless не доказывают эти сценарии. Signed бюджет
  и бонусное списание поминутки, аналитика бонусов ещё не реализованы.

### 2026-10-17 — подтверждённые начисления и FIFO долга

[План 49](49-bonus-program/PLAN.md): 150 passed / 4 skipped. Реальная PostgreSQL 17 подтверждает покупку и bonus receipt в одной транзакции, откат после записи начисления и последующий review/retry, исходный actor/reason, FIFO со старыми не участвующими расходами, гонку погашения и receipt, cumulative minute fractions, подтверждённый V2 stop и release reserve. Проверены миграции до `20261017_0080`, перенос старого долга без бонусов и восстановление неиспользованных purchase snapshots. Core/API/memory, существующие sales/V2 tests проходят; Kafka smoke пропущен без Kafka/Redis, три memory-случая требуют PostgreSQL. Широкий unit/API: 422 passed / 23 skipped / 1 прежнее падение docstring-check на 8 guest/V2-тестах. Ruff/format/diff проходят. Бонусная оплата, signed/local V2, browser/UI/Avalonia и аналитика не подтверждены: реализация продолжается.

### 2026-10-17 — бонусный wallet, журнал и резерв

[План 49](49-bonus-program/PLAN.md): 95 scoped test passed, 1 skipped. PostgreSQL 17 — реальная миграция всей цепочки, nonzero legacy opening, negative/overflow rejection, безопасный downgrade и запрет потери истории; конкурентные операции и changed retry payload, общий rollback денег/бонусов/журналов, bigint/дроби, legacy top-up. Memory/API — JWT/permissions, read/history/correction и active V2 guard. Ruff/format/diff проходят. Широкий unit/API прогон: 411 passed, 23 skipped, 1 failed (`test_test_conventions`: 8 прежних guest/V2 функций без русских docstring). Полный `test_postgres_concurrency.py` дополнительно дал 4 прежних нарушения `ck_workstations_session_mode` из-за `server_owned`; отдельный client top-up проходит. Рабочая база прочитана read-only: 11 клиентов, бонусы 0, расхождения 0, migration head `20261013_0076`. Рабочая миграция, settlement, FIFO/начисления, Kafka, frontend и Avalonia runtime этим срезом не подтверждены.

### 2026-10-16 — расчётное ядро бонусов и аудит остатков

Первый срез [плана 49](49-bonus-program/PLAN.md): 46 тестов (`test_bonus_calculations.py`, `test_bonus_audit_postgres.py`, `test_modules_workstations_clients.py`). PostgreSQL 17 запущена отдельно во временном каталоге: проверены пустые остатки, расхождение ledger, orphan-записи, отрицательные суммы, переполнение, read-only транзакция и отсутствие изменений. Это тестовые временные таблицы, не фактическая инвентаризация рабочей БД. Ruff check/format и diff check проходят. Runtime, миграция, PostgreSQL финансовые гонки, Kafka, браузер и native Windows не проверялись: соответствующей интеграции ещё нет.

### 2026-10-16 — дизайн бонусной программы

[План 49](49-bonus-program/PLAN.md): согласованы продуктовые правила, обновлены контракты. Это документальный срез: автоматическое начисление, бонусная оплата и V2-резерв не реализованы. Тесты приложения, PostgreSQL/Kafka, браузер и native Windows для этого среза не выполнялись; проверки реализации перечислены в плане.

### 2026-10-15 — скидка категории для поминутной V2-игры

- Backend подписывает цену минуты через Catalog quote с категорией клиента.
  `OfflineTariffSnapshot.is_per_minute = 11` отличает бесплатную минуту от
  пакетного тарифа; старые положительные ставки поддерживаются.
- Клиент сохраняет баланс и активную сессию при нулевой цене со скидкой;
  grant и пакеты расходуются первыми. Бесплатная минута не создаёт debit,
  повтор границы идемпотентен. Виджет: «Бесплатно», компактный таймер: «∞».
- Linux: 79 backend-тестов (включая скидки 0/12,5/100% и округление),
  172 теста клиента (включая signed snapshot reader и headless виджет).
  Windows-host build: 0 ошибок/предупреждений. В тестовом проекте остаётся
  прежнее предупреждение xUnit1031. Ruff/format изменённых Python-файлов и
  `git diff --check` проходят. Graphify обновлён; прежние ошибки парсинга
  `frontend/src/api.ts` и `frontend/src/api/index.ts` ограничивают полноту графа.
- PostgreSQL/Kafka, браузер и native Windows не проверялись. Runtime frontend
  не менялся. Развёртывание и сборка поставляемого EXE не выполнялись:
  обновить клиент и backend, затем выполнить новый вход. Прежние снимки,
  активные ledger и исторические списания не исправляются этим изменением.

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


2026-10-12: `RequestedThemeVariant="Dark"` в Avalonia-клиенте устраняет зависимость
Fluent-полей от светлой темы ОС. Linux: `dotnet test win-client/tests/GameClub.Client.Tests.csproj
-p:Platform=x64 --filter FullyQualifiedName~AvaloniaHostSmokeTests --no-restore`
— 14 passed; сборка успешна, существующее предупреждение xUnit1031 остаётся.
Ручной ввод, фокус и наведение на Windows со светлой темой ОС не проверены.

2026-10-11: собрана `release/` — self-contained single-file Windows x64 EXE (~104 MiB),
server.ini и start-service.cmd/ps1 + install/uninstall. 158 .NET тестов прошли:
разбор INI, ошибка/дубликаты/небезопасный HTTP, чтение рядом с host, env priority.
PowerShell Parser 7.4.6 проверил синтаксис start/install/uninstall/publish.
`IncludeAllContentForSelfExtract=false`: отдельный .NET 8 Linux single-file probe
подтвердил BaseDirectory рядом с executable (true возвращает extraction directory).
Watchdog использует ProcessPath, не extraction directory. Права C:\GameClub защищает
installer: SYSTEM/Administrators F, Users RX, владелец Administrators, reparse запрещены.
Адрес клуба ещё не предоставлен: server.ini оставлен незаполненным, запуск installer
блокируется до заполнения GrpcAddress. Публичные snapshot keys нужны для V2-входа.
Windows EXE/SCM/WTS/ACL вручную не запускались; Linux publish этого не доказывает.


2026-10-11: реализован постоянный desktop-виджет без изменения Windows-пользователя
и kiosk policy. В Windows User-режиме Topmost выключен; foreground WinEvent скрывает
виджет в других приложениях и возвращает на Explorer Desktop в прежнем состоянии.
Обычное закрытие отменяется, выход убран из трея. Повторный Opened после Hide/Show
не запускает host/recovery повторно и не сбрасывает геометрию HUD. Скрытие владельца
отменяет незавершённое подтверждение и освобождает окно; история повторно показывается. Maintenance после существующей
проверки пароля — обычное окно без Topmost, доступно скрытие через прежнюю кнопку.
Добавлена опциональная LocalSystem-служба HubShell.Watchdog: проверка console-сессии,
запуск GUI с токеном/окружением текущего пользователя, session-local mutex, retry delay,
SCM recovery. Install/uninstall поддерживают службу с явными параметрами; Windows
учётные записи/политики не меняются. Установка только в Program Files от администратора.
Проверено на Linux: 148 .NET тестов, сборки Windows host и Avalonia/Linux;
синтаксис install/uninstall проверен PowerShell Parser 7.4.6 без исполнения скриптов.
Пользователь разрешил исключение из AGENTS.md: глобальный WH_KEYBOARD_LL только в
Locked. Подавляются Win и Win+D/Win+R; при User/Maintenance/Dispose hook снимается.
Unit-проверки: нажатия/отпускания, оба Win, снятие ограничения, доступность Ctrl+Alt+P.
Реальное подавление системных сочетаний на Windows не проверено.
Ctrl+Alt+Del не перехватывается. Native foreground/Win+D, SCM/WTS, restart с настоящим
ledger, Event Log, PowerShell installation и режим менеджера в Windows не проверены.


2026-10-11: крестик зарегистрированного и гостевого виджета сворачивает
клиент в вертикальную HUD-кнопку по `ref/Неоновый Windows 11 с HUD-таймером.png`.
Кнопка 68×280 DIP стоит вплотную к правому краю рабочей области, показывает
остаток сессии ЧЧ:ММ и разворачивает виджет по клику. Переход 260 мс;
закрытия клиента и изменения игровой сессии нет. Блокировка/maintenance
отменяют анимацию и показывают access-gate. Реализация общая для Linux/Windows.
Проверки: 137 .NET тестов (гость/аккаунт, сворачивание/разворачивание,
сохранение сессии, отмена перехода блокировкой, обновление времени после допродажи),
Skia headless-рендер и обе сборки на Linux. Native Windows/DPI и живой
backend-сеанс не проверены.


2026-10-11: история аккаунта, уведомление виджета (включая недостаток средств)
и подтверждения покупки/переноса/выхода приведены к тёмно-бирюзовому оформлению.
Подтверждения используют общую форму с высотой по содержимому, компактными кнопками,
отменой по Escape и начальным фокусом на отмене. Предупреждения и серверные действия
сохранены. История подстраивается по содержимому, длинный список прокручивается.
Проверено: 135 .NET тестов; Skia headless-рендер подтверждения (390×149),
истории и уведомления на Linux; сборки Avalonia/Linux и Windows host.
Живые покупки и native Windows-окна в этой проверке не запускались.


2026-10-11: гостевой V2-виджет оформлен по `ref/Синеокий рабочий стол с панелью HUBSHELL.png`.
Использована общая оболочка 390×до 700 DIP: «Гость», соединение, активная сессия,
оплаченные пакеты и выход. Данные аккаунта не показываются даже при старом portal
snapshot; аккаунт не создаётся. Список берётся из guest ledger, обновляется после
допродажи, скрывает exhausted/burned; отображает честный остаток в минутах.
Сохранено отображение ошибки доставки обновлений. Кнопка переноса отключена:
в референсе есть действие, но утверждённого V2 guest transfer use case/API нет;
сценарий переноса и его правила должны быть определены отдельно.
Проверено на Linux: 134 .NET теста (guest recovery, допродажа, уведомление UI,
изоляция старого профиля, выход), Avalonia/Linux runtime и Windows-host build,
Skia headless-рендер с тестовыми данными и без горизонтального переполнения.
Живые гостевая оплата/допродажа/выход, Windows tray и native smoke не проверены.


2026-10-11: post-login Avalonia widget оформлен по `ref/Панель HUBSHELL на рабочем столе Windows 11.png`.
Добавлены графитово-бирюзовая поверхность, аватар, компактные карточки, строки тарифов
и пакетов со статусами; перенос и история расположены рядом внизу. Существующие данные,
покупка/выход с подтверждением, сброс пароля, бронь и уведомления сохранены.
Окно 390 DIP, высота до 1000 DIP с учётом рабочей области и прокруткой.
Проверено на Linux: 134 .NET теста, Avalonia и Windows-host build без предупреждений,
Skia headless-рендер с тестовыми данными 390×1000 и 390×700, доступность нижних действий
при прокрутке и отсутствие горизонтального переполнения. Пинг и отдельный экран
«Все тарифы» не добавлены. Живые покупка/перенос/выход, Windows tray, позиционирование
на реальном мониторе и прозрачность Windows не проверены.


2026-10-11: регистрация Avalonia оформлена по `ref/Неоновая регистрация в GAMEHUB.png`:
общий фон и карточка места, заголовок, неоновые поля с иконками, кнопки на всю ширину
и отдельный текст справа. Поля, ограничения, маска телефона и V2 flow сохранены.
Ссылка на правила клуба не добавлена: целевой документ отсутствует.
Проверки: Linux runtime build, headless/Skia-рендер формы, 134 .NET теста.
Регистрация через живой backend и Windows native smoke не проверены.


2026-10-11: исправлен вход в аккаунт после завершённого гостевого V2 ledger:
повторный stop использует guest endpoint с payment ID, не account endpoint с пустым client ID.
Сохранён отказ при PermissionDenied; журнал не очищается. Иконки access-gate выровнены
в фиксированных Canvas/Viewbox. Проверено: 133 .NET unit/headless теста и Skia-рендер;
живой повторный вход и Windows smoke не выполнены.


2026-10-11: access-gate Avalonia оформлен по `ref/Неоновый вход в игровой клуб HUBSHELL.png`.
Фон `ref/фон для входа GAMEHUB.png` встроен в общий UI-ресурс Linux/Windows;
центральная карточка места, неоновые кнопки и блок справа заменяют прежнюю двухколоночную форму.
Сохранены вход по нику/телефону, регистрация, скрытый manager route, ошибки и серверная тема.
Восстановление пароля и системные кнопки из картинки не добавлялись.
Проверено: Linux build, 131 unit/headless тест, Skia headless-рендер 1120×680.
Живой backend login, ручной Linux smoke и Windows fullscreen/tray не проверены.


2026-10-11: карта мест по умолчанию 10 × 4 — 8 тестов MapScreen проходят,
`npm --prefix ./frontend run build` проходит. Ручная проверка в браузере и
пересборка Compose frontend не выполнены.

2026-10-11: `uv run --directory ./backend pytest tests/test_modules_cash.py
tests/test_jobs.py -q` — 18 passed. Проверены повторные запуски расписания,
ручное открытие после автозакрытия и закрытие на следующий день; Ruff проходит.
Это unit-проверка с memory repository, PostgreSQL adapter и обновлённый
Compose worker в этом срезе не проверены.

Дата последней проверки: `2026-10-03`.

Документ разделяет фактически проверенное поведение и то, что пока подтверждено
только исходниками или требует другой платформы.

| Срез | Что проверено | Результат | Граница доказательства |
| --- | --- | --- | --- |
| Backend foundation и модули | Ruff, unit/API/contract tests, metered billing, package windows/auto-next, locked consumption delta, snapshot/heartbeat, transfer, offline replay, settlement review/retry, manager credential, lockdown policy, analytics, payment parts, guest paid-start и entry decision; guest `active_tariff` snapshot с server-calculated remaining time; shared Dramatiq broker и dedicated metering queue | `153 passed, 18 skipped` без DSN; contract-layout assertions обновлены под текущие API/Avalonia boundaries; bounded-context split и Russian docstring guard проходят | DSN suite включает PostgreSQL mixed settlement fault/idempotency, package locked-delta, transfer two-target concurrency и offline duplicate-debit; production cross-owner UoW остаётся policy gap |
| PostgreSQL schema | Alembic migration chain through active-client, payment-parts, entitlement, guest-payment, login-grant, transfer, offline и settlement retry metadata migrations | `20260918_0061 (head)`; upgrade/rollback/upgrade rehearsal, constraints/column check и isolated backup/restore прошли | Production backup policy и cross-owner transaction boundary не утверждены |
| Isolated PostgreSQL test container | Отдельный `postgres:16-alpine` из `docker-compose.postgres-test.yml`, Alembic migration, repeatable seed и analytics adapter against `GAMECLUB_TEST_POSTGRES_DSN` | `234 passed`; отдельный PostgreSQL marker run `21 passed, 213 deselected`; seed повторно применён без дублей | Контейнер предназначен для локальных проверок; production backup/restore policy остаётся отдельной задачей |
| Backend typing and lint | Ruff check, Ruff format check и mypy по `src`/`tests` | все проверки успешно; mypy `Success: no issues found in 253 source files`; `314 files already formatted` | Типизация не заменяет runtime-проверки PostgreSQL, Redis, браузера или Windows |
| Guest persistence | Guest CRUD/search и ссылки `guest_id` в Reservation/Session | успешно | Memory/API contract checks; PostgreSQL concurrency matrix пропущена без DSN |
| Cash producer/approval boundary | provider-neutral producers, approvals, HTTP/gRPC contracts | успешно | Unit/API/contract suite; реальные provider webhook не подключены |
| gRPC | generated protobuf, client portal entitlement queue/explicit activation, analytics/workstation/business registration, auth/audit и optional TLS policy; `SessionSnapshot.active_tariff` с названием/количеством/elapsed/remaining; внешний `SystemService/GetHealth` и авторизованный `SessionService/GetSnapshot` через `:51051` | generated contract и mapping-тесты успешно; Compose rebuild/health успешно | external TLS deployment и full gRPC flow matrix не проверялись; private-LAN insecure transport допускается |
| Frontend | `76` тестов Vitest, проверка типов TypeScript, lint и production-сборка Vite; четыре вида отчёта аналитики | успешно; frontend и backend в Docker Compose готовы, оба health endpoint вернули HTTP `200`; четыре отчёта просмотрены в Chromium на Linux с данными локальной базы | Проверена ширина экрана `1600px`; нужно проверить мобильную раскладку и остальные сценарии в браузере |
| Analytics recognized revenue | Finance service передаёт период в PostgreSQL snapshot; v2 Finance API считает пополнения один раз и не прибавляет списания баланса | `21 passed, 4 skipped`; Ruff прошёл; Compose Finance API вернул HTTP `200` и данные пополнений после backend fix | Четыре теста PostgreSQL/Kafka пропущены без настроек тестовых зависимостей; Compose smoke прошёл на локальной базе |
| Device panel V2 refresh regression | Одинаковый набор команд в активной сессии, старые V1-сессии только для чтения, одна кнопка продажи | `2` целевых теста прошли; проверка типов и production-сборка прошли; все тесты фронтенда — `76 passed` | Нужно вручную проверить панель ПК в браузере |
| Workstation session-mode cache/cutover | Redis round-trip сохраняет `session_mode`; ключ кэша обновлён; migration `20261002_0071` переводит сохранённые места в V2 и блокирует запуск при активной V1-сессии | `17` целевых backend tests прошли; Ruff прошёл; full backend suite: `325 passed, 35 skipped`, один failure в общей проверке отсутствующих русских docstring | Миграция не применялась к рабочей БД; при активной V1-сессии сначала нужен подтверждённый `POST /api/v1/sessions/cutover/terminate-v1`; PostgreSQL migration не проверена на живой БД |
| Frontend test foundation | Vitest API-boundary tests: phone normalization, transfer idempotency header/JSON, bearer refresh + retry и public API error mapping; React component/accessibility slice для login, map, sale, booking, offline-routing и confirmation | `19 passed` (`npm run test`) | `fetch` контролируется только на HTTP boundary; browser visual/realtime matrix ещё не проверялась |
| HTTP/gRPC contract fixtures | authorized ASGI context, stable workstation/reservation HTTP DTO factories and shared snapshot expectation for HTTP/gRPC adapters | reservation API smoke and snapshot transport contract pass | real PostgreSQL/Redis adapters and native Windows transport remain separate evidence |
| Coverage guardrail | V8 frontend and pytest-cov backend reports with explicit thresholds | frontend `17.18%` lines / `17%` guardrail; backend `70.10%` lines / `70%` guardrail | first measured baseline; DSN/native/browser coverage remains unproven |
| Frontend live flow | operator login, persistent refresh после reload, spatial map, tariff/product checkout idempotency, catalog sale confirmation, analytics overview, settings и payment-methods CRUD | успешно; headed mock smoke прошёл dashboard/map, offline panel и booking panel; component tests покрывают базовую accessibility semantics | Полный browser matrix, duplicate/error/queue/entry/transfer/guest UI, visual regression и realtime transport ещё не проверялись |
| Windows client | структура слоёв, protobuf consumers, server EntryDecision в portal login/register и session start, snapshot/transfer gateway, DPAPI journal/sequence, package notification, server-backed guest tariff/remaining time, pre-auth gate, post-auth widget/tray и restart flow | source-level успешно; generated protobuf signature проверена временным protoc | WindowsAppSDK compile/runtime, reconnect/power-loss и native Windows пока не доказаны |
| Avalonia Linux developer host | `net8.0` Core emits shared `MainViewModel` with portable visibility states; Avalonia host contains access-gate, local `Ctrl+Alt+P` manager route, manager password/maintenance, portal/session, tariff confirmation, queue, transfer, history and booking UI | source/unit slice добавляет shortcut state tests и headless manager-surface checks; Linux build/test проверяют portable behavior | Linux does not prove physical Windows chord delivery, Windows tray, compact placement, DPAPI, restart or kiosk behaviour |
| Avalonia Windows-target artifact | `GameClub.Client.Avalonia` cross-publish `net8.0/win-x64` из Linux | создан `win-client/artifacts/avalonia-cross-publish/win-x64/Debug/GameClub.Client.Avalonia.exe` (`152064` bytes), framework-dependent | это только cross-compile artifact; Windows runtime, publish delivery и kiosk evidence не проверены |
| Avalonia Windows production host | `GameClub.Client.Windows` composes shared Avalonia UI with DPAPI journal, Windows restart/power, command stream, fullscreen/compact window mode with transparent rounded outer corners and native tray; `GameClub.Client.Windows.sln` is the Windows production entry | Linux source build succeeds with `0` warnings/errors; self-contained `win-x64` folder-publish creates `GameClub.Client.Windows.exe` (`152064` bytes, PE32+ GUI) and `hostfxr.dll` | Runtime, actual transparency/tray/window placement and kiosk policy need a native Windows machine |
| Local Figma canvas bridge | Node WebSocket parser/secret comparison tests, JavaScript syntax, `manifest.json` parse, local loopback `/health`, MCP `initialize` и `tools/list` | source-level успешно: `3` Node tests passed; bridge bound only to `127.0.0.1:3847` and exposed only `figma_status`/`figma_apply_batch` | Figma Desktop dev-plugin was not manually imported or paired in this Linux check; native layer creation, edit permission and cloud file access remain unverified |
| Windows publish | воспроизводимый self-contained publish script и single-file portable EXE через `build-portable-exe.ps1` | source-level успешно | Сам publish и запуск требуют Windows/.NET/Windows SDK; один EXE ещё не запускался на целевой машине |
| Windows native | Avalonia production host restore/build, access-gate под обычным пользователем, reconnect, темы, restart, tray и compact widget | не проверено | Native build/runtime запускать на Windows; Linux source build не заменяет этот check |
| Docker Compose | config validation, backend rebuild/restart, PostgreSQL/Redis readiness, migration `20260902_0048`, backend HTTP health/auth/entry decision, frontend startup, worker/scheduler и dedicated meter worker | успешно в текущем прогоне 2026-09-06; worker обрабатывает billing/cash actors, `/health/ready` и `/health/live` OK, backend HTTP/gRPC healthy | live meter на реальной пользовательской сессии и browser matrix требуют отдельного smoke; native Windows client остаётся отдельной проверкой |
| Catalog product edit regression | реальный PUT существующего товара через frontend proxy после пересборки backend | `200 OK` | Проверен товар `Кофе`; отдельная PostgreSQL integration matrix без test DSN по-прежнему пропускается |
| Product sales and analytics | продажа товара клиенту из баланса, уменьшение остатка, snapshots цены/себестоимости/категории, overview и client analytics через live HTTP; KPI, дни/часы, маржа, оплаты, зоны/ПК/тарифы/категории и клиентская статистика в UI | успешно | Smoke на локальном Compose; cash/guest сценарий дополнительно покрыт unit/API tests |
| Live metered sessions | per-minute tariff, tariff-configured free minutes, separate device login-grant subtraction, package consumption/auto-next, local time-window eligibility, delta debit, insufficient-balance stop и session meter persistence | backend unit slice `53 passed`; C# client full suite `113 passed`; manual Linux V2 session `582467e4-6726-4d5a-8c09-0b69e00b90f0` accepted 5 grant events, 3 per-minute debits and stop at zero balance | PostgreSQL DSN concurrency suite, fault injection and native Windows timer remain separate checks |
| V2 billing and guest tariff regression | local minute runner, balance debit after free time, debt boundary, package priority/purchase/early exit, guest cash/transfer/mixed payment and tariff restrictions | `22` new C# tests + `11` new Python tests; all pass; real Kafka worker accepted the manual session facts | full PostgreSQL cross-owner transaction proof and native Windows runtime are not covered by Linux/unit evidence |
| Operator map quick operations | карта как главный экран, PC context menu, tariff mini-cards, guest/client selection, inline product sale and top-up | успешно | Playwright headed smoke на локальном Compose; device command runtime требует Windows |
| Product contract audit | сравнение backend/frontend/win-client product contracts с кодом, CODEX и планами; implementation progress зафиксирован в плане 29 и планах 31–37 | source/unit + Compose/HTTP/gRPC/headed slice реализован; DSN suite добавила package/transfer/offline/settlement evidence; 11 subitems сведены в `EVIDENCE-20260902.md` | native Windows/kiosk, full browser/accessibility matrix и production security evidence остаются незакрыты |
| Plan 44 phases 0–5 / F-01…F-13 current slice | client groups/default assignment and bounded metered debt; tariff `sale_channel`; active-client entitlement `payment_parts`/cash-shift checkout with durable settlement review/retry; explicit deposit recipient confirmation; notification rules/stable event id with HTTP/gRPC snapshot transport; PcGrid/MapView session tooltip; fixes/plans/contracts synchronized | full backend `174 passed, 19 skipped`; API/contract `42 passed, 151 deselected`; Ruff clean; frontend typecheck and `25 passed`; production build successful; Win Client solution `42 passed`; mixed entitlement/reconciliation regression, client-group, notification, sale-channel, settings, deposit and tooltip tests pass; `git diff --check` clean | skipped PostgreSQL DSN tests, live Compose/browser smoke, native Windows sound/toast/access-gate/restart/timer, and automatic mixed-payment rollback remain outside current evidence/MVP boundary |
| Session recovery and tariff zones | heartbeat active-session snapshot, device-authenticated gRPC `Resume`, Win-client resume wiring, operator `group_id` tariff query, Win portal scoped snapshot, session/guest-payment backend guards | targeted HTTP/unit/gRPC checks и frontend production build успешно; backend suite: `153 passed, 18 skipped` | C# native Windows restart/power-loss/reconnect smoke требуют Windows/.NET окружения; operator management catalog намеренно остаётся unscoped |

Сборка и startup diagnostics: [../win-client/docs/WINDOWS-BUILD-AND-RUN.md](../win-client/docs/WINDOWS-BUILD-AND-RUN.md).
Функциональный smoke: [../win-client/docs/REAL-PC-VERIFICATION.md](../win-client/docs/REAL-PC-VERIFICATION.md).

Детальный evidence текущего среза планов 31–37 находится в
[37-platform-integration-evidence/EVIDENCE-20260902.md](37-platform-integration-evidence/EVIDENCE-20260902.md).

## Повторяемые команды

Каждый блок запускается из корня `/home/daniel/HubShell`; не переходите в
`backend`, `frontend` или `win-client`.

Backend:

```text
cd /home/daniel/HubShell
uv run --directory ./backend pytest -q -m "not integration and not slow"
uv run --directory ./backend pytest -q -m "api or contract"
GAMECLUB_TEST_POSTGRES_DSN=... GAMECLUB_TEST_REDIS_URL=... uv run --directory ./backend pytest -q -m integration
uv run --directory ./backend ruff format --check src tests
uv run --directory ./backend ruff check .
GAMECLUB_POSTGRES_DSN=... uv run --directory ./backend alembic current
```

Frontend:

```text
cd /home/daniel/HubShell
npm --prefix ./frontend run typecheck
npm --prefix ./frontend run test
npm --prefix ./frontend run build
```

Linux Avalonia developer host:

```text
cd /home/daniel/HubShell
dotnet restore win-client/GameClub.Client.sln --disable-parallel
dotnet build win-client/GameClub.Client.sln --configuration Debug --no-restore
dotnet test win-client/GameClub.Client.sln --configuration Debug --no-build
dotnet run --project win-client/src/GameClub.Client.Avalonia --configuration Debug --no-build
dotnet publish win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj --configuration Debug --runtime win-x64 --self-contained false
```

В текущем checkout SDK установлен локально как `8.0.425`; `global.json` задаёт
совместимую версию. Artifact `win-x64` не запускать и не считать Windows smoke
без отдельной Windows-машины.

Windows native:

```powershell
Set-Location "C:\Git\HubShell"
.\win-client\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

| V2 anonymous guest launch | Backend one-time grant, signed guest payload, V2 client redemption and stop path | focused backend guest-access test, frontend SaleWorkspace 8-test slice and Linux client build/test passed | PostgreSQL migration/concurrency and native Windows runtime remain unverified |

## Правило обновления

Новый срез можно отметить проверенным только после проверки на уровне его
требования. Статическая проверка не заменяет native runtime, а unit-тест не
заменяет PostgreSQL concurrency или визуальный browser smoke.

### 2026-10-11 — гостевая очередь допродаж

- Backend: 79 тестов платежей, V2 guest access, metered billing, settlement,
  Clients/Workstations и session API прошли. Отдельный прогон с реальным
  изолированным PostgreSQL: 18 passed, включая сохранение session-bound
  платежа, snapshot тарифа, повторную выдачу grant и фильтр durable grant IDs.
- Новая миграция `20261011_0074` применена на чистом тестовом PostgreSQL
  вместе со всей цепочкой миграций; рабочая БД не изменялась.
- Linux: `dotnet test ./win-client/tests/GameClub.Client.Tests.csproj
  --configuration Debug -p:Platform=x64` — 130 passed; проверены signed
  schema-2 пакет, очередь, restart/dedupe, auto-next, сгорание и server stop.
- Frontend: SaleWorkspace — 10 passed; production build прошёл. Полный
  frontend — 82 passed, 1 failed: незатронутый AnalyticsView-тест
  `loads the additive v2 dashboard and exposes comparison and product states`
  ожидает текст `Состояние данных: Частичные данные`.
- Ruff затронутого backend и `git diff --check` прошли.
- Не выполнены запуск обновлённого Compose и ручной browser/Avalonia
  сценарий допродажи. Unit/adapter checks не доказывают живой UI/gRPC flow.

### 2026-10-11 — включение гостевой допродажи в рабочем dev-стеке

- Причина сохранявшегося POST 409: dev-frontend на 3102 проксировал запросы
  в старый HTTP backend на 8100; в его коде ещё не было payment.session_id.
- Пересобраны backend-migrate, backend-http и backend-grpc; рабочая БД
  обновлена с 0073 до `20261011_0074`. HTTP/gRPC контейнеры healthy.
- Live OpenAPI содержит session_id в GuestSessionPaymentRequest; gRPC
  protobuf содержит session_id и applied_grant_ids; frontend proxy 3102
  возвращает ожидаемый 401 на неавторизованный read-запрос guest-payments.
- Linux runtime клиент пересобран без ошибок/предупреждений. Запущенный
  ранее процесс не перезапускался и требует перезапуска для получения
  допродаж. Новую финансовую операцию для smoke не создавали.

### 2026-10-11 — hover остаток гостевой очереди

- Причина: operator SessionSnapshot содержал только исходный active_tariff,
  без оплаченных допродаж. Добавлен guest_packages через публичный порт
  GuestPaymentLookup; неподтверждённые платежи исключаются.
- Frontend учитывает всю очередь без двойного счёта active_tariff. Server
  projection расходует гостевые минуты по UTC minute boundaries, как V2
  runner; confirmed financial facts этот расчёт не создаёт.
- Backend срез: 75 passed, 1 skipped (PostgreSQL DSN не задан); после
  выравнивания minute boundaries — 73 passed в затронутом срезе. Frontend
  MapScreen/sessionTooltip: 16 passed; production build и Ruff прошли.
- HTTP/gRPC backend пересобраны и обновлены. В пользовательском Chrome
  на localhost:3102 подтверждено отображение гостевого пакета, общего
  остатка и окончания; на момент проверки ранние пакеты уже израсходованы.
- Тест 2 минуты текущего + 6 минут в очереди проверяет сумму 8 и оба тарифа.
  Ручная допродажа/финансовая операция для проверки не создавалась.

### 2026-10-11 — GAMECLUB_LOGIN_GRANT_MINUTES

- Unit: `uv run --directory ./backend pytest tests/test_modules_reservations_sessions.py tests/test_metered_billing.py tests/test_v2_offline_login.py -q` — 64 passed. Проверены grant 0/3, отказ для отрицательного/дробного/overflow значения, существующий grant 5 и списания.
- Ruff check/format изменённых Python-файлов пройдены; Compose config передаёт значение 1 всем backend-сервисам.
- Приложение не перезапускалось; PostgreSQL integration и native Windows smoke не запускались. Graphify update выполнен с предупреждениями парсера frontend и метаданных графа.

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

Проверки этого среза: .NET 161 passed; backend snapshot/login/gRPC portal
12 passed, enrollment/permissions/signature 15 passed; scoped Ruff check/format
passed. Windows runtime и сравнение одинакового snapshot на двух ОС не выполнены.

2026-10-11: отдельная категория `v2.minute` для диагностики
`ConsumeV2DueMinutesAsync`: этап ошибки, ledger/snapshot контекст и stack trace;
успешные minute commits без логирования пустых ticks. Проверено на Linux:
39 V2 access-gate/billing тестов, сборка и `git diff --check`.
Windows-запись client.log на реальном стенде ещё не проверена.

<<<<<<< HEAD
2026-10-12 — operator guest interrupt: backend guest access 2 passed / 1 PostgreSQL test skipped (DSN absent); V2AccessGate/V2LocalLedger/V2BillingLogic 76 passed on Linux. Windows host Release x64 build: 0 warnings/errors. Focused Ruff and git diff --check passed; graphify updated. Live admin→RPC→PC scenario and native Windows not checked.
=======
2026-10-12 — Windows desktop widget HWND_BOTTOM / Win+D recovery:
Windows host build на Linux: 0 warnings, 0 errors; существующие client tests:
161 passed после переноса поверх origin/V2. Native Win+D, повторный Win+D, HUD и Maintenance/tray на Windows
не проверены; Linux build/tests не проверяют user32/Explorer.
Graphify update недоступен: CLI не установлен.
>>>>>>> 6eff53637abdbff36cfb5824892a9a82fb64b00b

### 2026-10-13 — Xbox, реализация первого этапа

Доказательства, команды и ограничения — [план 48](48-xbox-places/PLAN.md).
Backend: 81 passed / 1 skipped в основном срезе, дополнительные Xbox API и
V2 PostgreSQL checks; 167 .NET tests passed. Frontend сценарии и production build
прошли. Chrome проверил создание места/тарифа, продажу и продление с реальным
backend. Миграция 0074 → 0075 на заполненной временной PostgreSQL сохранила
все прежние поля ПК, тарифов, активной сессии и продажи. Общие lint/Analytics
ошибки и старые fixtures описаны в плане, полный clean gate не заявляется.
Промышленная база, native Windows и Sonoff/TV не проверены.

2026-10-13: временно скрыта кнопка «Заблокировать клиент» в панели ПК из-за активного V2 ledger после display.lock; «Прервать сессию» сохранено. Проверено: 8 frontend-тестов (PcPanel/Xbox), production build. Развёртывание и браузер не проверены; существующий зависший ledger этим изменением не исправляется.

Проверка полного frontend набора после бонусной аналитики: 111 passed,
1 прежнее падение AnalyticsView.test.tsx:215 (статус товарного блока).
Изменение ожидания на асинхронное не устраняет ошибку; пробное изменение
откачено. Новые бонусные UI-тесты проходят. Graphify обновлён (прежние
предупреждения парсинга/метаданных сохраняются).


2026-10-17 — гонка выхода V2 и событий пакета исправлена. Серверный stop
может пометить пакет BURNED раньше доставки локальных package_consumed /
package_burned. Entitlements writer принимает такие отложенные факты только
для точного ID/подтверждённого ключа, с совпадающими тарифом, settled-статусом,
остатком и occurred_at не позже ended_at пакета. Legacy-поиск по тарифу для
BURNED не расширен. Терминальный статус/причина/время серверного сгорания
сохраняются: пакет не активируется заново. Ordered session_stopped затем
освобождает бонусный резерв обычной транзакцией Clients.
Регрессионный PostgreSQL-тест сначала воспроизвёл conflict, после исправления
проверяет stop до доставки consumed/burned/stop, повторы, отсутствие повторного
списания, запрет неверных остатков/тарифа и фактов после stop. Проверено:
26 passed, 3 broker-smoke skipped в test_v2_bonus_budget_postgres.py и
 test_v2_reconciliation_postgres.py. Клиентский текст выхода теперь поясняет,
что освобождение бонусов ждёт подтверждения списаний. Рабочие сервисы не
пересобирались; старый зависший резерв автоматически не освобождался.


2026-10-17 — восстановлен зависший резерв и проверено повторное включение.
В работающей базе резерв 7000 сотых бонуса принадлежал старой completed-сессии;
новая получила grant всего 39 сотых и закономерно оплатила минуту 39 бонусными
и 61 денежной копейкой при цене 100. Пересобран только v2-client-facts
(`docker compose up -d --no-deps --build v2-client-facts`). Из v2.failed-events
повторно доставлены исходные package_burned seq5 и session_stopped seq6 только
этой сессии, без изменения payload/ID и с проверкой связности hash-chain.
Оба факта accepted; резерв старой сессии освобождён, общий бонусный остаток
7000 сохранён, reserved=0. Прямых SQL-исправлений денег не было.
Регрессии: PostgreSQL enable → bonus minute → disable → money minute → enable
в той же сессии проходит; при 100% лимите деньги меняются только за выключенную
минуту. C# coordinator повторяет этот сценарий и сохраняет денежный баланс
при достаточном бонусном бюджете. 2 backend tests passed (новый сценарий и
гонка выхода), 1 focused C# test passed на Linux. Предупреждение xUnit1031
в прежнем AvaloniaHostSmokeTests.cs:289 остаётся. Native Windows не проверялся.

2026-10-17: автообновление бонусного резерва — 2 focused Linux C# tests passed:
пополнение резерва только при включённой оплате и доступных бонусах; отмена
потерянного включения не приводит к повторному включению при refresh. XAML
скомпилирован в составе test build. Внешний вид увеличенного переключателя
на Windows вручную не проверен. Прежнее предупреждение xUnit1031 остаётся.
