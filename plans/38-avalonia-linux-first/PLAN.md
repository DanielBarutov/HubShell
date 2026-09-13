# План 38 — Avalonia migration и Linux-first developer host

Статус: `in_progress`  
Владелец: `win-client/`  
Зависимости: [`win-client/PLAN.md`](../../win-client/PLAN.md),
[`36-winui-contract-consumers`](../36-winui-contract-consumers/PLAN.md)

## Цель

Заменить WinUI 3 UI-host Windows-клиента на Avalonia так, чтобы обычный цикл
разработки выполнялся в текущем Linux checkout: restore, compile, unit tests и
ручной запуск реального developer UI. Windows остаётся единственной
производственной платформой игрового ПК и отдельной обязательной проверкой
platform-specific поведения.

Эта первая версия плана заканчивается после первой успешной Linux-сборки,
тестового прогона, запуска Avalonia каркаса и Windows-target compile artifact,
собранного из Linux. Она не обещает функционально эквивалентный access-gate,
Windows runtime или готовый Windows release.

## Контекст и решение

Текущий проект на `net8.0-windows` использует WinUI 3 / Windows App SDK.
Поэтому Linux не может исполнить WindowsAppSDK XAML compiler и проверить окно.
При этом Domain/Application, gRPC contracts, enrollment, reconnect и большая
часть presentation state уже не зависят от Windows. Целевой UI-host — Avalonia.

Linux host — только developer/test environment. Его не разрешается называть
kiosk-клиентом, использовать как доказательство Windows security boundary или
поставлять на игровые ПК вместо Windows build.

## Входит в первую остановку

- документировать замену WinUI на Avalonia и границы Linux/Windows evidence;
- инвентаризировать зависимости текущего `GameClub.Client` и разделить
  platform-neutral code от Windows adapters;
- создать shared `net8.0` core, Avalonia `net8.0` host и cross-platform test
  project либо эквивалентное решение с теми же dependency boundaries;
- перенести минимальный application composition root и presentation state,
  необходимый для запуска пустого/diagnostic Avalonia окна;
- заменить UI-зависимость `Microsoft.UI.Xaml.Visibility` в ViewModel на
  platform-neutral state (`bool`/enum) и Avalonia converters/bindings;
- обеспечить Linux `dotnet restore`, `dotnet build`, `dotnet test` и
  `dotnet run` для Avalonia developer host;
- записать exact commands, фактическую ОС, SDK и результат первой сборки в
  [`plans/VERIFICATION.md`](../VERIFICATION.md).

## Не входит в первую остановку

- перенос access-gate, login/register, portal, tariff, transfer и widget UI
  до полного визуального/функционального эквивалента;
- native Windows run/install, single-file delivery, installer и kiosk runtime;
- tray, DPAPI, restart, autostart, monitor work-area positioning и kiosk policy;
- изменения protobuf, backend business rules, financial logic или product
  contracts;
- утверждение Linux как поддерживаемой платформы игрового ПК.

## Целевая граница проектов

```text
GameClub.Client.Core       net8.0
  Domain, Application, ports, gRPC DTO/gateways and portable state

GameClub.Client.Avalonia   net8.0
  Avalonia App/window, resources, bindings and Linux developer host

GameClub.Client.Windows    net8.0-windows
  DPAPI, Windows tray/restart/autostart and Windows-specific window adapters

GameClub.Client.Tests      net8.0
  Core and adapter fakes runnable in Linux
```

Это целевая зависимостная граница, а не требование создать все четыре проекта
до первой сборки. Допускается начать с Core + Avalonia + Tests, если Windows
adapters пока остаются в legacy source. Новые UI или Core-проекты не должны
ссылаться на `Microsoft.WindowsAppSDK`, `Microsoft.UI.*`, `user32.dll` или
`shell32.dll`.

## Порядок задач

1. [x] Зафиксировать inventory текущих зависимостей: WinUI `AppWindow`,
   `DisplayArea`, `DispatcherQueue`; `NativeTrayIcon` P/Invoke; DPAPI journal;
   Windows restart/autostart. Для каждой указан будущий port и Linux behaviour
   в [`INVENTORY.md`](INVENTORY.md).
