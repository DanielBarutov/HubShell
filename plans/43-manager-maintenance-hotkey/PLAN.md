# План 43 — менеджерский maintenance route и `Ctrl+Alt+P`

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `win-client/`  
Зависимости: [`22-windows-lockdown`](../22-windows-lockdown/PLAN.md),
[`24-windows-shell`](../24-windows-shell/PLAN.md),
[`38-avalonia-linux-first`](../38-avalonia-linux-first/PLAN.md)

## Цель

Добавить скрытый application-level route для менеджера: на заблокированном
access-gate комбинация `Ctrl+Alt+P` открывает форму отдельного manager password,
а успешная проверка переводит клиент в `Maintenance` без запуска пользовательской
сессии. В maintenance менеджер получает управляемый способ перейти к обычному
Windows Desktop.

Горячая клавиша является локальным событием активного окна клиента. Она не должна
перехватываться глобальным keyboard hook и не является заменой Assigned Access или
Shell Launcher.

## Границы первого среза

Входит:

- распознавание `Ctrl+Alt+P` в Avalonia production host;
- открытие manager password без публичной кнопки в пользовательском access-gate;
- сохранение состояния `Locked` до успешной проверки пароля;
- существующая PBKDF2-проверка, throttling неудачных попыток и очистка plaintext
  поля после обработки;
- переход в `Maintenance` без создания/возобновления клиентской игровой сессии;
- отдельное действие, позволяющее скрыть клиент в трей и показать рабочий стол;
- unit/UI checks для happy path, неверной комбинации, user session и manager state;
- обновление продуктового контракта, owner-plan, `plans/SUMMARY.md` и verification.

Не входит в первый срез:

- полноценное отключение Explorer, Start Menu, USB, дисков или других системных
  ограничений из runtime клиента; базовое подавление `Alt+Tab` и `Win+R` входит
  в отдельную политику lock плана 22;
- запуск произвольных процессов, shell-команд, PowerShell или изменение реестра;
- обход `Ctrl+Alt+Del`, `BlockInput` и глобальные hooks;
- выдача Windows administrator/UAC elevation по manager password;
- утверждение native Windows security без запуска под обычным пользователем.

## Целевой flow

1. Клиент находится в `Locked`, окно имеет фокус, менеджер нажимает `Ctrl+Alt+P`.
2. Клиент помечает событие обработанным, оставляет access-gate заблокированным,
   показывает форму пароля и переводит фокус в неё.
3. Неверный пароль оставляет `Locked`, показывает безопасное сообщение и следует
   существующему лимиту пяти попыток/30 секунд.
4. Верный пароль переводит состояние в `Maintenance`; пользовательская сессия
   не создаётся и портал не открывается.
5. В maintenance менеджер может скрыть клиент в трей, чтобы увидеть рабочий стол.
   Возврат к клиенту выполняется через tray; закрытие maintenance возвращает
   приложение в `Locked`.
6. Отключение системного shell остаётся отдельным будущим platform-policy flow:
   только явное действие, проверка administrator rights, backup/restore, audit и
   native Windows smoke.

## Архитектурное решение

- `MainViewModel` содержит проверяемое правило допуска shortcut и не знает об API
  Avalonia.
- UI-host преобразует событие клавиатуры в три boolean-признака и вызывает
  application boundary.
- `IClientWindowAdapter` отвечает только за window/tray presentation. Он не
  выполняет shell/system commands.
- `AccessGateCoordinator` остаётся единственным state machine для credential
  проверки и не получает обходного пути.
- Server manager verifier по-прежнему приходит только через authenticated
  heartbeat и хранится в памяти клиента; plaintext password не логируется и не
  сохраняется.

## Задачи

1. [x] Зафиксировать scope и ограничения в этом плане и product contracts.
2. [x] Добавить application-level matcher для `Ctrl+Alt+P`, доступный только из
   `Locked`, с тестами отрицательных состояний.
3. [x] Подключить shortcut к Avalonia production host и focus manager password.
4. [x] Зафиксировать единственный Avalonia production UI path.
5. [x] Добавить управляемый переход manager maintenance → tray/desktop без обхода
   Windows security policy.
6. [ ] Реализовать отдельный `shell.enable/disable` platform port после решения
   по политике OS, модели прав, audit и rollback.
7. [ ] Выполнить Windows native smoke: обычный пользователь, locked gate,
   shortcut, wrong-password throttle, maintenance, tray/desktop, restart и
   recovery.
8. [ ] Выполнить Assigned Access/Shell Launcher rehearsal и доказать, что
   пользователь не может покинуть разрешённую оболочку вне maintenance.

## Критерии готовности первого среза

- `Ctrl+Alt+P` открывает manager form только при активном `Locked` window.
- Одна клавиша `P`, `Ctrl+P`, `Alt+P` и shortcut в `User`/`Maintenance` не дают
  manager access.
- Пароль менеджера не хранится в исходниках, UI state после обработки или логах.
- До правильного пароля остаются скрытыми desktop/manager actions.
- Правильный пароль переводит клиент в `Maintenance` без active portal session.
- Закрытие maintenance очищает доступ и возвращает `Locked`.
- Linux test/build подтверждают portable behavior; Windows native и OS kiosk
  claims остаются отдельными непроверенными критериями.

## Проверки

```bash
cd /home/daniel/HubShell
dotnet test win-client/GameClub.Client.sln -p:Platform=x64
dotnet build win-client/GameClub.Client.Windows.sln -p:Platform=x64
```

Native Windows:

```powershell
Set-Location "C:\Git\HubShell"
.\win-client\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Сборка/тесты Linux не считаются доказательством фактического Windows shortcut,
tray, desktop switching или kiosk security.

## Риски и открытые вопросы

- Если окно потеряло фокус, локальный shortcut не срабатывает; глобальный hook
  намеренно не добавляется.
- Скрытие окна в трей показывает desktop только на уровне application shell и не
  снимает системные политики ОС.
- Нужно отдельно решить, должен ли manager maintenance получать собственный
  временный token/session audit и какие именно OS policies он может временно
  отключать.
