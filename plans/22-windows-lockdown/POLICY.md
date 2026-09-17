# Политика ограничений Windows-клиента v1

Этот документ фиксирует, где именно должны применяться ограничения игрового ПК.
Access-gate (экран входа на Windows-клиенте) относится к приложению; Windows
policy относится к пользовательской учётной записи и оболочке рабочего стола.
Клиентское приложение отвечает за свой access-gate и рабочие состояния, а
Windows отвечает за границу рабочего стола. Поля policy от backend сами по себе
не являются доказательством того, что ограничение реально применилось.

## 1. Профили развёртывания

| Профиль | Назначение | Граница безопасности | Статус |
| --- | --- | --- | --- |
| `app_gate` | разработка, диагностика, fallback | только application shell | уже поддержан как безопасный, но не kiosk |
| `shell_launcher` | production игровой ПК с desktop Avalonia | Windows Shell Launcher заменяет `Explorer.exe` для стандартного kiosk-пользователя | целевой production-профиль v1 |
| `assigned_access` | ограниченный desktop с несколькими разрешёнными приложениями | Assigned Access + allowlist приложений | отдельный профиль, не смешивать с Shell Launcher |

Для текущего Win32/Avalonia-клиента целевым production-профилем считается
`shell_launcher`: desktop-приложение запускается как оболочка пользователя.
`assigned_access` применяется только после отдельного решения о multi-app
allowlist и native rehearsal. На одной машине нельзя одновременно считать
активными Shell Launcher и Assigned Access.

`app_gate` не обещает защитить от Explorer, Task Manager, другого desktop,
PowerShell или завершения процесса. Для текущего базового lock в `Locked` есть
отдельные требования к `Topmost`, `Alt+Tab` и `Win+R`, но они не превращают
`app_gate` в полноценный kiosk и не запрещают запуск приложений.

## 2. Матрица ограничений

| Ограничение | Кто применяет | Значение v1 | Что считается доказательством |
| --- | --- | --- | --- |
| До входа скрыть профиль, баланс и действия | клиент | `Locked` | unit/UI tests + native smoke |
| После входа разрешить только GameClub UI | клиент | `User`/`SessionLocked` | state tests + native smoke |
| Потеря heartbeat/device-auth | клиент | `OfflineSafe`/`Locked`, без ослабления OS policy | reconnect/401/403 smoke |
| Explorer, Start, Taskbar, desktop switching, `Alt+Tab` | Windows policy | Shell Launcher или Assigned Access | native smoke под стандартным kiosk-пользователем |
| `Win+R` | local UI-handler в access-gate | подавлять только в `Locked`; после `User`/покупки тарифа комбинация снова доступна | native smoke до входа, после входа и после logout |
| `Ctrl+Alt+Del`, Task Manager, UAC и смена пользователя | Windows security boundary | не перехватывать; проверить, что access-gate остаётся поверх обычного Task Manager | native smoke и проверка локальной политики |
| USB-клавиатура/мышь | Windows policy | оставить разрешёнными для работы клиента | native smoke |
| USB Mass Storage | Windows policy | запрещать отдельной device policy, не через обработчик USB в клиенте | подключение накопителя под kiosk-пользователем |
| Доступ к дискам | Windows ACL/AppLocker/политика | `hidden_drives` только скрывает UI; не считать его защитой | попытка открыть путь и запуск приложения |
| Произвольные EXE, PowerShell, cmd, script host | Windows AppLocker/WDAC/Assigned Access | запрещать allowlist-политикой; клиент не запускает их | native smoke + policy audit |
| Manager maintenance | клиент + credential | отдельный PBKDF2 verifier, без user session | state tests + native smoke |
| Переход менеджера на Desktop | deployment profile | в `app_gate` допустимо скрыть client в tray; в `shell_launcher` не обещать Explorer Desktop | профильный native smoke |
| Restart/recovery | Windows deployment + клиентский adapter | recovery запускает только подписанный/известный клиент | kill/restart/reconnect smoke |

`blocked_window_rules` и `allowed_application_ids` являются декларацией для
будущего Windows enforcement adapter. Пока adapter не применяет их и не отдаёт
подтверждение, backend должен показывать policy как `desired`, а не `applied`.

## 3. Manager maintenance

Maintenance не должен быть способом выключить kiosk-политику из пользовательского
процесса.

- В `app_gate` `Ctrl+Alt+P` открывает форму manager password; после проверки
  менеджер может скрыть application shell в tray.
- В `shell_launcher` кнопка «Перейти к рабочему столу» не должна обещать
  `Explorer.exe`: его место занято shell-клиентом. Для полноценного обслуживания
  нужен отдельный администраторский или maintenance account и контролируемый
  sign-out/sign-in flow.
- Manager password не даёт UAC elevation, локального администратора или права
  менять registry/GPO/Assigned Access.
- Временное изменение Windows policy выполняется только отдельным provisioning
  инструментом с проверкой прав, backup, audit, explicit apply и restore.

## 3a. Базовый lock и offline manager access

- При старте в `Locked` Windows production adapter выставляет `Topmost`; Linux
  host не является доказательством поведения Windows-окон.
