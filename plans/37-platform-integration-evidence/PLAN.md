# План 37 — platform, integration и release evidence

Статус: `in_progress`
Приоритет: `P0`
Владельцы: `backend/`, `frontend/`, `win-client/`
Зависимости: `28-integration-checks`, `30-entitlements-meter`,
`31-settlement-reconciliation`, `32-session-snapshot-entry`,
`33-session-transfer`, `34-durable-offline`, `35-frontend-contract-consumers`,
`36-winui-contract-consumers`

## Цель

Закрыть доказательства, которые нельзя получить unit/source-level проверкой:
реальная PostgreSQL/Redis интеграция, миграции после `0039`, Compose smoke,
browser flow, native Windows runtime, kiosk boundary и production security
preflight.

## Входит в план

- PostgreSQL concurrency/transaction/migration upgrade и rollback rehearsal;
- Redis/Dramatiq replay/retry checks;
- Compose rebuild/readiness/HTTP/gRPC/worker smoke;
- browser matrix и headed operator flows;
- Windows native build, publish, widget/tray, reconnect, transfer, offline;
- Assigned Access/Shell Launcher reversible provisioning;
- enrollment/token/TLS/secret/logging review;
- обновление [`plans/VERIFICATION.md`](../VERIFICATION.md) только evidence.

## Реализовано в текущем срезе

Локально повторены backend proto generation, Ruff, frontend typecheck/build и
backend suite: `125 passed, 12 skipped` без DSN и `137 passed` с dev
PostgreSQL/Redis DSN. Compose rebuild применил migrations до `20260902_0046`,
HTTP/headed smoke подтвердил login, dashboard, map, context panel, session
snapshot и entry decision, а внешний gRPC smoke подтвердил health и
авторизованный snapshot. Специализированные package/debit/transfer/offline
concurrency, browser matrix и Windows native evidence ещё не выполнены.

## Не входит

- production deployment без отдельного approval;
- реальные payment providers и webhooks;
- irreversible kiosk change на рабочем ПК;
- утверждение source-level результата как native runtime.

## Порядок задач

1. [ ] Подготовить отдельную dev/test PostgreSQL и Redis с backup/restore
   точкой; не использовать production secrets.
2. [ ] Выполнить migration upgrade до текущей головы `20260902_0046`, проверить constraints,
   indexes, rollback rehearsal и persistence новых flows.
3. [x] Запустить все skipped integration/concurrency tests и задокументировать
   каждую оставшуюся причину пропуска.
4. [ ] Повторить Compose rebuild/readiness и smoke payment, guest, entry,
   entitlement, snapshot и gRPC activation.
5. [ ] Выполнить frontend headed browser matrix и проверить duplicate/error/
   stale/offline/confirmation states.
6. [ ] На целевой Windows-машине выполнить `verify-windows.ps1`, native build,
   portable publish и сценарии из `REAL-PC-VERIFICATION.md`.
7. [ ] Отдельно провести reversible Assigned Access/Shell Launcher rehearsal
   под ограниченным пользователем с documented restore.
8. [ ] Проверить secrets, tokens, certificates, logs, AppData, enrollment
   rebind/rate-limit и restart/recovery policy.
9. [x] Обновить verification matrix, summary и статус child plans только по
   фактическим результатам; зафиксировать known gaps и release blockers.

## Критерии готовности

- все обязательные P0 flows имеют evidence требуемого уровня;
- migrations и concurrency подтверждены реальной PostgreSQL;
- Compose и browser smoke проходят после текущего migration head;
- Windows native и kiosk границы проверены на целевой машине обратимо;
- ни один skipped/native/source-level чек не помечен как runtime success;
- итоговый release report содержит blockers, owner и следующий action.

## Проверки и evidence

- `pytest` с `GAMECLUB_TEST_POSTGRES_DSN` и `GAMECLUB_TEST_REDIS_URL`;
- `alembic upgrade head/current`, Compose logs/readiness и gRPC smoke;
- `npm run typecheck`, `npm run build`, headed Playwright matrix;
- Windows `verify-windows.ps1`, publish и manual checklist;
- security/backup/restore/recovery review.

## Открытые решения

- поддерживаемые browser/Windows versions и минимальный smoke matrix;
- критерии нагрузки для polling/realtime;
- кто утверждает kiosk provisioning и restore перед production.
