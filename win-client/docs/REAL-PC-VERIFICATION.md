# Проверка Windows-клиента на реальном ПК

Этот документ проверяет целевой deployment: один EXE собирается на админском
Windows-ПК, затем переносится на игровой ПК и запускается без консольной
настройки. Это не означает, что для Linux нет библиотек: NuGet-пакеты и
кроссплатформенная генерация protobuf доступны, поэтому Linux подтверждает
исходники, контракты и серверные тесты. Полный target этого проекта всё равно
зависит от WinUI 3, Windows SDK, XAML compiler и Windows native assets
(`win-x64`/`win-x86`/`win-arm64`), поэтому `GameClub.Client.exe`, fullscreen и
kiosk нужно собирать и проверять на физическом Windows-ПК.

## 1. Что нужно заранее

- Windows 10 build 17763+ или Windows 11 на тестовом игровом ПК;
- админский Windows-ПК с Visual Studio 2022, workload `.NET desktop
  development`, .NET 8 SDK и Windows SDK;
- backend GameClub, доступный игровому ПК по HTTPS/gRPC TLS;
- операторский доступ к web-админке;
- отдельная тестовая workstation и тестовый пользователь.

Для обычного клиента не нужны Visual Studio, .NET SDK и права администратора.
Архитектура `x64` подходит для обычного игрового ПК.

## 2. Проверить backend и порты

