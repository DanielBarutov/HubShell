# Сборка, запуск и диагностика Windows-клиента

Этот документ является основной инструкцией для сборки и запуска
`GameClub.Client` на Windows. Он рассчитан на checkout проекта в
`C:\Git\HubShell`.

Функциональный smoke-тест после запуска описан отдельно в
[`REAL-PC-VERIFICATION.md`](REAL-PC-VERIFICATION.md). Поведение access-gate и
границы безопасности описаны в [`ACCESS-GATE.md`](ACCESS-GATE.md).

## 1. Пути проекта и правила

Все команды ниже выполняются в PowerShell. Каталог проекта разработчика:

```text
C:\Git\HubShell
```

Основные пути:

```text
C:\Git\HubShell\win-client\GameClub.Client.sln
C:\Git\HubShell\win-client\src\GameClub.Client\GameClub.Client.csproj
C:\Git\HubShell\win-client\scripts
C:\Git\HubShell\win-client\artifacts
```

Не путайте следующие результаты:

- `dotnet build` — проверка исходников, не переносимый клиент;
- folder-publish — каталог EXE вместе со всеми зависимостями, основной вариант
  для отладки;
- single-file publish — один EXE для передачи на игровой ПК, проверять его
  нужно отдельно после folder-publish.

Нельзя копировать один `GameClub.Client.exe` из каталога `bin` или из
folder-publish и ожидать, что он будет переносимым. Для одного файла используйте
только `build-portable-exe.ps1`.

## 2. Что требуется

На машине сборки/разработчика:

- Windows 10 build 17763 или новее либо Windows 11;
- Visual Studio 2022 с workload `.NET desktop development`;
- .NET 8 SDK;
- Windows SDK;
- доступ к backend, если проверяется сетевой сценарий.

На игровом ПК для Release single-file не требуются Visual Studio, .NET SDK и
Windows App SDK. Обычный запуск выполняется без прав администратора. Для
первой проверки kiosk-политику Windows не включайте.

Если файлы пришли архивом или скачаны браузером, в каталоге проекта можно
снять Mark-of-the-Web:

```powershell
Unblock-File -Path "C:\Git\HubShell\win-client\scripts\*.ps1"
```

## 3. Проверить checkout

```powershell
Set-Location "C:\Git\HubShell"
git status --short
git rev-parse --show-toplevel
git rev-parse --short HEAD
Test-Path "C:\Git\HubShell\win-client\GameClub.Client.sln"
Test-Path "C:\Git\HubShell\win-client\src\GameClub.Client\GameClub.Client.csproj"
```

Ожидаемый корень — `C:\Git\HubShell`, а обе проверки `Test-Path` должны вернуть
`True`. Перед сборкой убедитесь, что незакоммиченные изменения принадлежат
текущей проверке.

## 4. Проверить backend и адреса

Для backend на этой же Windows-машине допустим dev-вариант:

```powershell
Invoke-WebRequest "http://127.0.0.1:8100/health/ready" -UseBasicParsing
```

Для игрового ПК `127.0.0.1` указывает на сам игровой ПК и обычно неверен.
Production-сборка должна получать доступные DNS/LAN-адреса с HTTPS:

```text
AuthAddress = https://api.example.club:8100
GrpcAddress = https://api.example.club:51051
```

`api.example.club` выше — только обозначение места для подстановки, не рабочий
адрес. В реальной команде используйте DNS-имя или IP вашего backend.

В production клиенту не нужны PostgreSQL, Redis или внутренние порты backend.
HTTP допускается только для `dev` с loopback-адресом; остальные HTTP-адреса
клиент отклоняет политикой endpoint.

## 5. Native restore, build и tests

Это проверяет solution, но не запускает опубликованный EXE.

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Скрипт выполняет `dotnet --info`, restore, build и test с платформой `x64`.
Для solution используйте `-p:Platform=x64`; параметр `--arch` не является его
заменой и может привести к `NETSDK1134`.

Если нужен ручной эквивалент:

```powershell
dotnet restore "C:\Git\HubShell\win-client\GameClub.Client.sln"
dotnet build "C:\Git\HubShell\win-client\GameClub.Client.sln" `
  --configuration Debug -p:Platform=x64 --no-restore
dotnet test "C:\Git\HubShell\win-client\GameClub.Client.sln" `
  --configuration Debug -p:Platform=x64 --no-restore
```

## 6. Debug folder-publish и запуск

