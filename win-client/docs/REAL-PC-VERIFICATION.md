# Проверка Windows-клиента на реальном ПК

Этот документ предназначен для первой полноценной проверки `GameClub.Client`
на физическом компьютере под Windows. В Linux можно проверить структуру проекта,
контракты и статические границы, но нельзя считать подтверждёнными WinUI 3
restore/build, запуск окна, access-gate и системный kiosk.

## 1. Что понадобится

- физический Windows 10 build 17763+ или Windows 11;
- для сборки: Visual Studio 2022 с workload **.NET desktop development**, .NET
  8 SDK и Windows SDK;
- архитектура `x64` для обычного игрового ПК;
- доступ к исходникам проекта и PowerShell;
- запущенный backend GameClub;
- зарегистрированный в dashboard workstation с тем же `device_id`, который
  будет передан Windows-клиенту.

Целевая матрица версий находится в
[SUPPORT-MATRIX.md](SUPPORT-MATRIX.md).

## 2. Выберите схему подключения

### Backend и Windows-клиент на одном ПК

Это самый простой вариант для первого smoke-теста. Клиент использует:

```text
GAMECLUB_AUTH_ADDRESS=http://127.0.0.1:8000
GAMECLUB_GRPC_ADDRESS=http://127.0.0.1:50051
```

### Backend на отдельном Linux-компьютере

Вместо `127.0.0.1` укажите LAN-адрес backend-хоста, например
`http://192.168.1.20:8000` и `http://192.168.1.20:50051`.

Важно: текущий dev Compose по умолчанию публикует HTTP и gRPC только на
`127.0.0.1` хоста. Для подключения с другого компьютера нужно осознанно
изменить сетевую публикацию/прокси и правила firewall. Для production
используйте TLS и `https://`/защищённый gRPC endpoint; не переносите dev
bootstrap-токен в постоянную установку.

## 3. Запустите dev backend

