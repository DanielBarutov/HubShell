# План 36 — WinUI snapshot, transfer и offline consumers

Статус: `in_progress`
Приоритет: `P0`
Владелец: `win-client/`
Зависимости: `30-entitlements-meter`, `32-session-snapshot-entry`,
`33-session-transfer`, `34-durable-offline`, `27-portable-deployment`,
[`win-client/PRODUCT-CONTRACT.md`](../../win-client/PRODUCT-CONTRACT.md)

## Цель

Подключить WinUI к server snapshot, entry decision, package lifecycle,
transfer и durable offline protocol. Клиент остаётся thin consumer: не считает
цену, совместимость, 30 минут, остаток или settlement.

## Текущее состояние

Pre-auth gate, right-aligned compact post-auth widget/tray without avatar, portal
tariff purchase/package queue/explicit activation,
snapshot gateway, heartbeat callback, transfer UI и durable offline journal есть
на source-level. Portal login/register и command-driven session start теперь
передают workstation/client через server `EntryDecision`; native compile/runtime
пока не доказаны.

## Реализовано в текущем срезе

Добавлены C# snapshot/entry/transfer/offline DTO, gateway methods и coordinator
heartbeat/replay wiring. MainViewModel показывает active-package/auto-next
уведомление с закрытием через 3 секунды, transfer offer/confirm, блокирует
login при offline/reconnecting и очищает portal token при отказе EntryDecision.
Journal шифрует JSONL и sequence state через DPAPI. Source-level tests/fakes
обновлены; native Windows build не запускался из-за отсутствующего .NET SDK на
host.

## Входит в план

- login response/heartbeat с `SessionSnapshot` и `EntryDecision`;
- активный пакет, queue и auto-next notifications;
- explicit activation saved package при новом входе;
- session stop/logout/restart по server result;
- transfer offer/confirm на новом ПК;
- compact widget без выбора темы пользователем и без фиктивной брони; карточка
  бронирования строится только из совпадающей будущей подтверждённой брони
  snapshot;
- durable journal, reconnect batch и result UI;
- stale/offline lock states и безопасный no-new-session rule.

## Не входит

- Windows shell replacement в приложении;
- произвольные process/shell commands;
- локальный balance/tariff/zone calculation;
- Assigned Access implementation внутри WinUI.

## Порядок задач

1. [x] Обновить generated C# DTO и gateway interfaces после фиксации protobuf;
   сохранить backward-compatible handling неизвестных enum/fields.
2. [x] Встроить snapshot/entry result в login/register, command-driven session
   start и heartbeat; до server result показывать locked/reconnecting state.
3. [x] Реализовать package activation/auto-next notification: self-closing
   через 3 секунды и собственная close button.
4. [x] Связать stop/exhaustion/logout с server result, burn/lock/restart policy;
   не выполнять финансовое действие локально.
5. [x] Добавить transfer offer/confirm/result и старый-PC restart ACK.
6. [x] Реализовать durable journal storage, batch replay и partial-result UI.
7. [x] Проверить no-new-session offline, clock-skew/duplicate/out-of-order
   backend guards и отсутствие передачи secrets/лишней PII в client DTO на
   source-level; native disk/crash/filesystem smoke остаётся Windows blocker.
8. [x] Добавить unit/source contract tests coordinator/gateway/entry refusal и
   обновить manual Windows scenarios; native execution этих сценариев требует
   целевого Windows ПК.

## Критерии готовности

- до auth/offline-before-login нет пользовательской рабочей сессии;
- entry refusal и snapshot приходят от backend;
- package activation/auto-next не приводит к двойному расходу;
- transfer требует подтверждения и не создаёт второй active session;
- journal переживает restart и replay идемпотентен;
- после exhaustion/stop клиент блокируется или перезапускается по server result.

## Остаток и release blocker

Нужно выполнить generated C# + XAML compile на Windows, native x64/reconnect/
power-loss smoke, проверить local offline limit и restart при недоступном
backend на целевом ПК. Linux подтверждает source/generated-protobuf signature,
но не заменяет WindowsAppSDK runtime.

## Проверки и evidence

- C# unit tests и generated contract checks;
- Windows native x64 smoke на обычном пользователе;
- reconnect/duplicate/power-loss/offline-before-login scenarios;
- manual visual checks widget/tray/access-gate/notifications;
- inspection AppData/logs/Credential Manager boundary.

## Открытые решения

- точный Windows storage API и encryption boundary;
- поведение restart при недоступном backend после подтверждённого stop;
- локальный лимит работы по последнему snapshot.