На машине, где запущен backend, администратор может поднять dev-стек:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --build
docker compose ps
(Invoke-WebRequest http://127.0.0.1:8100/health/ready).StatusCode
```

Ожидаемый readiness — `200`. Для реального игрового ПК `127.0.0.1` не подходит:
в EXE нужно зашить доступный DNS/LAN-адрес backend и защищённые endpoint'ы.
Dev HTTP loopback не является способом подключения удалённого клиента.

Текущий Compose публикует host-порты frontend `3100`, HTTP `8100`, gRPC `51051`,
PostgreSQL `55432` и Redis `56379`. В клиент вшивается только HTTP auth и gRPC
адрес; PostgreSQL/Redis клиенту не нужны.

## 3. Один раз собрать portable EXE

На админском Windows-ПК из каталога `win-client` выполните:

```powershell
.\scripts\build-portable-exe.ps1 `
  -Architecture x64 `
  -Configuration Release `
  -EnvironmentName production `
  -AuthAddress "https://api.example.club:8100" `
  -GrpcAddress "https://api.example.club:51051"
```

Подставьте реальные адреса вашей инфраструктуры. Результат:

```text
artifacts\portable\win-x64\Release\GameClub.Client.exe
```

Сохраните SHA-256 из вывода скрипта. Не копируйте в EXE или командную строку
секреты, JWT, bootstrap token, PIN-хэши или `device_id`.

## 4. Запустить клиент до назначения

1. Скопируйте один `GameClub.Client.exe` на игровой ПК.
2. Запустите двойным кликом обычным пользователем, не от имени администратора.
3. Убедитесь, что клиент стартует в полноэкранном borderless shell, а не в
   обычном окне с desktop-фоном.
4. До назначения места клиент показывает ожидание привязки по MAC и не открывает
   рабочие действия.
5. В логах и файлах не должно быть JWT, паролей и полного payload.

На игровом ПК не выполняются `dotnet`, PowerShell setup, установка SDK,
создание env-переменных или генерация PIN-хэшей.

## 5. Назначить MAC в админке

1. Откройте web-админку на админском ПК.
2. Создайте workstation без ручного `device_id`.
3. Введите MAC игрового ПК, выберите имя, группу/зону и позицию.
4. Убедитесь, что место имеет разрешённое состояние и не disabled.
5. Дождитесь автоматического перехода клиента из `pending` в `approved`.

MAC можно посмотреть штатными средствами Windows, например в сведениях
сетевого адаптера. В production используйте подтверждённый MAC из инвентаризации;
MAC сам по себе не считается полноценной аутентификацией.

После первого approved backend связывает workstation с техническим
`installation_id` в `%LocalAppData%\GameClub\Client`. Другая установка не может
молча заменить эту привязку. Проверяйте также heartbeat, тему группы и policy.

## 6. Пользовательский smoke

На Locked-экране проверить:

- [ ] fullscreen, borderless, focus и отсутствие обычного title bar;
- [ ] до входа не видны баланс, история и рабочие операции;
- [ ] новая регистрация по nickname, телефону и PIN проходит один раз;
- [ ] повторный запуск/вход не создаёт дублирующий аккаунт или ledger;
- [ ] вход работает по nickname и canonical phone;
- [ ] видны только данные текущего пользователя: баланс, бонусы, пополнения,
  списания, поминутные charges, товары, тарифы, сессии и доступное время;
- [ ] logout очищает пользовательский snapshot и возвращает Locked;
- [ ] истёкший/отозванный client token возвращает Locked без показа чужих данных;
- [ ] `Ctrl+Alt+P` открывает только manager maintenance по отдельному паролю;
- [ ] закрытие maintenance снова возвращает Locked.

Одна и та же операция не должна повторяться при двойном клике. Ошибка backend
должна показываться понятным состоянием, а не оставлять пользователя в
полусостоянии активной сессии.

## 7. Связь, настройки и сессия

- [ ] workstation становится online только после актуального heartbeat;
- [ ] остановка backend/gRPC показывает offline/reconnect, а не ложный успех;
- [ ] после восстановления соединения возвращаются heartbeat, stream, тема и
  policy без ручного ввода токена;
- [ ] смена темы группы применяется после обновления настроек;
- [ ] старт/stop сессии проходит через backend и не создаёт вторую active-сессию;
- [ ] поминутная сессия отражается в доступном времени и debit history;
- [ ] повторное нажатие stop/sale не создаёт второй debit, sale или active session;
- [ ] после restart клиент снова стартует Locked и повторяет enrollment по своей
  installation identity.

Для управляемого сетевого теста на backend-хосте:

```powershell
docker compose stop backend-grpc
# проверить offline/reconnect на игровом ПК
docker compose start backend-grpc
# дождаться heartbeat и восстановления stream
```

Не используйте для первого smoke команды `system.restart`, `shell.*` и другие
непроверенные административные действия.

## 8. Windows kiosk boundary

App-level Locked shell не запрещает выход в Windows. На отдельной тестовой
машине сформируйте preview:

```powershell
.\scripts\configure-windows-kiosk.ps1 `
  -KioskUser "GameClubUser" `
  -ExecutablePath "C:\GameClub\GameClub.Client.exe"
```

Применение выполняйте только после сохранения точки восстановления и отдельного
подтверждения:

```powershell
.\scripts\configure-windows-kiosk.ps1 -Apply
```

Проверьте обычным пользователем отсутствие Explorer, Start Menu, desktop,
Alt+Tab и произвольных приложений, а также recovery. Для возврата:

```powershell
.\scripts\configure-windows-kiosk.ps1 -Apply -Restore
```

Если редакция Windows не поддерживает Assigned Access/Shell Launcher, отмечайте
пункт `NOT CHECKED`, а не `PASS`.

## 9. Native build и release-check

На машине разработчика/администратора, не на игровом ПК:

```powershell
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Успехом считаются безошибочные `dotnet restore`, `dotnet build` и `dotnet test`.
Для solution используйте `-p:Platform=x64`, а не `--arch`.

После Debug smoke снова соберите Release portable, проверьте SHA-256 и запустите
файл на чистом профиле игрового ПК. Отдельная folder-публикация и installer
нужны только для сценариев автозапуска/recovery; основной пользовательский
сценарий остаётся «скопировать один EXE и запустить».

### Если появляется MC6000 и `Microsoft.WinFX.targets`

Этот WinUI 3 проект не использует WPF или Windows Forms: эффективные свойства
`UseWPF` и `UseWindowsForms` должны быть `false`. После обновления checkout
проверьте их и удалите только промежуточные каталоги проекта:

```powershell
dotnet msbuild .\src\GameClub.Client\GameClub.Client.csproj `
  -getProperty:UseWPF,UseWindowsForms,TargetFramework
Remove-Item .\src\GameClub.Client\bin -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item .\src\GameClub.Client\obj -Recurse -Force -ErrorAction SilentlyContinue
```

Ожидаемый результат — `UseWPF=false` и `UseWindowsForms=false`. Затем повторите
`verify-windows.ps1` или `build-portable-exe.ps1`; оба скрипта передают эти
значения явно. Если при таких значениях ошибка повторяется, сохраните binlog:

```powershell
dotnet publish .\src\GameClub.Client\GameClub.Client.csproj `
  -c Release -r win-x64 --self-contained true `
  -p:UseWPF=false -p:UseWindowsForms=false -bl:gameclub-client.binlog
```

## 10. Отчёт о проверке

Зафиксируйте:

- версию/commit backend и клиента;
- edition/build Windows, архитектуру и конфигурацию;
- вывод `dotnet --info` без секретов;
- restore/build/test и SHA-256 EXE;
- workstation MAC без лишних персональных данных;
- пункты smoke как `PASS`, `FAIL` или `NOT CHECKED`;
- отдельно: проверялись ли reconnect, kiosk, recovery и production TLS.

Нативная проверка считается закрытой только после реального запуска и ручного
smoke. Linux-тесты и статический анализ не заменяют этот результат.

Связанные документы: [README.md](../README.md),
[ACCESS-GATE.md](ACCESS-GATE.md), [SUPPORT-MATRIX.md](SUPPORT-MATRIX.md),
[`plans/28-integration-checks`](../../plans/28-integration-checks/PLAN.md).