- Локальный UI-handler подавляет `Alt+Tab` и `Win+R`, когда access-gate имеет
  состояние `Locked`. Глобальный keyboard hook и `BlockInput` не используются.
- `Ctrl+Alt+Del` оставляется системным; Task Manager не запрещается и должен быть
  отдельно проверен на Windows на предмет положения под access-gate.
- Windows user policy `NoRun=1` не применяется в базовом `app_gate`: она
  действует на всю учётную запись и поэтому нарушила бы требование вернуть
  `Win+R` после входа. Для отдельного полного kiosk-профиля есть
  `scripts/configure-windows-user-policy.ps1`, но его нельзя запускать в этом
  базовом сценарии.
- При запуске клиент имеет встроенный PBKDF2 verifier для пароля `password`.
  Валидный verifier с сервера заменяет его в памяти при старте/heartbeat;
  невалидный или пустой verifier fallback не затирает.
- При потере сервера уже загруженный verifier продолжает работать в памяти.
  После холодного offline-запуска работает fallback `password`; серверный пароль
  после перезапуска без сервера не восстанавливается, потому что verifier не
  сохраняется на диск.

## 3b. Опциональная policy полного kiosk

Если в будущем потребуется ограничить всю kiosk-учётную запись, включая уже
авторизованного пользователя, provisioning может включить `NoRun=1` в
`HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer`. Microsoft
описывает это как запрет Run и `Win+R`: [NoRun policy](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/policy/adhering-to-system-policy-settings).
Это отдельный профиль, не часть базового `app_gate`; менеджер для него должен
использовать отдельную maintenance/admin-учётную запись.

## 4. Жизненный цикл policy

1. Backend хранит декларативную policy группы с монотонной `version`.
2. Heartbeat доставляет desired policy конкретному device после device-auth.
3. Клиент валидирует только известные значения и применяет безопасную
   application-часть: login/lock/restart/session behavior.
4. Windows-часть применяется provisioning/deployment boundary, а не обычным
   client runtime и не произвольной командой из payload.
5. Клиент сообщает `desired_version`, `applied_version`, `enforcement_mode` и
   `last_error` для диагностики drift.
6. При неизвестном режиме или невалидной policy нельзя молча ослаблять профиль:
   client остаётся `Locked`, OS policy не меняется, ошибка фиксируется в audit.
7. При неуспешном применении Windows policy восстанавливается предыдущий backup.
   Если restore не подтверждён, устройство не считается готовым к выдаче игроку.

## 5. Профиль по умолчанию для зала

Рекомендуемый production baseline:

- стандартный локальный kiosk-пользователь без администратора;
- `deployment_mode = shell_launcher`;
- `shell_enabled = true` трактуется как «клиентская оболочка разрешена», а не
  как разрешение `Explorer.exe`;
- `user_self_login_enabled = true`;
- `lock_after_session = true`;
- `restart_after_session = true` только после подтверждённого server-side stop;
- USB HID разрешён, USB Mass Storage запрещён;
- доступ к системным дискам и запуск произвольных приложений запрещены policy
  boundary, а не только `hidden_drives`;
- manager maintenance доступен, но не получает права изменения Windows policy;
- fallback при drift — `Locked`/`OfflineSafe`, без автоматического перехода к
  менее строгому профилю.

## 6. Release gates

До production нельзя считать policy готовой по одному Linux build или наличию
JSON/protobuf-полей. Нужны отдельные результаты:

- source/unit/API: validation, serialization, unknown-policy fail-closed;
- native Windows: обычный kiosk-пользователь, startup, login, logout, restart,
  reconnect, manager route и recovery;
- basic lock: `Topmost`, `Alt+Tab`, `Win+R`, `Ctrl+Alt+Del` → Task Manager under
  shell, offline manager password and fallback;
- basic lock lifecycle: `Win+R` блокируется в `Locked`, работает после `User` и
  снова блокируется после logout;
- optional full-kiosk policy: отдельный `NoRun=1` provisioning с backup/restore,
  если потребуется ограничивать `Win+R` после входа тоже;
- OS boundary: Explorer/Start/Task Manager/desktop switching,
  PowerShell/cmd, USB Mass Storage и разрешённые приложения;
- rollback: restore previous profile, sign-out/sign-in and recovery after client
  crash;
- audit: policy version, target workstation, actor, apply/restore result and
  error, без manager password и токенов.

Только после этих gates профиль получает статус `production_ready`.

## 7. Текущий разрыв реализации

На текущем checkout policy уже хранится в backend и приходит через heartbeat,
но Windows-адаптер реально использует только `shell_enabled`,
`user_self_login_enabled`, lock-after-session и restart-after-session. Поля
дисков, USB, Start Menu, desktop switching, blocked windows и allowed apps пока
транспортируются как desired state и не применяются локально.

`configure-windows-kiosk.ps1` настраивает Shell Launcher и его XML backup;
Assigned Access, optional features, startup/recovery и полная проверка drift в
этот backup не входят. Поэтому текущий script нельзя описывать как готовый
универсальный provisioning для всех трёх профилей.

Отдельно нужно согласовать канонический запуск kiosk-пользователя: обычный
`HKCU Run` для пользователя установки не должен считаться заменой Shell Launcher
для `KioskUser`. До этого решения installer не получает статус
`production_ready`.