2. [x] Зафиксировать solution layout и project references: shared code на
   `net8.0`, Avalonia host на `net8.0`, tests на `net8.0`; выбрать совместимую
   стабильную версию Avalonia и записать её в project file. Выбрана Avalonia
   `11.3.2`: она собирается SDK `8.0.425` без analyzer warnings.
3. [x] Вынести из shared presentation state WinUI-specific `Visibility` и
   другие `Microsoft.UI.*` types; `MainViewModel` emitted only from
   `GameClub.Client.Core` and exposes 16 positive `bool Is*Visible` states.
   Legacy WinUI maps these values through a UI-only converter; public
   domain/application contracts and their behaviour remain unchanged.
4. [x] Добавить пустой Avalonia App/MainWindow с application composition root,
   безопасным developer settings source и visible diagnostic state. Не подключать
   Windows P/Invoke как условие запуска Linux UI.
5. [x] Добавить Linux-runnable tests для Core и как минимум один Avalonia
   smoke, который создаёт UI host без Windows API. UI test не получает реальные
   credentials, PII или production endpoint.
6. [x] В Linux выполнить и записать точные команды:

   ```bash
   dotnet restore win-client/GameClub.Client.sln
   dotnet build win-client/GameClub.Client.sln --configuration Debug
   dotnet test win-client/GameClub.Client.sln --configuration Debug
   dotnet run --project win-client/src/GameClub.Client.Avalonia --configuration Debug
   ```

   Если имя solution/project в задаче 2 меняется, сначала обновить этот план и
   `win-client/README.md`, затем выполнять команды.
7. [x] В Linux собрать Windows-target compile artifact Avalonia host:

   ```bash
   dotnet publish win-client/src/GameClub.Client.Avalonia \
     --configuration Debug --runtime win-x64 --self-contained false
   ```

   Сохранить путь, runtime identifier и результат. Успех этой команды не
   подтверждает запуск в Windows, tray, DPAPI или kiosk behaviour.
8. [x] Обновить `plans/VERIFICATION.md`, `win-client/docs/SUPPORT-MATRIX.md` и
   owner-level plan фактическим evidence. Следующий этап — перенос access-gate
   и portal flows — открывается только после закрытия задачи 3 и всех критериев
   первой остановки.

## Критерии первой остановки

- Linux успешно выполняет restore, Debug build и tests без WindowsAppSDK/XAML
  compiler и без target `net8.0-windows` для Core/Avalonia/Tests;
- Avalonia developer host запускается локально и показывает окно/diagnostic
  state, не завершаясь из-за Windows API;
- Linux создаёт Windows-target `win-x64` compile artifact; этот результат
  помечен только как cross-compile, не Windows runtime proof;
- shared ViewModel/application code не содержит `Microsoft.UI.*` dependencies;
- существующие backend/gRPC/product rules не изменены;
- Windows-only зависимости имеют задокументированный будущий adapter boundary,
  а Windows native evidence по-прежнему явно помечен как непроверенный;
- результат, команды и версия SDK занесены в verification evidence.

## Проверки

- `git diff --check`;
- Linux restore/build/test/run по записанным командам;
- Linux cross-publish Avalonia `win-x64` с проверкой созданного артефакта;
- поиск отсутствия `Microsoft.UI`, `WindowsAppSDK`, `user32.dll` и `shell32.dll`
  в новых portable projects;
- review project-reference graph: Avalonia host не зависит от Windows adapter;
- последующая, но не блокирующая эту остановку, Windows restore/build/publish
  проверка по плану 37.

## Риски и открытые решения

- Avalonia tray/window APIs различаются между Windows, X11 и Wayland; их нельзя
  считать проверенными при первом Linux window run;
- DPAPI не переносится на Linux. Для developer host нужен non-production local
  storage adapter, который не имитирует production encryption guarantee;
- cross-publish Windows artifact из Linux может быть технически возможен, но не
  является доказательством Windows runtime; final smoke выполняется на Windows;
- до выбора пакетов следует проверить совместимость Avalonia с .NET 8,
  self-contained Windows publish и требуемыми архитектурами x86/x64/ARM64.
