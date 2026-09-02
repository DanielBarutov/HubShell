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

Pre-auth gate, post-auth widget/tray, portal package queue/explicit activation,
snapshot gateway, transfer UI и durable offline journal есть на source-level.
Полный entry integration и native compile/runtime пока не доказаны.

## Реализовано в текущем срезе

Добавлены C# snapshot/transfer/offline DTO, gateway methods и coordinator
heartbeat/replay wiring. MainViewModel показывает active-package/auto-next
уведомление с закрытием через 3 секунды, transfer offer/confirm, а journal
шифрует JSONL и sequence state через DPAPI. Source-level tests/fakes обновлены;
native Windows build не запускался из-за отсутствующего .NET SDK на host.

## Входит в план

- login response/heartbeat с `SessionSnapshot` и `EntryDecision`;
- активный пакет, queue и auto-next notifications;
- explicit activation saved package при новом входе;
- session stop/logout/restart по server result;
- transfer offer/confirm на новом ПК;
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
2. [ ] Встроить snapshot/entry result в login и heartbeat; до server result
   показывать locked/reconnecting state.
3. [x] Реализовать package activation/auto-next notification: self-closing
   через 3 секунды и собственная close button.
4. [x] Связать stop/exhaustion/logout с server result, burn/lock/restart policy;
   не выполнять финансовое действие локально.
5. [x] Добавить transfer offer/confirm/result и старый-PC restart ACK.
6. [x] Реализовать durable journal storage, batch replay и partial-result UI.
7. [ ] Проверить no-new-session offline, disk/crash recovery и отсутствие
   секретов/лишней PII в local files/logs.
8. [ ] Добавить unit tests coordinator/gateway и Windows manual scenarios.

## Критерии готовности

- до auth/offline-before-login нет пользовательской рабочей сессии;
- entry refusal и snapshot приходят от backend;
- package activation/auto-next не приводит к двойному расходу;
- transfer требует подтверждения и не создаёт второй active session;
- journal переживает restart и replay идемпотентен;
- после exhaustion/stop клиент блокируется или перезапускается по server result.

## Остаток и release blocker

Нужно связать `EntryDecision` с фактическим login UI, проверить generated C# и
XAML на Windows, а также провести native x64/reconnect/power-loss smoke.
Local offline limit и поведение restart при недоступном backend требуют
подтверждения на целевом ПК.

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
