# Windows client — support matrix

Документ фиксирует целевую платформу по текущему `.csproj`. Фактический запуск
нужно подтвердить на Windows перед выпуском.

| Область | Целевое значение | Подтверждение |
| --- | --- | --- |
| Runtime | .NET 8 | project target framework |
| UI framework | WinUI 3 / Windows App SDK 1.6 | project package reference |
| Target framework | `net8.0-windows10.0.19041.0` | project target framework |
| Минимальная ОС | Windows 10 build 17763 | `TargetPlatformMinVersion` |
| Windows build для разработки | Windows 10/11 SDK 19041+ | target framework and SDK tooling |
| Архитектуры | x86, x64, ARM64 | `Platforms`/`RuntimeIdentifiers` |
| Транспорт | gRPC over configured endpoint; dev loopback HTTP, production HTTPS | `EndpointPolicy` и generated protobuf consumers |
| Auth | device JWT через dev bootstrap | runtime configuration |
| Режим окна | компактный виджет / full-window | `MainWindow` resize flow |
| Access gate | Locked до кода пользователя, отдельный Maintenance для менеджера | `AccessGateCoordinator` + PBKDF2 verifier |
| Kiosk boundary | Assigned Access/Shell Launcher для запрета выхода в Windows desktop | deployment policy, не WinUI-код |

## Что проверено в текущей Linux-среде

- структура слоёв и исходных файлов;
- наличие source-of-truth protobuf и C# `Protobuf Include` для актуальных
  contracts, включая billing;
- статическая граница device JWT, heartbeat, command stream, expiry и ACK;
- app-level access-gate: locked startup, manager boundary, idle relock и throttling;
- конфигурационные значения из проекта.

## Что требует Windows

- `dotnet restore` и `dotnet build` WinUI solution;
- запуск под обычным пользователем;
- `dotnet test` для coordinator/access-gate тестов;
- проверка компактного и full-window режимов;
- старт без рабочих действий до user unlock и вход в maintenance только отдельным
  manager password;
- запуск в Assigned Access/Shell Launcher и проверка, что обычный пользователь не
  получает desktop, shell, Alt+Tab и произвольные приложения;
- фактический app-shell lock, применение theme resources и восстановление после
  перезапуска;
- проверка device stream и heartbeat на целевых Windows builds.
- проверка загрузки production-конфигурации с HTTPS и отклонения HTTP.

`scripts/configure-windows-kiosk.ps1` по умолчанию только создаёт preview XML.
Применение или восстановление требует явного `-Apply`, администратора,
контекста `SYSTEM`, существующей стандартной kiosk-учётной записи и
поддерживаемой редакции Enterprise/Education/IoT. Скрипт сохраняет backup перед
заменой Shell Launcher policy.

Автоматизированная последовательность restore/build и ручной checklist находятся в
[`../scripts/verify-windows.ps1`](../scripts/verify-windows.ps1). Запускать из
PowerShell в каталоге `win-client`:

```powershell
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Скрипт передаёт архитектуру как `-p:Platform`, потому что `--arch` для solution
не поддерживается SDK; publish использует отдельный runtime `win-x64`/`win-x86`/
`win-arm64`.

В текущем Linux-окружении .NET 8 SDK доступен локально в `/tmp/hubshell-dotnet`,
но native WinUI/Windows App SDK XAML-компилятор Windows не запускается. `csc` и
`msbuild` не находятся в системном PATH. Это ограничение проверки, а не
разрешение считать native build успешным.
