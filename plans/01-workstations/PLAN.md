# План 01 — Workstations / PC Management

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: `00-foundation`, базовые решения `04-auth-security`

## Цель

Реализовать управление игровыми ПК и надёжную связь backend с Windows-клиентом: регистрация, heartbeat, актуальное состояние, группы/зоны и команды с подтверждением.

## Входит в план

- device identity и регистрация ПК;
- группы оборудования, зоны и позиция на карте;
- состояния `unknown`, `online`, `stale`, `offline`, `disabled`;
- heartbeat, last seen и последняя ошибка;
- версия клиента и capabilities;
- команды, deadline, retry и acknowledgement;
- аудит административных команд;
- данные для карты и таблицы dashboard.

## Не входит

- игровая сессия и биллинг;
- списание баланса;
- произвольный запуск опасных системных команд;
- полноценный auto-update;
- UI-реализация frontend/WinUI.

## Домен и контракты

Нужно определить `WorkstationId`, стабильный `device_id`, `GroupId`, позицию, технический status и command state. Регистрация не делает ПК online. Online/stale/offline определяется сервером по heartbeat и конфигурируемому порогу. Disabled не получает обычные команды.

Спроектировать versioned protobuf для регистрации, heartbeat, списка ПК, команд, acknowledgement и operator management групп/зон.

## Задачи

1. [x] Зафиксировать ownership данных и state machine.
2. [x] Описать protobuf RPC/messages и безопасные error reasons.
3. [x] Реализовать Domain transitions и value objects.
4. [x] Реализовать Application через порты `typing.Protocol`.
5. [x] Реализовать Repository, миграции и индексы.
6. [x] Реализовать gRPC handlers, permissions и общий audit interceptor для `Register`, `Heartbeat`, `List`, `Disable`.
7. [x] Реализовать command delivery/ack с idempotency: durable queue record, server-streaming delivery, device acknowledgement и expiry; retry policy остаётся.
8. [x] Подготовить данные карты/таблицы и групповых настроек.
9. [x] Добавить сохраняемые настройки групп и allowlist тем, передавать тему
   в HTTP/gRPC heartbeat для Windows-клиента.
10. [x] Добавить unit tests, memory concurrency и базовый API/DB smoke test; PostgreSQL contract/concurrency tests остаются.
11. [x] Добавить operator CRUD-срез для групп/зон и игровых мест: создание и
    изменение группы, изменение названия/зоны/позиции ПК и безопасное удаление
    через архивирование без физического удаления истории.
12. [x] Добавить versioned декларативную lockdown policy группы: режим
    `app_gate`/`assigned_access`/`shell_launcher`, app-shell поведение после
    сессии и allowlist ограничений Windows; native применение остаётся планом
    `plans/22-windows-lockdown`.

Текущий транспортный срез: gRPC handlers для workstations, clients, catalog и reservations
подключены к общим Application-сервисам. Для workstations добавлены `DispatchCommand`,
`WatchCommands` и `AcknowledgeCommand`, проверка device JWT, durable command records и
capabilities в heartbeat. Команды имеют настраиваемый TTL и переходят в `expired` до
delivery/ack после истечения срока. Windows-клиент получает dev device JWT, выполняет только
разрешённые `display.lock`/`theme.apply` и отправляет acknowledgement; `session.start/stop`
проходят через защищённый SessionService gateway с device identity, а локальные игровые
процессы остаются вне этого среза. Клиентский reconnect использует backoff до 30 секунд
и повторно отправляет сохранённый результат ACK без повторного исполнения локального side effect;
серверная доставка остаётся durable и идемпотентной по command id/idempotency key.
Общий gRPC audit interceptor фиксирует изменяющие RPC без
payload. Web BFF возвращает capabilities и
поддерживает отправку типизированной команды из правой панели ПК, чтение статуса команды
и polling до ACK. Карта использует состояние и last-seen из backend.
Настройки групп хранятся в `workstation_groups`, доступны через защищённый HTTP
BFF и RPC `ListGroups`/`UpsertGroup`. Группа имеет allowlist theme keys; выбранная
тема возвращается вместе с workstation heartbeat, поэтому Win-клиент может
применить её после reconnect без отдельной команды. Та же heartbeat boundary
передаёт валидированную декларативную lockdown policy группы; backend хранит её
как JSON с безопасным default и сериализует в protobuf, но не применяет Windows
политику непосредственно.

Management API также поддерживает `POST`/`PUT`/`DELETE` для зон и ПК. Удаление ПК
идемпотентно переводит запись в архив, исключает её из рабочих списков и оставляет
аудит/историю. Позиция карты хранится отдельно от device identity и может быть
изменена оператором.

## Критерии готовности

- heartbeat обновляет состояние идемпотентно;
- просроченный heartbeat даёт понятный stale/offline status;
- disabled ПК не принимает обычные команды;
- duplicate command не создаёт второй эффект;
- оператор видит status, причину и last seen;
- изменяющие действия авторизуются и аудируются.

## Риски

- неправильный threshold создаст ложный статус;
- повтор команды может вызвать опасный эффект;
- Windows API и права пользователя отличаются между версиями Windows.

## Проверки

- state-machine unit tests;
- PostgreSQL repository tests;
- gRPC contract tests;
- timeout/retry/duplicate/reconnect tests;
- permission tests;
- mock Windows-client smoke test.

## Открытые вопросы

- bootstrap token или другой способ первой регистрации;
- нужны ли `club_id`/`location_id`;
- список команд MVP;
- polling, server streaming или events для dashboard;
- нужен ли отдельный Windows Service.
