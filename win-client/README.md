# GameClub Windows client

Текущий `GameClub.Client` source — legacy WinUI 3-клиент игрового ПК. Целевой
host — Avalonia: Linux будет использоваться для обычной разработки, build/test
и UI-smoke, а Windows сохранится платформой поставки и финальной native
проверки. До завершения первой точки миграции текущие Windows-инструкции ниже
относятся только к legacy source; порядок перехода описан в
[`plans/38-avalonia-linux-first`](../plans/38-avalonia-linux-first/PLAN.md).

Продуктовой flow не меняется: до авторизации клиент показывает fullscreen Locked
access-gate; после входа — компактный borderless виджет без замены Windows shell.
Backend остаётся источником истины для сессий, тарифов, баланса, списаний и
команд.

## Linux developer host

Linux-first solution находится в `GameClub.Client.sln`; legacy WinUI solution
для будущего Windows comparison — `GameClub.Client.Windows.sln`. После установки
.NET SDK версии из [`../global.json`](../global.json) первый host запускается так:

```bash
dotnet restore win-client/GameClub.Client.sln --disable-parallel
dotnet build win-client/GameClub.Client.sln --configuration Debug --no-restore
dotnet test win-client/GameClub.Client.sln --configuration Debug --no-build
dotnet run --project win-client/src/GameClub.Client.Avalonia --configuration Debug --no-build
```

Это Linux developer host с настоящим access-gate и portable gRPC transport.
Для локального integration-smoke сначала поднять только backend-контур:

```bash
docker compose up -d --build postgres redis backend-migrate backend-http backend-grpc worker meter-worker scheduler
curl --fail --silent --show-error http://127.0.0.1:8100/health/ready
```

Затем один раз создать в локальной dev-базе игровое место с MAC текущей Linux
машины. После первого запуска Avalonia enrollment свяжет installation identity
с этим местом; register/login в окне используют реальные localhost HTTP/gRPC
контракты и создают server-backed session. Тест перехода register → portal
запускается только явно и создаёт отдельный случайный dev-аккаунт:

```bash
GAMECLUB_RUN_LOCAL_INTEGRATION=1 \
  /home/daniel/.local/share/dotnet-sdk-8/dotnet test win-client/GameClub.Client.sln \
  --configuration Debug --no-build --filter LocalAvaloniaBackendIntegrationTests
```

Linux не реализует DPAPI, tray, restart или kiosk-policy. Для Windows-target
compile из Linux использовать:

```bash
dotnet publish win-client/src/GameClub.Client.Avalonia/GameClub.Client.Avalonia.csproj \
  --configuration Debug --runtime win-x64 --self-contained false
```

Полученный artifact не является доказательством Windows runtime.

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
C:\Git\HubShell\win-client\src\GameClub.Client\GameClub.Client.csproj
C:\Git\HubShell\win-client\scripts
C:\Git\HubShell\win-client\artifacts
```

Скрипты запускаются из `C:\Git\HubShell\win-client`.

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
- fullscreen WinUI не заменяет Assigned Access/Shell Launcher;
- отсутствие backend должно отображаться как offline/reconnecting, а не быть
  причиной закрытия окна.

После запуска клиент определяет MAC, ждёт назначения workstation в админке,
получает device identity и тему группы через backend. Подробный пользовательский
flow проверяется по `REAL-PC-VERIFICATION.md`.