Из корня проекта в PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
(Invoke-WebRequest http://127.0.0.1:8000/health/ready).StatusCode
```

Ожидаемый код readiness — `200`. Если backend запущен на другом хосте,
проверяйте его адрес вместо `127.0.0.1`.

Для локального dev допустимы значения из `.env.example`, но перед проверкой
убедитесь, что bootstrap-токен и operator credentials заданы в локальном
`.env`, а не вписаны в эту инструкцию или в исходники. Реальные секреты не
добавляйте в Git и не передавайте в командной строке, если этого можно избежать.

## 4. Зарегистрируйте workstation

1. Откройте operator UI: `http://127.0.0.1:3000`.
2. Войдите оператором dev-окружения.
3. В настройках добавьте или найдите workstation и задайте:
   - `device_id`, например `pc-001`;
   - имя и группу/зону;
   - позицию на карте;
   - разрешённое состояние, без disabled-причины.
4. Для группы задайте тему (обычная, VIP, neon или minimal) и policy.

Один только device bootstrap token не регистрирует новый ПК: identity устройства
должна существовать в Workstations. Для первого безопасного теста используйте
`lock_after_session=true`, но временно выключите
`restart_after_session`, иначе успешная проверка `session.stop` может запланировать
перезапуск Windows.

## 5. Подготовьте переменные процесса

Откройте PowerShell из корня проекта. Значения ниже действуют только для текущего
окна PowerShell и не сохраняются в репозитории:

```powershell
Set-Location .\win-client

$env:GAMECLUB_ENVIRONMENT = "dev"
$env:GAMECLUB_DEVICE_ID = "pc-001"
$env:GAMECLUB_AUTH_ADDRESS = "http://127.0.0.1:8000"
$env:GAMECLUB_GRPC_ADDRESS = "http://127.0.0.1:50051"

$deviceTokenLine = Get-Content ..\.env |
    Where-Object { $_ -match '^GAMECLUB_DEVICE_BOOTSTRAP_TOKEN=' } |
    Select-Object -First 1
$env:GAMECLUB_DEVICE_BOOTSTRAP_TOKEN =
    $deviceTokenLine -replace '^GAMECLUB_DEVICE_BOOTSTRAP_TOKEN=', ''
Remove-Variable deviceTokenLine
```

Если backend находится на Linux-хосте, замените оба адреса на его LAN/TLS-адрес.
Не вставляйте фактическое значение токена в отчёты, скриншоты или Git.

Для access-gate сгенерируйте PBKDF2-хеши локально. Скрипт не печатает plaintext
пароль, поэтому сохраните пароль в менеджере секретов тестовой машины:

```powershell
$userHashLine = .\scripts\new-access-hash.ps1 -Kind user
$env:GAMECLUB_CLIENT_ACCESS_PIN_HASH =
    $userHashLine.Substring($userHashLine.IndexOf("=") + 1)
Remove-Variable userHashLine

$managerHashLine = .\scripts\new-access-hash.ps1 -Kind manager
$env:GAMECLUB_MANAGER_PASSWORD_HASH =
    $managerHashLine.Substring($managerHashLine.IndexOf("=") + 1)
Remove-Variable managerHashLine
```

В dev при отсутствии manager hash существует встроенное значение `password`, но
для проверяемого сценария лучше задать свой пароль и зафиксировать только факт
проверки, не сам пароль.

## 6. Выполните native restore/build/test

В том же PowerShell:

```powershell
dotnet --info
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Скрипт проверяет Windows, выполняет `restore`, native `build` и `test`, затем
печатает ручной checklist. Успехом считается только ситуация, когда все три шага
завершились без ошибок. При необходимости те же действия вручную:

```powershell
dotnet restore .\GameClub.Client.sln
dotnet build .\GameClub.Client.sln --configuration Debug -p:Platform=x64 --no-restore
dotnet test .\GameClub.Client.sln --configuration Debug -p:Platform=x64 --no-restore
```

## 7. Запустите клиент

Предпочтительно запустить `GameClub.Client` из Visual Studio с конфигурацией
`Debug` и платформой `x64`. Если нужен запуск из PowerShell после build:

```powershell
$clientExe = Get-ChildItem .\src\GameClub.Client\bin -Recurse `
    -Filter GameClub.Client.exe | Select-Object -First 1
& $clientExe.FullName
```

Клиент должен стартовать в `Locked`, без показа баланса, профиля и рабочих
действий до ввода пользовательского PIN.

## 8. Ручной smoke-чеклист

Отмечайте каждый пункт как `PASS`, `FAIL` или `NOT CHECKED` с временем и
комментарием.

### Access-gate и режимы

- [ ] После запуска отображается `Locked`; рабочие данные не раскрыты.
- [ ] Правильный пользовательский PIN переводит клиент в `User`.
- [ ] Неверные попытки отклоняются; после пяти ошибок действует cooldown.
- [ ] После закрытия/деактивации окна credentials очищаются, клиент возвращается
  в `Locked`.
- [ ] `Ctrl+Alt+P` открывает manager maintenance только по отдельному паролю.
- [ ] После бездействия клиент блокируется; штатный таймаут access-gate — 10 минут.
- [ ] При `401/403` или `Unauthenticated/PermissionDenied` клиент не продолжает
  рабочие действия и требует повторной авторизации устройства.

### Связь с backend и карта ПК

- [ ] Workstation появляется online с правильным `device_id`.
- [ ] Первый heartbeat приходит в течение примерно 15–30 секунд; статус не
  становится «доступен» только из-за факта регистрации.
- [ ] При остановке backend/gRPC клиент показывает offline/reconnect, а не
  ложный успех операции:

```powershell
docker compose stop backend-grpc
# подождать 15–30 секунд и проверить offline/reconnect
docker compose start backend-grpc
# дождаться heartbeat и восстановления stream
```

- [ ] После восстановления соединения клиент снова получает актуальную policy.
- [ ] Компактный и full-window режимы переключаются, контекст не теряется.

### Темы и типизированные команды

- [ ] Из настроек группы применяются `standard`, `vip`, `neon`, `minimal`.
- [ ] Тема обновляется после heartbeat без пересборки клиента.
- [ ] Для безопасной проверки команды отправьте только `theme.apply` или
  `display.lock` через operator UI/API; проверяйте переход команды из `queued` в
  `acknowledged`.
- [ ] Повторная доставка одной команды не создаёт второй локальный side effect.
- [ ] Не используйте для первого smoke `system.restart`, `shell.*` и любые
  непроверенные административные команды.

Для ручной проверки BFF используйте Swagger backend (окончание `/docs`) и операторский
JWT. Endpoint команды:
`POST /api/v1/workstations/{workstation_id}/commands` с заголовком
`Idempotency-Key`; статус читается через
`GET /api/v1/workstations/{workstation_id}/commands/{command_id}`.

### Сессия

- [ ] Создайте тестовую сессию из operator UI для этого workstation.
- [ ] Убедитесь, что в один момент времени не появляется вторая active-сессия.
- [ ] Выполните штатное завершение и отдельно interrupt-сценарий.
- [ ] После подтверждённого `session.stop` клиент переходит в
  `SessionLocked`/`Locked`, а повторное нажатие не создаёт вторую операцию.
- [ ] После теста верните исходное значение `restart_after_session` в policy.

### Обрыв и повторный запуск

- [ ] Остановите клиент во время offline и запустите снова: стартовое состояние
  снова `Locked`.
- [ ] Восстановите backend и проверьте heartbeat, stream и ACK после reconnect.
- [ ] В логах нет токенов, PIN, manager password, JWT или полного payload.

## 9. Проверка Windows kiosk

App-level access-gate не является границей безопасности Windows. Assigned Access
или Shell Launcher проверяйте только на отдельной тестовой машине с возможностью
восстановления. Не применяйте policy на ежедневном рабочем ПК.

Сначала сформируйте preview без изменения системы:

```powershell
.\scripts\configure-windows-kiosk.ps1 `
    -KioskUser "GameClubUser" `
    -ExecutablePath "C:\Program Files\GameClub\Client\GameClub.Client.exe"
```

Фактическое применение требует поддерживаемой редакции Enterprise/Education/IoT,
прав администратора/SYSTEM, отдельной kiosk-учётной записи и заранее проверенного
пути восстановления. После отдельного подтверждения можно применить policy через
`-Apply`; восстановление выполняется так:

```powershell
.\scripts\configure-windows-kiosk.ps1 -Apply -Restore
```

Проверяйте обычным пользователем запрет Explorer, Start Menu, Alt+Tab,
неразрешённых приложений, выхода в desktop и восстановление клиента после
перезапуска. Если редакция Windows или policy не позволяет выполнить этот пункт,
фиксируйте `NOT CHECKED`, а не `PASS`.

## 10. Release-проверка (после Debug smoke)

Публикация и installer выполняются только после успешного Debug smoke:

```powershell
.\scripts\publish-windows.ps1 -Architecture x64 -Configuration Release
.\scripts\build-installer.ps1 -Architecture x64 -Configuration Release
```

Проверьте установку на чистом тестовом профиле, автозапуск, recovery task и
удаление. В self-contained payload должен попасть весь необходимый runtime, а не
только EXE. Production secrets не должны вшиваться в EXE или передаваться в
обычный installer command line.

## 11. Что приложить к результату

- commit/version backend и Windows-клиента;
- edition и build Windows;
- вывод `dotnet --info` без секретов;
- архитектуру и конфигурацию сборки;
- результат restore/build/test;
- список пунктов smoke с `PASS`/`FAIL`/`NOT CHECKED`;
- время теста, workstation `device_id` и backend endpoint без токенов;
- скриншоты только без PIN, JWT, токенов и персональных данных;
- отдельное указание, проверялся ли Assigned Access/Shell Launcher.

## Критерий завершения

Нативная проверка считается закрытой, когда на реальном Windows-ПК пройдены
restore/build/test, locked/user/maintenance/session flows, reconnect, heartbeat,
темы, типизированная команда и повторный запуск. Kiosk и Release installer
отмечаются отдельными результатами; отсутствие поддерживаемой редакции Windows
не скрывается под общим статусом «клиент проверен».

Связанные документы:

- [README.md](../README.md) — конфигурация и локальный запуск;
- [ACCESS-GATE.md](ACCESS-GATE.md) — границы app-shell и Windows security;
- [SUPPORT-MATRIX.md](SUPPORT-MATRIX.md) — целевые версии и ограничения;
- [lockdown plan](../../plans/22-windows-lockdown/PLAN.md) — план lockdown;
- [verification matrix](../../plans/VERIFICATION.md) — общий verification matrix.
