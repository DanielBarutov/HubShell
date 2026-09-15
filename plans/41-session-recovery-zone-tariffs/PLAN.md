# План 41 — восстановление сессии и зона тарифов

Статус: `in_progress` — source/unit/API/gRPC/frontend срез закрыт; native Windows
restart/reconnect smoke остаётся открытым
Владельцы: `backend/`, `frontend/`, `win-client/`
Зависимости: [`04-auth-security`](../04-auth-security/PLAN.md),
[`03-catalog-time-tariffs`](../03-catalog-time-tariffs/PLAN.md),
[`06-sessions`](../06-sessions/PLAN.md),
[`32-session-snapshot-entry`](../32-session-snapshot-entry/PLAN.md),
[`34-durable-offline`](../34-durable-offline/PLAN.md),
[`40-avalonia-product-flows`](../40-avalonia-product-flows/PLAN.md)

## Цель

Закрыть два пользовательских сбоя текущего среза:

1. после перезапуска клиента/ПК или временной потери связи восстановить уже
   активную server-backed сессию на этом игровом месте без повторного ввода
   пароля;
2. показывать и принимать только тарифы, совместимые с зоной игрового места,
   одинаково в Win-клиенте, operator checkout и backend write-path.

## Контрактные решения

- Heartbeat остаётся источником обнаружения активной сессии на workstation.
- Для именованной active session backend предоставляет отдельный
  device-authenticated `ClientPortalService.Resume`.
- Resume разрешается только для active session, принадлежащей тому же
  workstation/device. Гостевая сессия не выпускает client token: heartbeat
  только возвращает session snapshot и открывает guest UI.
- Клиентский пароль и portal access token не сохраняются на диск. Явный logout
  сначала останавливает server session и поэтому не может быть автоматически
  восстановлен следующим heartbeat.
- Тариф с `group_id = null` является общим для всех зон. Тариф с конкретным
  `group_id` выдаётся и принимается только в той же зоне.
- Operator catalog management может видеть все версии для настройки, но sale
  checkout получает только тарифы текущей workstation. Win-client portal
  snapshot получает только тарифы текущей workstation.
- UI-фильтр не является границей безопасности: session start, guest payment,
  client package purchase и activation дополнительно проверяют зону на backend.

## Задачи

1. [x] Добавить versioned gRPC resume contract и backend lookup active session
   через device/workstation.
2. [x] Подключить resume к Win-client heartbeat и восстановить portal/access
   state после restart/reconnect.
3. [x] Добавить zone-scoped tariff read model для operator sale и Win portal.
4. [x] Добавить backend zone guards для session start, guest payment и package
   purchase/activation.
5. [x] Добавить unit/API/gRPC/frontend checks; native Windows restart/power-loss
   smoke оставить отдельной platform evidence.

## Фактические проверки 2026-09-15

- `backend`: `uv run pytest -q` — `145 passed, 18 skipped` и 6 известных
  pre-existing contract-layout failures в dirty checkout; отдельные тесты
  этого среза проверяют HTTP-фильтр `group_id`, session start и guest payment
  zone guards, а также gRPC resume по active session;
- `backend`: `uv run ruff check` и `ruff format --check` для затронутых файлов;
- `frontend`: `npm run build` (включает TypeScript build и Vite production build);
- `frontend`: server-backed коллекции operator UI переведены в Redux workspace;
  refresh thunk и bookings thunk принимают request-id, поэтому поздний ответ не
  может перезаписать более свежий снимок; sale checkout фильтрует только block
  тарифы текущей зоны;
- `win-client`: source wiring проверен, но `dotnet` отсутствует в текущем Linux
  окружении, поэтому C# build и native restart/power-loss не утверждаются.

## Граница доказательства

Unit, API, gRPC, TypeScript и Linux Avalonia checks подтверждают source/runtime
контракт. Они не заменяют native Windows power-loss/restart/reconnect smoke.
