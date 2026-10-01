# GameClub Windows client

`GameClub.Client.Avalonia` содержит общий Avalonia UI и Linux V2 developer
composition для build/test/UI-smoke. `GameClub.Client.Windows` — отдельный
production composition: он подключает тот же UI к Windows-only DPAPI journal,
restart, command stream, fullscreen/compact window adapter и native tray.
`GameClub.Client.Windows` — единственная production entry point для Windows.

Продуктовой flow не меняется: до авторизации клиент показывает fullscreen Locked
access-gate; после входа — компактный borderless виджет без замены Windows shell.
Backend остаётся источником истины для snapshot, тарифов и server facts; active
V2 session decisions и minute debit выполняются локальным ledger.

## Linux developer host

Linux-first solution находится в `GameClub.Client.sln`; Windows Avalonia
production solution — `GameClub.Client.Windows.sln`. После установки
.NET SDK версии из [`../global.json`](../global.json) V2 host запускается так:

```bash
cd /home/daniel/HubShell
dotnet restore win-client/GameClub.Client.sln --disable-parallel
dotnet build win-client/GameClub.Client.sln --configuration Debug --no-restore
dotnet test win-client/GameClub.Client.sln --configuration Debug --no-build
dotnet run --project win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj --configuration Debug --runtime linux-x64 --no-build
```

Это Linux V2 developer host с настоящим access-gate, V2 gRPC transport,
server-event polling и локальным ledger. Старый V1 client host для ручного
тестирования больше не используется.

