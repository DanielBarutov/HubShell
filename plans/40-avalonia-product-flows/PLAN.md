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
- gRPC transport, enrollment and portable composition отделяются от UI-host,
  чтобы Avalonia могла работать с test/dev backend без Windows API.
- DPAPI offline journal, NativeTrayIcon, restart/power, AppWindow and Shell
  integration остаются Windows adapters. Linux host не подменяет их и не
  хранит production credentials.
- Новый UI не получает демонстрационные balance/reservation/session values и
  не выполняет финансовое действие без уже существующего backend call.

## Порядок задач

1. [x] Выделить `net8.0` gRPC transport/enrollment project: generated protobuf
   consumers, `GrpcBackendClient`, MAC enrollment and endpoint validation.
   Перенести эти types в portable compilation без изменения wire calls.
2. [x] Добавить безопасную Avalonia developer composition: offline/connection
   state виден без endpoint; текущий dev host жёстко ограничен loopback
   `127.0.0.1` и не использует DPAPI journal как Linux security guarantee.
3. [x] Перенести access-gate layout и binding/event adapters. Первый frame
   остаётся тёмным; entry/login/register/password-reset rules остаются в
   `MainViewModel` и backend responses. Avalonia содержит полный dark gate,
    non-user-facing maintenance state, phone mask, очистку password-полей после submit,
   activity tracking и dynamic group-theme accent.
4. [x] Перенести post-login portal/session widget: profile, server snapshot,
   balance, server-backed upcoming booking, tariffs with explicit local
   confirmation before the existing backend call, queued entitlement activation,
   active session, transfer, dismissible notification and account history.
   Tray/restart/desktop window mode не подменяются Linux-host; это отдельный
   Windows adapter/evidence task.
5. [ ] Добавить Avalonia headless tests для state transitions and bindings;
   Linux smoke без endpoint, optional integration smoke только против
   explicitly supplied test backend. Headless check now verifies the complete
   access-gate/maintenance/portal control surface; add interaction-level tests
   for confirmation, transfer and password-reset before closing this task.
6. [ ] После каждого portable slice выполнить Linux restore/build/test/run and
   `win-x64` cross-publish. Перед release выполнить separate Windows native
   compile/runtime smoke, including tray/window adapter review. Linux builds
   the new `GameClub.Client.Windows` solution without warnings and produces a
   self-contained `win-x64` PE folder-publish; native execution remains
   unverified.
7. [x] Заменить исторический UI executable host отдельным
   `GameClub.Client.Windows` Avalonia production host (portable `net8.0`,
   published only as `win-*`). Он должен переиспользовать
   `MainWindow`/Core/transport, а Windows-only composition подключает DPAPI
   journal, restart/power, command stream, native window/tray adapters и baked
   production endpoints. Не оставлять второй UI-host как production path;
   native Windows execution остаётся обязательным evidence.
   Имя опубликованного процесса и файла — `HubShell.exe`; знак приложения
   добавлен в Windows-ресурсы и назначен главному и вспомогательному окнам.
   Реализовано source-level: `GameClub.Client.Windows.sln` ведёт на новый
   Avalonia host; DPAPI journal, restart/power, command stream, fullscreen
   access-gate, compact always-on-top widget с прозрачными скруглёнными
   внешними углами и native Windows tray перенесены в явные adapters. Linux
   host намеренно скрывает действие tray. Реальная
   Windows runtime-проверка остаётся открытым evidence в task 6.

## Критерии готовности этапа

- Avalonia uses the same Core contracts and portable transport without a second UI path;
  no copied business state or duplicate client implementation.
- Linux opens the dark access-gate and exercises safe UI state transitions
  without Windows P/Invoke or production secrets.
- Product-changing calls remain backend-mediated and their errors are visible.
- Windows-only mechanisms are still explicit ports with unverified native
  evidence, not silent Linux fallbacks.

## Выполненный UI-срез

- `MainWindow.axaml` использует только `MainViewModel` и существующие
  server-backed DTO/calls: не создаёт локальный баланс, сессию, бронь или
  финансовый факт.
- Тема workstation меняет Avalonia resource `AccentBrush`; пользовательского
  выбора темы нет.
- Пользовательское имя станции переносится из `workstation.name` authenticated
  heartbeat в общий `MainViewModel`; UUID станции остаётся только техническим
  идентификатором и не выводится в access-gate или widget.
- Пользовательский access-gate содержит только вход и создание аккаунта:
  соединение обновляется автоматически, а ошибки portal показываются отдельной
  плашкой с безопасным локализованным текстом. Primary/secondary buttons имеют
  явные normal/hover/pressed/disabled состояния с короткой анимацией.
- Основной post-login widget сохраняет фиксированную компактную ширину и
  растягивает свои карточки на доступную колонку. История аккаунта вынесена в
  отдельное borderless-окно с явным закрытием, той же палитрой и локальным
  `dd.MM.yyyy HH:mm` форматом server-backed timestamps.
- Запуск в Linux проверяет normal developer window, а не Windows fullscreen,
  compact placement, tray, restart, DPAPI journal или kiosk policy.
