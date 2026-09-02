# План 35 — frontend consumers новых backend-контрактов

Статус: `in_progress`
Приоритет: `P0`
Владелец: `frontend/`
Зависимости: `32-session-snapshot-entry`, `33-session-transfer`,
`34-durable-offline`, `31-settlement-reconciliation`,
[`frontend/PRODUCT-CONTRACT.md`](../../frontend/PRODUCT-CONTRACT.md)

## Цель

Довести operator UI от typed DTO до полного server-backed поведения карты,
checkout и статусов ПК. Frontend не вычисляет reservation lock, совместимость
пакета, остаток, settlement или offline result.

## Текущее состояние

Typed BFF DTO, guest payment confirmation и mixed product sale уже добавлены.
Snapshot, queue, entry refusal, transfer confirmation, settlement review и
offline/stale workstation fields подключены в основные operator consumers;
headed route smoke и sale-confirmation visual evidence добавлены в текущем
срезе.

## Реализовано в текущем срезе

`api.ts` содержит typed snapshot, entry, transfer и settlement states. Карточка
ПК обновляет server snapshot и показывает active package, queue, meter и tariff;
entry start проверяет backend decision; transfer требует explicit confirm;
needs-review не показывается как успешная продажа; offline card показывает
последний heartbeat. TypeScript typecheck и production build проходят.

## Входит в план

- карта/карточка ПК с session snapshot и ordered queue;
- server `EntryDecision` banner с причиной и интервалом брони;
- guest flow workstation → tariff → payment → confirmation → session start;
- top-up/sale/guest parts с явным pending/review/error state;
- transfer offer/confirm/result;
- stale/offline card с last client/time/status;
- idempotent submit, refresh после 403 и недопущение двойного финансового action.

## Не входит

- прямой backend/gRPC/Redis доступ из браузера;
- локальный тарифный расчёт или самостоятельный entry check;
- VNC/remote control и новый order/basket domain;
- полноценный realtime transport без отдельного решения.

## Порядок задач

1. [x] Добавить typed API methods для snapshot, entry decision, transfer и
   offline/reconciliation states с generated response fixtures.
2. [x] Расширить карту и PC context panel: client, active tariff/package,
   remaining, queue, server timestamp и stale state.
3. [x] Добавить entry banner и named/guest semantics; текст причины брать из
   backend enum/message mapping.
4. [x] Завершить guest checkout с подтверждением payment fact до start/unlock;
   mixed guest payment разрешить только когда backend это явно поддерживает.
5. [x] Отобразить pending/needs_review settlement и блокировать повторную
   отправку до server result.
6. [x] Реализовать transfer modal с explicit confirm и duplicate-safe result.
7. [x] Отобразить offline ПК и последний server snapshot без создания новых
   offline session/payment действий.
8. [x] Провести headed smoke основных маршрутов и обновить visual evidence;
   подтверждены login/dashboard/map/PC context, catalog sale confirmation,
   bookings, clients, analytics, cash, settings и offline action guards.

## Критерии готовности

- карточка места отражает только server DTO;
- оператор видит queue, snapshot и entry reason в контексте места;
- guest session не стартует до подтверждённой оплаты;
- transfer и settlement имеют явные success/pending/review/error states;
- offline PC остаётся видимым и не создаёт ложный success.

## Остаток и release blocker

После актуальной пересборки выполнен headed smoke основных маршрутов,
catalog-sale confirmation и offline action guards; screenshot сохранён в
`output/playwright/2026-09-02-map.png`. Полная matrix queue/entry/guest
payment/duplicate retry/transfer и accessibility/focus checks всё ещё требует
отдельного browser-run. Полный realtime transport не входит в текущий срез;
polling остаётся временной реализацией.

## Проверки и evidence

- TypeScript typecheck/build;
- API contract tests и mocked error states;
- headed Playwright: queue, entry lock, guest paid-start, duplicate retry,
  transfer and offline card;
- accessibility/focus/keyboard checks для confirmation dialogs.

## Открытые решения

- точная компоновка queue в карте без создания новых сущностей;
- copy для `needs_review` и права supervisor action;
- polling interval до решения о realtime.
