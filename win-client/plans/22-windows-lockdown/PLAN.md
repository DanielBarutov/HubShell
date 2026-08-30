# План 22 — Windows lockdown по модели SmartShell/Gizmo

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `win-client/`  
Зависимости: Workstations, Sessions, Auth, installer/deployment

## Цель

Сделать Windows-клиент игрового места безопасной оболочкой: до авторизации
пользователь видит только access-gate, во время сессии получает разрешённый
клиентский интерфейс, а менеджер имеет отдельный контролируемый путь обслуживания.
Поведение должно быть близким к SmartShell/Gizmo, но без копирования их закрытой
реализации и без попытки заменить системную безопасность Windows кодом WinUI.

## Принцип двух границ

1. **Application shell** — состояние клиента, access-gate, session lock, темы,
   heartbeat, команды и безопасные ACK.
2. **Windows security boundary** — Assigned Access/Shell Launcher, стандартная
   учётная запись, ограничения Explorer/Start Menu/USB/дисков и политика запуска.

Обычный WinUI-процесс не считается достаточной защитой рабочего стола. Не применять
глобальные keyboard hooks, `BlockInput` или скрытые обходы Ctrl+Alt+Del как замену
политике ОС. Любое изменение системной политики должно быть явно подтверждено,
проверять права администратора и иметь обратимый сценарий.

## Целевые состояния клиента

- `Locked` — access-gate, рабочие действия скрыты.
- `User` — пользователь авторизован, разрешён только клиентский UI.
- `SessionLocked` — сессия остановлена или баланс исчерпан, ввод закрыт до нового
  входа; сервер остаётся источником истины.
- `Maintenance` — менеджер подтвердил отдельный пароль, пользовательские действия
  остановлены.
- `OfflineSafe` — нет актуального device-auth/heartbeat, новые операции запрещены,
  текущие опасные команды не считаются успешными без ACK.
- `ShellDisabled` — shell отключён только через подтверждённую maintenance-команду.

## Политика зоны

Для каждой группы ПК должна быть конфигурация:

- режим развёртывания: `app_gate`, `assigned_access`, `shell_launcher`;
- включён ли shell и автозапуск;
- разрешён ли пользовательский self-login;
- lock после остановки сессии и lock при исчерпании баланса;
- автоматический restart после подтверждённого `session.stop`;
- скрытые диски и запрет внешних накопителей;
- запрет Start Menu/переключения рабочих столов;
- список разрешённых приложений и список блокируемых окон по безопасным правилам;
- таймаут access-gate и grace period пополнения;
- версия политики и время последнего применения.

Сервер хранит декларативную policy, а клиент применяет только известные ключи.
Неизвестная или неподдерживаемая политика откатывается к безопасному профилю.

## Команды и безопасность

Оставить только versioned allowlist:

- `display.lock` / `display.unlock`;
- `session.start` / `session.stop`;
- `maintenance.enter` / `maintenance.exit`;
- `shell.enable` / `shell.disable`;
- `system.restart`;
- `policy.apply` с валидированной структурой.

Все изменяющие команды получают idempotency key, срок действия, device identity и
ACK. Произвольные shell-команды, пути к EXE и JSON с командами ОС запрещены.
Команда `display.lock` должна блокировать именно клиентский shell, а не вызывать
Windows Logon через `LockWorkStation`, если сценарий требует последующего входа
пользователя в GameClub.

## Этапы

1. [x] Зафиксировать различие shell-lock, maintenance, out-of-order и системного
   kiosk-режима в документации.
2. [x] Расширить domain/protobuf/heartbeat конфигурацией lockdown policy группы.
3. [x] Добавить application policy validator с allowlist тем, ограничений и
   команд; неизвестные поля не должны включать опасное поведение.
4. [x] Перевести `display.lock` в управляемый app-level lock и добавить тесты
   повторной доставки, offline-safe и session stop.
5. [x] Добавить dashboard-настройки политики зоны с preview, версией и audit.
6. [x] Подключить клиентскую визуализацию `Locked/User/SessionLocked/Maintenance`
   и безопасный возврат к locked после потери auth; policy приходит heartbeat-ом,
   а отключённый shell/self-login переводит клиент в locked.
7. [x] Подготовить Windows provisioning scripts с preview и поддержкой
   `-WhatIf` по умолчанию, backup/restore и явным `-Apply` для Assigned
   Access/Shell Launcher.
8. [ ] Добавить проверку Windows edition, обычного пользователя, автозапуска,
   restart/recovery и фактический smoke на Windows.
9. [ ] Добавить security profile для дисков, USB, Start Menu, desktop switching,
   блокируемых окон и разрешённых приложений только после native проверки.
10. [ ] Обновить installer: зарегистрировать клиент, применить выбранный профиль
    только по явному флагу, не выдавать production manager secret в командной строке.

## Критерии готовности

- До user login нет рабочих действий и персональных данных.
- Баланс/session stop блокируют shell и не открывают Windows logon вместо клиента.
- Manager maintenance требует отдельного проверяемого credential и audit.
- Потеря device-auth переводит клиент в `OfflineSafe`/`Locked`.
- Дубли команд не повторяют restart, lock или stop.
- Policy применяется только из allowlist и восстанавливается после перезапуска.
- На целевой Windows-машине проверено, что пользователь не получает Explorer,
  Start Menu и запрещённые приложения вне разрешённой политики.

## Ограничения и открытые решения

- Полный kiosk зависит от редакции Windows и Assigned Access/Shell Launcher.
- Политика ОС не должна применяться автоматически на машине разработчика.
- Настоящий Windows Service не нужен для UI shell; для recovery достаточно
  Scheduled Task, пока отдельный service-host не обоснован.
- Guest metered billing и device enrollment/rotation остаются отдельными планами.
