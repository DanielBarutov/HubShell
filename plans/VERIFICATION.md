# Verification matrix

Дата последней проверки: `2026-09-17`.

Документ разделяет фактически проверенное поведение и то, что пока подтверждено
только исходниками или требует другой платформы.

| Срез | Что проверено | Результат | Граница доказательства |
| --- | --- | --- | --- |
| Backend foundation и модули | Ruff, unit/API/contract tests, metered billing, package windows/auto-next, locked consumption delta, snapshot/heartbeat, transfer, offline replay, settlement review/retry, manager credential, lockdown policy, analytics, payment parts, guest paid-start и entry decision; guest `active_tariff` snapshot с server-calculated remaining time; shared Dramatiq broker и dedicated metering queue | `153 passed, 18 skipped` без DSN; contract-layout assertions обновлены под текущие API/Avalonia boundaries; bounded-context split и Russian docstring guard проходят | DSN suite включает PostgreSQL mixed settlement fault/idempotency, package locked-delta, transfer two-target concurrency и offline duplicate-debit; production cross-owner UoW остаётся policy gap |
| PostgreSQL schema | Alembic migration chain through active-client, payment-parts, entitlement, guest-payment, login-grant, transfer, offline и settlement retry metadata migrations | `20260902_0048 (head)`; upgrade/rollback/upgrade rehearsal, constraints/column check и isolated backup/restore прошли | Production backup policy и cross-owner transaction boundary не утверждены |
| Guest persistence | Guest CRUD/search и ссылки `guest_id` в Reservation/Session | успешно | Memory/API contract checks; PostgreSQL concurrency matrix пропущена без DSN |
| Cash producer/approval boundary | provider-neutral producers, approvals, HTTP/gRPC contracts | успешно | Unit/API/contract suite; реальные provider webhook не подключены |
| gRPC | generated protobuf, client portal entitlement queue/explicit activation, analytics/workstation/business registration, auth/audit и optional TLS policy; `SessionSnapshot.active_tariff` с названием/количеством/elapsed/remaining; внешний `SystemService/GetHealth` и авторизованный `SessionService/GetSnapshot` через `:51051` | generated contract и mapping-тесты успешно; Compose rebuild/health успешно | external TLS deployment и full gRPC flow matrix не проверялись; private-LAN insecure transport допускается |
| Frontend | TypeScript typecheck и Vite production build; единый тёмный shell, topbar, dashboard/map/catalog/panel visual system | успешно | Headed snapshot smoke карты с фиксированной карточкой и отдельным scroll-frame; полный browser matrix и realtime transport ещё не проверялись |
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
| Live metered sessions | per-minute tariff, tariff-configured free minutes, separate device login-grant subtraction, package consumption/auto-next, local time-window eligibility, delta debit, insufficient-balance stop и session meter persistence | успешно на source/unit slice; PostgreSQL DSN suite включает locked package delta и offline duplicate debit | cross-repository settlement UoW и fault injection не доказаны |
| Operator map quick operations | карта как главный экран, PC context menu, tariff mini-cards, guest/client selection, inline product sale and top-up | успешно | Playwright headed smoke на локальном Compose; device command runtime требует Windows |
| Product contract audit | сравнение backend/frontend/win-client product contracts с кодом, CODEX и планами; implementation progress зафиксирован в плане 29 и планах 31–37 | source/unit + Compose/HTTP/gRPC/headed slice реализован; DSN suite добавила package/transfer/offline/settlement evidence; 11 subitems сведены в `EVIDENCE-20260902.md` | native Windows/kiosk, full browser/accessibility matrix и production security evidence остаются незакрыты |
| Plan 44 phase 0/early F-01/F-02/F-03/F-06/F-07/F-10/F-11 | контракты для client groups/debt policy, payment-method independence, package fallback, stop acknowledgement, server-anchored timer и notification boundaries; regression matrix F-01…F-13; positive-balance fallback, Core stop-order, countdown projection, top-up snapshot, active-client deposit/sale guards и package UI filtering | contracts, owner plans и matrix обновлены; полный backend suite `162 passed, 19 skipped`, F-06 snapshot/meter slice `22 passed`, F-10 session guard slice `39 passed`, Ruff clean; Win Core `39 passed`, включая projection, stop-order и package UI tests; F-06 projection filter `3 passed`; frontend `21 passed` и typecheck, включая DepositPanel и active-client sale guards; proto layout `19 passed` | F-01b/group debt, F-02 Windows visual timer, F-03 full access-gate/restart, F-06 live portal polling/package-source smoke, F-07 live/headed path, F-10 отдельный channel API/Win self-service и F-11 Avalonia/Windows visual smoke ещё требуют evidence |
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

## Правило обновления

Новый срез можно отметить проверенным только после проверки на уровне его
требования. Статическая проверка не заменяет native runtime, а unit-тест не
заменяет PostgreSQL concurrency или визуальный browser smoke.
