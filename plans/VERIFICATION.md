# Verification matrix

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
