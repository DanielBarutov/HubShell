# Verification matrix

Дата последней проверки: `2026-09-02`.

Документ разделяет фактически проверенное поведение и то, что пока подтверждено
только исходниками или требует другой платформы.

| Срез | Что проверено | Результат | Граница доказательства |
| --- | --- | --- | --- |
| Backend foundation и модули | Ruff, unit/API/contract tests, metered billing, package windows/auto-next, snapshot, transfer, offline replay, settlement review, manager credential, lockdown policy, analytics, payment parts, guest paid-start и entry decision | `125 passed, 12 skipped` без DSN; `137 passed` с dev PostgreSQL/Redis DSN (2026-09-02) | Dedicated package/debit/transfer/offline PostgreSQL concurrency и fault injection остаются отдельной проверкой |
| PostgreSQL schema | Alembic migration chain through active-client, payment-parts, entitlement, guest-payment, login-grant, transfer и offline migrations | `20260902_0046 (head)` по `alembic heads`; Compose migrate применил chain на dev PostgreSQL | Production backup/rollback и dedicated concurrency suite не проверялись |
| Guest persistence | Guest CRUD/search и ссылки `guest_id` в Reservation/Session | успешно | Memory/API contract checks; PostgreSQL concurrency matrix пропущена без DSN |
| Cash producer/approval boundary | provider-neutral producers, approvals, HTTP/gRPC contracts | успешно | Unit/API/contract suite; реальные provider webhook не подключены |
| gRPC | generated protobuf, client portal entitlement queue/explicit activation, analytics/workstation/business registration, auth/audit и TLS policy; внешний `SystemService/GetHealth` и авторизованный `SessionService/GetSnapshot` через `:51051` | успешно в текущем Compose smoke | production certificate issuance/TLS deployment и full gRPC flow matrix не проверялись |
| Frontend | TypeScript typecheck и Vite production build; единый тёмный shell, topbar, dashboard/map/catalog/panel visual system | успешно | Headed snapshot smoke карты с фиксированной карточкой и отдельным scroll-frame; полный browser matrix и realtime transport ещё не проверялись |
| Frontend live flow | operator login, persistent refresh после reload, spatial map, tariff/product checkout idempotency, catalog, расширенная analytics overview, настройки зон и payment-methods CRUD | успешно; текущий headed smoke после login открыл dashboard, map и PC context panel | Полный browser matrix, snapshot/transfer/offline UI сценарии и realtime transport ещё не проверялись |
| Windows client | структура слоёв, protobuf consumers, snapshot/transfer gateway, DPAPI journal/sequence, package notification, pre-auth gate, post-auth widget/tray, portal package queue/activation source и self-stop/restart flow | source-level успешно | entry login integration, generated compile/runtime, reconnect/power-loss и native Windows пока не доказаны |
| Windows publish | воспроизводимый self-contained publish script и single-file portable EXE через `build-portable-exe.ps1` | source-level успешно | Сам publish и запуск требуют Windows/.NET/Windows SDK; один EXE ещё не запускался на целевой машине |
| Windows native | WinUI 3 restore/build, access-gate под обычным пользователем, reconnect, темы и restart | не проверено | .NET 8 SDK восстановлен локально, но WindowsAppSDK `XamlCompiler.exe` требует Windows; native build/runtime запускать на Windows |
| Docker Compose | config validation, rebuild, PostgreSQL/Redis readiness, migrations `20260902_0033`→`20260902_0046`, backend HTTP health/auth, live session snapshot и entry decision, frontend startup, worker/scheduler | успешно в текущем прогоне 2026-09-02 | Полный gRPC external smoke, browser matrix, backup/rollback и native Windows client остаются отдельными проверками |
| Catalog product edit regression | реальный PUT существующего товара через frontend proxy после пересборки backend | `200 OK` | Проверен товар `Кофе`; отдельная PostgreSQL integration matrix без test DSN по-прежнему пропускается |
| Product sales and analytics | продажа товара клиенту из баланса, уменьшение остатка, snapshots цены/себестоимости/категории, overview и client analytics через live HTTP; KPI, дни/часы, маржа, оплаты, зоны/ПК/тарифы/категории и клиентская статистика в UI | успешно | Smoke на локальном Compose; cash/guest сценарий дополнительно покрыт unit/API tests |
| Live metered sessions | per-minute tariff, tariff-configured free minutes, separate device login-grant subtraction, package consumption/auto-next, local time-window eligibility, delta debit, insufficient-balance stop и session meter persistence | успешно на source/unit slice | PostgreSQL-backed debit/package concurrency tests пропущены; common cross-repository UoW не доказан |
| Operator map quick operations | карта как главный экран, PC context menu, tariff mini-cards, guest/client selection, inline product sale and top-up | успешно | Playwright headed smoke на локальном Compose; device command runtime требует Windows |
| Product contract audit | сравнение backend/frontend/win-client product contracts с кодом, CODEX и планами; implementation progress зафиксирован в плане 29 | source/unit + текущий Compose/headed slice реализован | PostgreSQL concurrency/fault injection, native Windows/kiosk и production security evidence остаются незакрыты |

Подробная последовательность проверки физического Windows-ПК находится в
[../win-client/docs/REAL-PC-VERIFICATION.md](../win-client/docs/REAL-PC-VERIFICATION.md).

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
cd win-client
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

## Правило обновления

Новый срез можно отметить проверенным только после проверки на уровне его
требования. Статическая проверка не заменяет native runtime, а unit-тест не
заменяет PostgreSQL concurrency или визуальный browser smoke.