Folder-publish — первый вариант для разбора проблемы запуска: рядом с EXE
остаются DLL, native-файлы и PDB, поэтому проще определить отсутствующую
зависимость.

Для локального dev backend на этой же машине:

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\publish-windows.ps1 `
  -Architecture x64 `
  -Configuration Debug `
  -EnvironmentName dev `
  -AuthAddress "http://127.0.0.1:8100" `
  -GrpcAddress "http://127.0.0.1:51051" `
  -CleanOutput `
  -OutputPath "C:\GameClub\debug-publish"
```

Для удалённого backend замените адреса на реальные HTTPS и используйте
`-EnvironmentName production`.

Запускать нужно весь каталог, а не только EXE:

```powershell
$debugExe = "C:\GameClub\debug-publish\GameClub.Client.exe"
$debugDir = Split-Path -Parent $debugExe

$process = Start-Process `
  -FilePath $debugExe `
  -WorkingDirectory $debugDir `
  -Wait `
  -PassThru

"PID: $($process.Id)"
"ExitCode: $($process.ExitCode)"
```

Если клиент остаётся запущен, остановите его обычным способом и переходите к
ручному smoke. Если он сразу завершается, сохраните `ExitCode` и события
Windows из следующего раздела.

## 7. Диагностика EXE, который сразу завершается

Текущий `WinExe` не выводит исключения в консоль. Для автоматического сбора
кода завершения и записей Application Event Log используйте:

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\diagnose-startup.ps1 `
  -ExecutablePath "C:\GameClub\debug-publish\GameClub.Client.exe" `
  -TimeoutSeconds 30
```

Отчёт создаётся в:

```text
C:\Git\HubShell\win-client\artifacts\diagnostics\<timestamp>\startup-report.txt
```

В отчёте сохраняются путь EXE, рабочий каталог, PID, код завершения, версия
Windows, сообщения провайдеров `.NET Runtime`, `Application Error` и
`Windows Error Reporting`, а также последние 100 строк собственного
`startup.log`. Пароли, PIN, JWT и сетевые payload туда не добавляются.

После запуска также проверьте собственный журнал приложения:

```text
C:\Users\<WindowsUser>\AppData\Local\GameClub\startup.log
```

Он содержит только этапы старта, типы/сообщения исключений и stack trace без
JWT, PIN и сетевых payload. Прочитать последние записи можно так:

```powershell
Get-Content "${env:LOCALAPPDATA}\GameClub\startup.log" -Tail 100
```

Если скрипт ещё не использовался или нужна ручная проверка:

```powershell
$since = (Get-Date).AddMinutes(-10)
Get-WinEvent -FilterHashtable @{ LogName = "Application"; StartTime = $since } |
  Where-Object {
    $_.ProviderName -in ".NET Runtime", "Application Error", "Windows Error Reporting"
  } |
  Select-Object TimeCreated, ProviderName, Id, Message |
  Format-List
```

Дополнительно проверьте блокировку Defender:

```powershell
Get-MpThreatDetection |
  Sort-Object InitialDetectionTime -Descending |
  Select-Object -First 10
```

### Как интерпретировать результат

| Результат | Следующий шаг |
| --- | --- |
| Folder-publish работает, single-file нет | Проверить распаковку single-file, `%TEMP%`, Defender и права пользователя. |
| EXE не найден или ошибка отсутствующей DLL | Использован не тот артефакт; собрать folder-publish и не отделять EXE от каталога. |
| Ошибка `0xc000007b` или похожая native loader error | Проверить архитектуру ПК и сборки; для обычного игрового ПК использовать `x64`. |
| `.NET Runtime` с managed exception | Запустить Debug folder-publish из Visual Studio под отладчиком и сохранить stack trace. |
| `Application Error` с faulting module | Проверить native dependency, Windows App SDK, архитектуру и crash dump. |
| Нет событий, EXE исчезает сразу | Проверить Defender/SmartScreen, `Unblock-File`, права на каталог и совместимость Windows. |
| Процесс жив, но окна нет | Запустить из Visual Studio, проверить XAML и native tray; отсутствие backend не должно закрывать окно. |

Особенно важно: native tray и фоновые циклы теперь запускаются после
`Window.Activate()`, а ошибка tray записывается в `startup.log` и не должна
скрывать уже созданное окно. Если процесс всё равно исчезает до появления
записи, используйте Event Log, Defender/SmartScreen и Visual Studio.

## 8. Запуск под Visual Studio

Откройте:

```text
C:\Git\HubShell\win-client\GameClub.Client.sln
```

В Visual Studio выберите:

```text
Configuration: Debug
Platform: x64
Startup Project: GameClub.Client
```

Запустите `F5`. В `Debug > Windows > Exception Settings` включите остановку
на выброшенных CLR-исключениях. Для native-сбоя включите native debugging и
сохраните имя faulting module из остановки или Event Viewer.

Для отладки уже опубликованного EXE используйте Debug folder-publish с PDB.
Single-file Release не должен быть первым объектом отладки.

## 9. Release single-file для игрового ПК

После успешного Debug folder-publish соберите один EXE на машине сборки:
Сначала задайте реальные production endpoint'ы. Не используйте адреса из
примера и не записывайте в команды секреты:

```powershell
$authAddress = Read-Host "Production AuthAddress (https://...)"
$grpcAddress = Read-Host "Production GrpcAddress (https://...)"
```

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\build-portable-exe.ps1 `
  -Architecture x64 `
  -Configuration Release `
  -EnvironmentName production `
  -AuthAddress $authAddress `
  -GrpcAddress $grpcAddress
