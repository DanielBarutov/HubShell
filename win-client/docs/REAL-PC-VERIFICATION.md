# Функциональная проверка Windows-клиента на реальном ПК

Этот документ начинается после успешного выполнения
[`WINDOWS-BUILD-AND-RUN.md`](WINDOWS-BUILD-AND-RUN.md). Здесь нет команд сборки:
его задача — проверить фактическое поведение клиента на Windows и зафиксировать
результат как `PASS`, `FAIL` или `NOT CHECKED`.

## 1. Тестовые условия

Машина сборки/администратора:

```text
C:\Git\HubShell
```

Игровой ПК:

```text
C:\GameClub\Client\GameClub.Client.exe
```

Проверять нужно под обычным пользователем, не под администратором. Для первого
smoke не включайте Assigned Access или Shell Launcher. У вас должны быть:

- Windows 10 build 17763+ или Windows 11;
- Release single-file EXE, собранный для архитектуры игрового ПК;
- доступный backend по production HTTP/gRPC в private LAN либо HTTPS для внешнего адреса;
- операторский доступ к web-админке;
- отдельные тестовые workstation, клиент/гость и тариф.

Запуск и визуальная проверка должны выполняться в интерактивной Windows-сессии
пользователя (`SessionId` обычно `1` или другой активный номер), напрямую на
ПК или по RDP. SSH-сеанс обычно работает в Session 0: он подходит для сборки,
публикации и чтения логов, но не для проверки WinUI-окна.

На игровом ПК не должны требоваться `dotnet`, Visual Studio, Windows App SDK,
PowerShell setup, env-переменные, `device_id`, bootstrap token или PIN hash.

## 2. Установка и первый запуск

Скопируйте EXE в `C:\GameClub\Client` и запустите двойным кликом обычного
пользователя. Не копируйте EXE отдельно из `bin` или из folder-publish.

Проверьте:

- [ ] процесс появляется и окно не закрывается сразу;
- [ ] клиент стартует в fullscreen borderless Locked shell;
- [ ] нет стандартного title bar и системных кнопок окна;
- [ ] до назначения места не видны баланс, профиль и рабочие операции;
- [ ] отображается ожидание привязки ПК по MAC;
- [ ] создаётся технический installation identity в `%LocalAppData%\GameClub\Client`;
- [ ] при старте обновляется `%LocalAppData%\GameClub\startup.log`;
- [ ] в локальных файлах нет JWT, паролей, PIN и полного сетевого payload.

Если EXE закрывается, остановите этот checklist и выполните раздел
`Startup diagnostics` в [`WINDOWS-BUILD-AND-RUN.md`](WINDOWS-BUILD-AND-RUN.md).

## 3. Назначение workstation

В web-админке:

1. Создайте workstation без ручного `device_id`.
2. Укажите MAC-адрес игрового ПК.
3. Выберите имя, группу/зону и позицию.
4. Убедитесь, что workstation не disabled.

Проверьте:

- [ ] до назначения состояние остаётся `pending`/«Ожидаем привязку»;
- [ ] после назначения клиент переходит в `approved`/connected;
- [ ] отправляется heartbeat с device identity;
- [ ] приходит тема группы и применяется безопасная палитра;
- [ ] приходит lockdown policy;
- [ ] installation identity не позволяет другой установке молча занять это место.

MAC можно посмотреть штатными средствами Windows. Не включайте полный MAC в
публичный отчёт, если для проверки достаточно имени workstation и последних
символов адреса.

## 4. Access-gate и portal

- [ ] экран до входа заблокирован;
- [ ] регистрация выполняется один раз по nickname, телефону и PIN;
- [ ] вход работает по nickname и canonical phone;
- [ ] во время offline/reconnecting новый вход недоступен;
- [ ] server entry decision может отклонить вход по правилам брони;
- [ ] после входа видны только данные текущего пользователя;
- [ ] отображаются баланс, бонусы, пополнения, списания, товары, тарифы,
  сессии и доступное время;
- [ ] logout очищает snapshot и возвращает Locked;
- [ ] истёкший или отозванный client token возвращает Locked без показа чужих
  данных;
- [ ] `Ctrl+Alt+P` открывает отдельный manager maintenance;
- [ ] закрытие maintenance снова возвращает Locked;
- [ ] manager credential не появляется в пользовательском экране или логах.

