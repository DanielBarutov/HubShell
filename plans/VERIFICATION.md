# Verification matrix

Дата последней проверки: `2026-09-02`.

Документ разделяет фактически проверенное поведение и то, что пока подтверждено
только исходниками или требует другой платформы.

| Срез | Что проверено | Результат | Граница доказательства |
| --- | --- | --- | --- |
| Backend foundation и модули | Ruff, unit/API/contract tests, metered billing, package windows/auto-next, locked consumption delta, snapshot/heartbeat, transfer, offline replay, settlement review/retry, manager credential, lockdown policy, analytics, payment parts, guest paid-start и entry decision | `139 passed, 18 skipped` без DSN; `157 passed` с dev PostgreSQL/Redis DSN (2026-09-02) | DSN suite включает PostgreSQL mixed settlement fault/idempotency, package locked-delta, transfer two-target concurrency и offline duplicate-debit; production cross-owner UoW остаётся policy gap |
| PostgreSQL schema | Alembic migration chain through active-client, payment-parts, entitlement, guest-payment, login-grant, transfer, offline и settlement retry metadata migrations | `20260902_0048 (head)`; upgrade/rollback/upgrade rehearsal, constraints/column check и isolated backup/restore прошли | Production backup policy и cross-owner transaction boundary не утверждены |
| Guest persistence | Guest CRUD/search и ссылки `guest_id` в Reservation/Session | успешно | Memory/API contract checks; PostgreSQL concurrency matrix пропущена без DSN |
| Cash producer/approval boundary | provider-neutral producers, approvals, HTTP/gRPC contracts | успешно | Unit/API/contract suite; реальные provider webhook не подключены |
| gRPC | generated protobuf, client portal entitlement queue/explicit activation, analytics/workstation/business registration, auth/audit и TLS policy; внешний `SystemService/GetHealth` и авторизованный `SessionService/GetSnapshot` через `:51051` | успешно в текущем Compose smoke, `gameclub-backend:ok:0.1.0`, snapshot schema `1` | production certificate issuance/TLS deployment и full gRPC flow matrix не проверялись |
| Frontend | TypeScript typecheck и Vite production build; единый тёмный shell, topbar, dashboard/map/catalog/panel visual system | успешно | Headed snapshot smoke карты с фиксированной карточкой и отдельным scroll-frame; полный browser matrix и realtime transport ещё не проверялись |
| Frontend live flow | operator login, persistent refresh после reload, spatial map, tariff/product checkout idempotency, catalog sale confirmation, analytics overview, settings и payment-methods CRUD | успешно; headed smoke прошёл основные routes, PC context и offline sale/booking guards disabled | Полный browser matrix, duplicate/error/queue/entry/transfer/guest UI, accessibility и realtime transport ещё не проверялись |
| Windows client | структура слоёв, protobuf consumers, server EntryDecision в portal login/register и session start, snapshot/transfer gateway, DPAPI journal/sequence, package notification, pre-auth gate, post-auth widget/tray и restart flow | source-level успешно; generated protobuf signature проверена временным protoc | WindowsAppSDK compile/runtime, reconnect/power-loss и native Windows пока не доказаны |
| Windows publish | воспроизводимый self-contained publish script и single-file portable EXE через `build-portable-exe.ps1` | source-level успешно | Сам publish и запуск требуют Windows/.NET/Windows SDK; один EXE ещё не запускался на целевой машине |
| Windows native | WinUI 3 restore/build, access-gate под обычным пользователем, reconnect, темы и restart | не проверено | .NET 8 SDK восстановлен локально, но WindowsAppSDK `XamlCompiler.exe` требует Windows; native build/runtime запускать на Windows |
| Docker Compose | config validation, backend rebuild/restart, PostgreSQL/Redis readiness, migration `20260902_0048`, backend HTTP health/auth/entry decision, frontend startup, worker/scheduler | успешно в текущем прогоне 2026-09-02 | gRPC health/snapshot smoke и backup/rollback прошли; browser matrix и native Windows client остаются отдельными проверками |
| Catalog product edit regression | реальный PUT существующего товара через frontend proxy после пересборки backend | `200 OK` | Проверен товар `Кофе`; отдельная PostgreSQL integration matrix без test DSN по-прежнему пропускается |
| Product sales and analytics | продажа товара клиенту из баланса, уменьшение остатка, snapshots цены/себестоимости/категории, overview и client analytics через live HTTP; KPI, дни/часы, маржа, оплаты, зоны/ПК/тарифы/категории и клиентская статистика в UI | успешно | Smoke на локальном Compose; cash/guest сценарий дополнительно покрыт unit/API tests |
| Live metered sessions | per-minute tariff, tariff-configured free minutes, separate device login-grant subtraction, package consumption/auto-next, local time-window eligibility, delta debit, insufficient-balance stop и session meter persistence | успешно на source/unit slice; PostgreSQL DSN suite включает locked package delta и offline duplicate debit | cross-repository settlement UoW и fault injection не доказаны |
| Operator map quick operations | карта как главный экран, PC context menu, tariff mini-cards, guest/client selection, inline product sale and top-up | успешно | Playwright headed smoke на локальном Compose; device command runtime требует Windows |
| Product contract audit | сравнение backend/frontend/win-client product contracts с кодом, CODEX и планами; implementation progress зафиксирован в плане 29 и планах 31–37 | source/unit + Compose/HTTP/gRPC/headed slice реализован; DSN suite добавила package/transfer/offline/settlement evidence; 11 subitems сведены в `EVIDENCE-20260902.md` | native Windows/kiosk, full browser/accessibility matrix и production security evidence остаются незакрыты |

Сборка и startup diagnostics: [../win-client/docs/WINDOWS-BUILD-AND-RUN.md](../win-client/docs/WINDOWS-BUILD-AND-RUN.md).
Функциональный smoke: [../win-client/docs/REAL-PC-VERIFICATION.md](../win-client/docs/REAL-PC-VERIFICATION.md).

Детальный evidence текущего среза планов 31–37 находится в
[37-platform-integration-evidence/EVIDENCE-20260902.md](37-platform-integration-evidence/EVIDENCE-20260902.md).

## Повторяемые команды

Backend:

```text
cd backend
GAMECLUB_TEST_POSTGRES_DSN=... GAMECLUB_TEST_REDIS_URL=... uv run pytest -q
uv run ruff format --check src tests
uv run ruff check .
GAMECLUB_POSTGRES_DSN=... uv run alembic current
```

Frontend:

```text
cd frontend
npm run typecheck
npm run build
```

Windows native:

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

## Правило обновления

Новый срез можно отметить проверенным только после проверки на уровне его
требования. Статическая проверка не заменяет native runtime, а unit-тест не
заменяет PostgreSQL concurrency или визуальный browser smoke.
