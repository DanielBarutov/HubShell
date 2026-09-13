# План 40 — Avalonia product flows и portable transport

Статус: `in_progress`  
Владелец: `win-client/`  
Зависимости: [`38-avalonia-linux-first`](../38-avalonia-linux-first/PLAN.md),
[`23-windows-enrollment-member-portal`](../23-windows-enrollment-member-portal/PLAN.md),
[`25-client-portal`](../25-client-portal/PLAN.md),
[`32-session-snapshot-entry`](../32-session-snapshot-entry/PLAN.md)

## Цель

Перенести access-gate и post-login portal/widget с сохранением существующих
server-backed правил на Avalonia. Linux остаётся development/test host: он
может подключаться только к явно указанному dev endpoint. Windows остаётся
продуктовой платформой и единственным evidence для tray, DPAPI, restart,
fullscreen/window placement и kiosk policy.

## Границы

- Backend, protobuf semantics, EntryDecision, session lifecycle, balance,
  tariff purchase/activation и transfer не меняются; UI только отображает DTO
  и вызывает существующие ports.
- gRPC transport, enrollment and portable composition отделяются от WinUI,
  чтобы Avalonia могла работать с test/dev backend без Windows API.
- DPAPI offline journal, NativeTrayIcon, restart/power, AppWindow and Shell
  integration остаются Windows adapters. Linux host не подменяет их и не
  хранит production credentials.
- Новый UI не получает демонстрационные balance/reservation/session values и
  не выполняет финансовое действие без уже существующего backend call.

## Порядок задач

1. [x] Выделить `net8.0` gRPC transport/enrollment project: generated protobuf
   consumers, `GrpcBackendClient`, MAC enrollment and endpoint validation.
   Перенести эти types из legacy WinUI compilation без изменения wire calls.
2. [ ] Добавить безопасную Avalonia developer composition: offline/connection
   state виден без endpoint; реальный endpoint включается только явной dev
   настройкой и не использует DPAPI journal как Linux security guarantee.
3. [ ] Перенести access-gate layout и binding/event adapters. Первый frame
   остаётся тёмным; entry/login/register/password-reset rules остаются в
   `MainViewModel` и backend responses.
4. [ ] Перенести post-login portal/session widget: profile, server snapshot,
   balance, tariffs, queued entitlement, active session, transfer and visible
   notifications. Не переносить tray/restart/desktop window mode в Linux.
5. [ ] Добавить Avalonia headless tests для state transitions and bindings;
   Linux smoke без endpoint, optional integration smoke только против
   explicitly supplied test backend.
6. [ ] После каждого portable slice выполнить Linux restore/build/test/run and
   `win-x64` cross-publish. Перед release выполнить separate Windows native
   compile/runtime smoke, including legacy-to-Avalonia adapter review.

## Критерии готовности этапа

- Avalonia uses the same Core contracts and portable transport as legacy;
  no copied business state or duplicate client implementation.
- Linux opens the dark access-gate and exercises safe UI state transitions
  without Windows P/Invoke or production secrets.
- Product-changing calls remain backend-mediated and their errors are visible.
- Windows-only mechanisms are still explicit ports with unverified native
  evidence, not silent Linux fallbacks.