## 5. Сессии, тарифы и повторные действия

- [ ] старт сессии проходит через backend и не создаёт вторую active session;
- [ ] активная сессия отображается в виджете;
- [ ] завершение сессии разрешено только после server result;
- [ ] после stop применяется заданная policy lock/restart;
- [ ] package queue и explicit activation показывают server result;
- [ ] совместимый следующий пакет активируется по правилам backend;
- [ ] недостаток баланса/времени завершает сессию и блокирует клиент;
- [ ] повторный клик по login, stop, activation или sale не создаёт двойной
  debit, sale или active session.

## 6. Сеть, heartbeat и restart

Проверяйте на тестовой машине, не в рабочей сессии:

1. Остановите backend gRPC или временно заблокируйте соединение.
2. Убедитесь, что виджет показывает offline/reconnecting, а не ложный success.
3. Восстановите backend/сеть.
4. Дождитесь heartbeat, reconnect, theme и policy.

Отметьте:

- [ ] workstation становится online только после актуального heartbeat;
- [ ] временная потеря сети не удаляет активную сессию;
- [ ] offline до входа не позволяет создать новую сессию;
- [ ] после восстановления не повторяются server side effects;
- [ ] после перезапуска клиент снова стартует Locked;
- [ ] installation identity сохраняется, а лишние персональные данные и секреты
  не появляются в AppData.

Для локального Compose backend на машине с backend можно использовать:

```powershell
docker compose stop backend-grpc
# проверить offline/reconnecting на игровом ПК
docker compose start backend-grpc
```

Не используйте для первого smoke команды `system.restart`, `shell.*` и другие
непроверенные административные действия.

## 7. Kiosk boundary — отдельный этап

Fullscreen WinUI не запрещает `Ctrl+Alt+Del`, Task Manager, другой desktop,
Explorer или выход из процесса. В текущем репозитории скрипт настраивает только
Shell Launcher; Assigned Access через него не настраивается. Проверяйте kiosk
только на отдельной тестовой машине после обычного smoke.

Сначала сформируйте preview без изменения политики:

```powershell
Set-Location "C:\Git\HubShell\win-client"
.\scripts\configure-windows-kiosk.ps1 `
  -KioskUser "GameClubUser" `
  -ExecutablePath "C:\GameClub\Client\GameClub.Client.exe"
```

Применение требует отдельной точки восстановления, административных прав и
SYSTEM-контекста. Обычный elevated PowerShell недостаточен: сам скрипт
проверяет SID SYSTEM. Выполните из elevated PowerShell:

```powershell
$taskName = "GameClub.ConfigureShellLauncher"
$action = New-ScheduledTaskAction `
  -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Git\HubShell\win-client\scripts\configure-windows-kiosk.ps1" -Apply -KioskUser "GameClubUser" -ExecutablePath "C:\GameClub\Client\GameClub.Client.exe"'
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Force
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 5
Get-ScheduledTaskInfo -TaskName $taskName
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
```

В выводе проверьте `LastTaskResult`. Для восстановления используйте тот же
шаблон SYSTEM-задачи, заменив аргументы запуска на:

```text
-Apply -Restore
```

Проверить под kiosk-пользователем:

- [ ] не запускаются Explorer, Start Menu, desktop и произвольные приложения;
- [ ] `Alt+Tab` не позволяет уйти в другой пользовательский сценарий;
- [ ] клиент восстанавливается после завершения;
- [ ] есть документированный rollback.

Если редакция Windows или политика организации не поддерживает нужный режим,
отмечайте `NOT CHECKED`, а не `PASS`.

## 8. Отчёт

Зафиксируйте:

- commit: `git -C C:\Git\HubShell rev-parse --short HEAD`;
- Windows edition/build;
- архитектуру ПК и EXE;
- тип артефакта: folder-publish или single-file;
- путь запуска;
- результаты пунктов как `PASS`, `FAIL` или `NOT CHECKED`;
- reconnect, restart, kiosk и transport mode (private HTTP или external HTTPS) отдельно;
- каталог диагностики, если EXE завершался с ошибкой.

Native Windows-проверка считается закрытой только после фактического запуска и
ручного smoke. Source-level и Linux-проверки этого не заменяют.