Актуальная команда запуска конкретного Linux-проекта (передавать каталог
проекта без имени \`.csproj\` больше нельзя, потому что в нём несколько проектов):

```bash
GAMECLUB_V2_DEV_LEDGER_PATH=/tmp/hubshell-v2-manual.json dotnet run --project win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj --configuration Debug --runtime linux-x64
```
Для локального integration-smoke сначала поднять только backend-контур:

```bash
cd /home/daniel/HubShell
docker compose up -d --build postgres redis backend-migrate backend-http backend-grpc worker meter-worker scheduler v2-client-facts v2-server-outbox
curl --fail --silent --show-error http://127.0.0.1:8100/health/ready
```

Затем в локальной dev-базе нужно один раз создать или одобрить игровое место
с MAC текущей Linux-машины. После enrollment окно использует V2 offline
login/register и подписанный server snapshot. Для чистого ручного прогона
запускайте клиент с временным ledger:

```bash
cd /home/daniel/HubShell
GAMECLUB_V2_DEV_LEDGER_PATH=/tmp/hubshell-v2-manual.json \
  dotnet run --project win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj \
  --configuration Debug --runtime linux-x64
```

Клиент пишет локальный журнал запуска и сетевых ошибок без паролей и токенов.
По умолчанию Linux-файл находится в `~/.local/share/HubShell/logs/client.log`.
Для отдельного ручного прогона можно задать явный путь и сразу смотреть новые
строки:

```bash
cd /home/daniel/HubShell
GAMECLUB_CLIENT_LOG_PATH=/tmp/hubshell-client.log \
GAMECLUB_V2_DEV_LEDGER_PATH=/tmp/hubshell-v2-manual.json \
  dotnet run --project win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj \
  --configuration Debug --runtime linux-x64
tail -f /tmp/hubshell-client.log
```

Журнал ограничен размером 2 МБ и автоматически переносит старый файл в
`client.log.1`.

Linux не реализует DPAPI, tray, restart или kiosk-policy. Для Windows-target
compile из Linux использовать:

```bash
cd /home/daniel/HubShell
dotnet publish win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj \
  --configuration Debug --runtime win-x64 --self-contained false
```

Полученный artifact не является доказательством Windows runtime.

## Windows Avalonia host

На Windows production entry point собирается из Avalonia solution:

```powershell
Set-Location "C:\Git\HubShell"
dotnet restore win-client\GameClub.Client.Windows.sln
dotnet build win-client\GameClub.Client.Windows.sln -c Debug -p:Platform=x64
dotnet publish win-client\src\GameClub.Client.Windows\GameClub.Client.Windows.csproj `
  -c Debug -r win-x64 --self-contained false
```

Linux не считает успешным этот native publish: для него остаются обязательны
ручные Windows checks окна, tray, DPAPI, restart и kiosk-policy.

## Основной порядок работы

1. Клонировать проект в `C:\Git\HubShell`.
2. На Windows-машине сборки выполнить native restore/build/test.
3. Проверить Debug folder-publish и запуск.
4. Собрать Release single-file EXE.
5. Передать EXE на игровой ПК и выполнить ручной smoke.

Полная пошаговая инструкция, включая диагностику EXE, находится в
[`docs/WINDOWS-BUILD-AND-RUN.md`](docs/WINDOWS-BUILD-AND-RUN.md).

## Документы

- [`docs/WINDOWS-BUILD-AND-RUN.md`](docs/WINDOWS-BUILD-AND-RUN.md) — каноническая
  сборка, folder-publish, single-file, запуск и startup diagnostics;
- [`docs/REAL-PC-VERIFICATION.md`](docs/REAL-PC-VERIFICATION.md) — функциональный
  smoke на физическом Windows-ПК после успешной сборки;
- [`docs/ACCESS-GATE.md`](docs/ACCESS-GATE.md) — режимы, access-gate и границы
  kiosk-безопасности;
- [`docs/SUPPORT-MATRIX.md`](docs/SUPPORT-MATRIX.md) — целевая платформа и
  разделение source-level/native evidence.

## Пути

```text
C:\Git\HubShell\win-client\GameClub.Client.sln
C:\Git\HubShell\win-client\GameClub.Client.Windows.sln
C:\Git\HubShell\win-client\src\GameClub.Client.Windows\GameClub.Client.Windows.csproj
C:\Git\HubShell\win-client\scripts
C:\Git\HubShell\win-client\artifacts
```

Все команды и скрипты запускаются из `C:\Git\HubShell`. Не переходите в
`win-client`: используйте пути `.\win-client\scripts\...`, а сами скрипты
строят внутренние пути от `$PSScriptRoot`.

## Скрипты

- `scripts\verify-windows.ps1` — restore, Debug build и tests solution;
- `scripts\publish-windows.ps1` — folder-publish или low-level single-file
  publish с явными параметрами;
- `scripts\build-portable-exe.ps1` — канонический Release single-file EXE с
  SHA-256;
- `scripts\diagnose-startup.ps1` — запуск с ожиданием, exit code и сбором
  Application Event Log;
- `%LocalAppData%\GameClub\startup.log` — собственные этапы запуска,
  managed/UI-исключения и ошибки фоновых циклов без секретов;
- `scripts\install-windows.ps1` — необязательное копирование folder-publish и
  регистрация автозапуска текущего пользователя;
- `scripts\uninstall-windows.ps1` — явное удаление этой установки и автозапуска;
- `scripts\configure-windows-kiosk.ps1` — отдельный preview/apply/restore только для
  Windows Shell Launcher; не использовать до успешного обычного smoke;
- `scripts\configure-windows-user-policy.ps1` — optional preview/apply/restore
  full-kiosk user policy `NoRun=1`; не применять в базовом `app_gate`, если
  `Win+R` должен работать после входа;
- `scripts\new-access-hash.ps1` — только developer helper для PBKDF2 verifier,
  не часть обычной установки клиента.

`build-installer.ps1` удалён: это не был установщик, а дублирующий упаковочный
скрипт без отдельного installer-формата.

## Важные ограничения

- `dotnet build` не создаёт переносимый один EXE;
- для отладки сначала использовать folder-publish с PDB;
- для solution использовать `-p:Platform=x64`, не `--arch`;
- production в изолированной приватной LAN может использовать HTTP для auth и gRPC;
  для публичного или недоверенного адреса обязательно использовать HTTPS;
- на игровом ПК не нужны SDK, Visual Studio, env-переменные, `device_id`,
  bootstrap token или PIN hash;
- fullscreen Avalonia access-gate не заменяет Assigned Access/Shell Launcher;
- отсутствие backend должно отображаться как offline/reconnecting, а не быть
  причиной закрытия окна.

После запуска клиент определяет MAC, ждёт назначения workstation в админке,
получает device identity и тему группы через backend. Подробный пользовательский
flow проверяется по `REAL-PC-VERIFICATION.md`.
