# Windows client — support matrix

Документ фиксирует целевую платформу и границы доказательств. Фактический
запуск нужно подтвердить на Windows перед выпуском. Команды сборки, публикации и
startup diagnostics находятся в
[`WINDOWS-BUILD-AND-RUN.md`](WINDOWS-BUILD-AND-RUN.md).

| Область | Целевое значение | Статус в Linux checkout |
| --- | --- | --- |
| Runtime | .NET 8 | source-level |
| UI framework | WinUI 3 / Windows App SDK 1.6 | source-level |
| Target framework | `net8.0-windows10.0.19041.0` | project config |
| Минимальная ОС | Windows 10 build 17763 | project config |
| Архитектуры | x86, x64, ARM64 | project config; native runtime не проверен |
| Транспорт | gRPC/Protobuf, HTTP/gRPC в private LAN или HTTPS при внешнем доступе | source-level; transport runtime требует Windows smoke |
| Device auth | MAC enrollment → device-scoped JWT | source-level |
| User auth | server-backed register/login → client-scoped JWT | source-level |
| Режим окна | borderless fullscreen Locked shell | source-level; native smoke не выполнен |
| Manager access | `Ctrl+Alt+P`, отдельный manager password | source-level; native smoke не выполнен |
| Kiosk boundary | Assigned Access/Shell Launcher | не проверено |
| Delivery | self-contained single-file `GameClub.Client.exe` | publish требует Windows |

## Целевой deployment flow

1. Администратор собирает EXE с реальными `AuthAddress` и `GrpcAddress`.
2. EXE копируется на игровой ПК и запускается обычным пользователем.
3. Клиент создаёт технический installation id в AppData и отправляет MAC.
4. До назначения в админке отображается `Ожидает назначения`.
5. После назначения workstation по MAC backend выдаёт device JWT и настройки
   группы через heartbeat.
6. Клиент открывает Locked shell; пользователь регистрируется или входит и
   получает свой профиль/историю.

Канонический checkout на машине сборки:

```text
C:\Git\HubShell
```

Канонический путь приложения на тестовом игровом ПК:

```text
C:\GameClub\Client\GameClub.Client.exe
```

На клиентском ПК не должны выполняться `dotnet`, PowerShell setup, ввод
`device_id`, bootstrap-токена или локальных PIN-хэшей.

## Что проверено в текущем Linux checkout

- структура слоёв и source-of-truth protobuf;
- MAC enrollment, installation binding и состояния `pending/approved/disabled`;
- device/client JWT claims и device binding на source-level;
- fullscreen presenter, locked flow, portal view и `Ctrl+Alt+P` на source-level;
- allowlist команд, deadline, expiry, ACK и reconnect boundaries;
- portable publish parameters и отсутствие секретов в deployment script.

Это не подтверждает запуск WinUI, XAML compilation, Windows networking или
поведение полноэкранного окна.

## Что требует реального Windows-ПК

- `dotnet restore`, `dotnet build`, `dotnet test` для solution;
- запуск EXE на чистом ПК без SDK и без прав администратора;
- pending → assignment в web-админке → approved heartbeat;
- fullscreen/borderless, отсутствие desktop-фона и корректный focus;
- регистрация, login, logout, relock и отображение только своего профиля;
- reconnect, theme/policy, session lifecycle и повторный запуск;
- portable single-file запуск на чистом профиле;
- Assigned Access/Shell Launcher: Explorer, Start, desktop, Alt+Tab,
  произвольные приложения, recovery и restore;
- private-LAN HTTP/gRPC либо production HTTPS/gRPC TLS и сертификатная цепочка для внешнего доступа.

Автоматизированная сборка и запуск находятся в
[WINDOWS-BUILD-AND-RUN.md](WINDOWS-BUILD-AND-RUN.md), а ручные отметки — в
[REAL-PC-VERIFICATION.md](REAL-PC-VERIFICATION.md).

Для native solution используется `-p:Platform=x64`; `--arch` для solution не
является эквивалентом и приводит к `NETSDK1134`.
