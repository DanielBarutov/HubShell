# Verification matrix

Дата последней проверки: `2026-08-30`.

Документ разделяет фактически проверенное поведение и то, что пока подтверждено
только исходниками или требует другой платформы.

| Срез | Что проверено | Результат | Граница доказательства |
| --- | --- | --- | --- |
| Backend foundation и модули | Ruff, форматирование, unit/API/contract tests, metered billing, manager credential, lockdown policy, analytics и payment-methods | `104 passed, 12 skipped` | Текущий локальный suite без integration DSN; PostgreSQL concurrency остаётся отдельной проверкой |
| PostgreSQL schema | Alembic migration chain, tariff metering, workstation manager verifier, lockdown policy и payment methods | `20260830_0031 (head)` | Dev-база мигрирована; production backup/rollback не проверялись |
| Guest persistence | Guest CRUD/search и ссылки `guest_id` в Reservation/Session | успешно | Memory/API и PostgreSQL integration suite |
| Cash producer/approval boundary | provider-neutral producers, approvals, HTTP/gRPC contracts | успешно | Unit/API/contract suite; реальные provider webhook не подключены |
| gRPC | generated protobuf, analytics/workstation/business service registration, auth/audit и TLS policy | успешно | Dev analytics overview smoke и ранее выполненный secure smoke; production certificate issuance не проверялась |
| Frontend | TypeScript typecheck и Vite production build; единый тёмный shell, topbar, dashboard/map/catalog/panel visual system | успешно | Headed snapshot smoke карты с фиксированной карточкой и отдельным scroll-frame; полный browser matrix и realtime transport ещё не проверялись |
| Frontend live flow | operator login, persistent refresh после reload, spatial map, tariff/product checkout idempotency, catalog, расширенная analytics overview, настройки зон и payment-methods CRUD | успешно | Playwright headed smoke на локальном Compose; полный browser matrix и realtime transport ещё не проверялись |
| Windows client | структура слоёв, protobuf consumers, tariff payload, app-level access-gate, `SessionLocked`, Ctrl+Alt+P, heartbeat manager verifier/lockdown policy, self-stop/restart flow и C# test project в solution | source-level успешно | Native compile/runtime и C# tests пока не доказываются; требуется Windows/.NET |
| Windows publish | воспроизводимый self-contained publish script с проверкой ожидаемого EXE | source-level успешно | Сам publish и запуск требуют Windows/.NET/Windows SDK |
| Windows native | WinUI 3 restore/build, access-gate под обычным пользователем, reconnect, темы и restart | не проверено | .NET 8 SDK восстановлен локально, но WindowsAppSDK `XamlCompiler.exe` требует Windows; native build/runtime запускать на Windows |
| Docker Compose | config validation, frontend/backend image rebuild, full stack startup, readiness, migration `20260830_0031`, policy API smoke, billing worker/scheduler, auth, payment methods and Redis workstation snapshot TTL | успешно | Локальный compose запущен; native Windows client в compose не входит |
| Catalog product edit regression | реальный PUT существующего товара через frontend proxy после пересборки backend | `200 OK` | Проверен товар `Кофе`; отдельная PostgreSQL integration matrix без test DSN по-прежнему пропускается |
| Product sales and analytics | продажа товара клиенту из баланса, уменьшение остатка, snapshots цены/себестоимости/категории, overview и client analytics через live HTTP; KPI, дни/часы, маржа, оплаты, зоны/ПК/тарифы/категории и клиентская статистика в UI | успешно | Smoke на локальном Compose; cash/guest сценарий дополнительно покрыт unit/API tests |
| Live metered sessions | per-minute tariff, free grace minutes, delta debit, insufficient-balance stop, sequential block quantity и session meter persistence | успешно | Unit suite и PostgreSQL-backed suite; guest без client ledger остаётся cashier flow |
| Operator map quick operations | карта как главный экран, PC context menu, tariff mini-cards, guest/client selection, inline product sale and top-up | успешно | Playwright headed smoke на локальном Compose; device command runtime требует Windows |

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