```

Ожидаемый результат:

```text
C:\Git\HubShell\win-client\artifacts\portable\win-x64\Release\GameClub.Client.exe
```

SHA-256 печатается скриптом. На игровом ПК создайте, например, каталог:

```text
C:\GameClub\Client\GameClub.Client.exe
```

Скопируйте туда именно этот EXE и запускайте обычным пользователем. Для первого
запуска не задавайте `GAMECLUB_*`, `device_id`, bootstrap token или PIN hash.
Адреса backend уже зашиты в deployment metadata сборки.

Если нужен автозапуск, это отдельный необязательный шаг:

```powershell
.\scripts\install-windows.ps1 `
  -PublishPath "C:\Git\HubShell\win-client\artifacts\publish\win-x64\Release" `
  -InstallPath "C:\Users\Public\GameClub\Client"
```

Сначала проверьте ручной запуск без автозапуска. Kiosk provisioning не является
частью обычной установки.

Если нужен recovery-task вместо HKCU Run, используйте только один механизм:

```powershell
.\scripts\install-windows.ps1 `
  -PublishPath "C:\GameClub\debug-publish" `
  -InstallPath "C:\Users\Public\GameClub\Client" `
  -NoStartup `
  -RegisterRecoveryTask
```

Не запускайте эту команду вместе с обычным вариантом без `-NoStartup`: скрипт
остановит попытку зарегистрировать оба механизма одновременно.

Для удаления установки нужен явный параметр подтверждения. По умолчанию
зашифрованный offline journal и startup log сохраняются, чтобы не потерять
ожидающие reconciliation операции и диагностику:

```powershell
.\scripts\uninstall-windows.ps1 `
  -InstallPath "C:\Users\Public\GameClub\Client" `
  -ConfirmRemoval
```

Удалять offline journal и startup log можно только отдельным явным параметром
после проверки backend и состояния финансовых операций:

```powershell
.\scripts\uninstall-windows.ps1 `
  -InstallPath "C:\Users\Public\GameClub\Client" `
  -ConfirmRemoval `
  -RemoveRuntimeData
```

Кастомный `InstallPath` удаляется только если в нём есть marker
`.gameclub-installation`, созданный `install-windows.ps1`. Корень диска и
неподтверждённые каталоги скрипт отклоняет.

## 10. После запуска

Функциональные проверки выполняются по
[`REAL-PC-VERIFICATION.md`](REAL-PC-VERIFICATION.md):

1. pending до назначения MAC;
2. approved и heartbeat после назначения workstation;
3. fullscreen Locked access-gate;
4. регистрация/login/logout;
5. reconnect и повторный запуск;
6. theme, session stop и manager maintenance;
7. отдельная проверка Assigned Access/Shell Launcher.

Нативный Windows runtime считается подтверждённым только после фактического
запуска EXE и ручного smoke на Windows. Linux-проверка исходников этого не
заменяет.

## 11. Минимальный отчёт о проблеме

Для передачи проблемы приложите:

- commit из `git rev-parse --short HEAD`;
- архитектуру (`x64`, `x86` или `ARM64`);
- команду и тип артефакта: build, folder-publish или single-file;
- путь запуска;
- `ExitCode`;
- каталог `artifacts\diagnostics\<timestamp>`;
- событие Windows с `ProviderName`, `ExceptionCode` и `FaultingModuleName`;
- результат проверки folder-publish против single-file.

Не прикладывайте JWT, bootstrap token, PIN, пароли и полные сетевые payload.
