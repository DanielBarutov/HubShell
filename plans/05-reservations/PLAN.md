# План 05 — Reservations / Booking

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: `00-foundation`, `01-workstations`, `02-clients-guests`, `03-catalog-time-tariffs`, `04-auth-security`

## Цель

Реализовать бронирование игровых мест и времени для оператора, а затем подготовить тот же контракт для online-бронирования клиентом или гостем.

## Входит в план

- доступность ПК на период;
- бронь одного или нескольких мест;
- бронь клиента или гостя;
- создание, изменение, отмена, завершение и no-show;
- конфликт с активной сессией, другой бронью и disabled/offline ПК;
- strict reservation, grace period и опоздание;
- временная шкала бронирований;
- snapshot тарифа/quote или явная ссылка на версию тарифа;
- idempotency и audit.

## Не входит

- внешний платёж и эквайринг;
- полноценная игровая сессия;
- автоматическое списание баланса без отдельного session/payment решения;
- push/SMS/Telegram notifications;
- онлайн-приложение клиента целиком.

## Ownership и доменные правила

Reservation владеет жизненным циклом брони и конфликтами. Workstations владеет ресурсом и техническим состоянием ПК, Clients — профилем, Catalog — tariff/quote. Создание брони на несколько ПК должно быть атомарным: либо забронированы все выбранные места, либо ни одно.

Минимальная модель: `ReservationId`, resource/workstation IDs, client/guest reference, start/end в timezone клуба, status, source, notes, tariff reference/snapshot, created/updated/cancelled metadata и idempotency key.

Нужно явно решить, что происходит при опоздании, no-show, отключении ПК, переносе места и пересечении полуночи. Конфликты проверяются транзакционно на стороне backend, а не только в UI.

## UX-направление

По мотивам SmartShell используем отдельный экран бронирований:

- ресурсы/ПК по вертикали;
- время по горизонтали;
- выбор даты и видимого периода;
- сортировка/фильтр групп;
- визуальные блоки броней с различимыми статусами;
- явная кнопка создания брони;
- открытие подробностей и действий в правой панели;
- ночные и пересекающие полночь брони показываются без потери связи с датой.

Это визуальный ориентир, а не копирование SmartShell. В MVP можно начать с окна 24–36 часов, если это упростит работу оператора.

## Контракты

Спроектировать versioned protobuf/API для `CheckAvailability`, `CreateReservation`, `ListReservations`, `GetReservation`, `UpdateReservation`, `CancelReservation`, `CompleteReservation` и `MarkNoShow`. Ответы должны содержать conflict reason, resource status, reservation status и безопасный audit context.

## Задачи

1. [x] Зафиксировать lifecycle и state machine брони.
2. [x] Определить timezone, границы периодов и configurable grace/no-show policy; strict mode остаётся.
3. [x] Описать ownership и межмодульные порты.
4. [x] Спроектировать protobuf-команды и ошибки конфликтов.
5. [x] Реализовать Domain conflict rules через `typing.Protocol` ports.
6. [x] Реализовать PostgreSQL schema, indexes и migrations с advisory-lock strategy.
7. [x] Реализовать atomic multi-resource create и idempotency на PostgreSQL; PostgreSQL locking/concurrency test добавлен, отдельные contract tests остаются.
8. [x] Реализовать operator API и permissions.
9. [x] Подготовить frontend timeline/map integration prototype.
10. [x] Подготовить WinUI отображение ближайшей реальной брони текущего места;
    фиктивный `VIP-01` удалён, при отсутствии совпадения карточка скрывается.
11. [x] Добавить unit/API/DB smoke tests и memory/PostgreSQL concurrency tests; отдельные contract tests остаются.
12. [x] Добавить async Dramatiq sweep и Redis scheduler boundary для no-show.
13. [x] Закрепить анонимную гостевую бронь: `client_id` и `guest_id` могут быть
    пустыми, а display snapshot нормализуется к `Гость`; зарегистрированный
    участник сохраняет ссылку на клиента, а UI разрешает редактирование периода
    без подмены идентичности.

Текущий срез поддерживает атомарное создание, список, idempotency, получение,
редактирование подтверждённой брони, отмену и базовые lifecycle-переходы
`activate`, `complete`, `no-show` через HTTP/gRPC контракты.
Конкурентная защита проверена на memory-adapter и реализована через advisory locks
в PostgreSQL; backend no-show защищён настраиваемым grace period.
В web timeline доступны выбор даты, создание, фильтр зон, редактирование
подтверждённой брони и отмена с подтверждением. Foundation для worker уже добавлен:
async Dramatiq actor запускает PostgreSQL sweep, scheduler периодически ставит эту
задачу в Redis, а атомарный repository-переход повторно проверяет статус под row
lock. Realtime остаётся следующим этапом.

## Критерии готовности

- конфликтующие брони не создаются даже при конкурентных запросах;
- мульти-PC бронь атомарна;
- повторная команда не создаёт дубль;
- disabled/offline и занятые места дают объяснимую ошибку;
- изменение/отмена сохраняет историю;
- оператор видит бронь на временной шкале и в контексте ПК;
- права создания, изменения и отмены проверяются в use case;
- tariff/quote не меняется незаметно после создания брони.

## Риски

- race condition при одновременном бронировании одного ПК;
- неявный timezone приведёт к неверному времени начала;
- изменение тарифа без snapshot/reference сломает финансовую историю;
- слишком сложный realtime ухудшит MVP без доказанной необходимости.

## Проверки

- state-machine and conflict unit tests;
- PostgreSQL concurrency/transaction tests;
- gRPC contract tests;
- duplicate/multi-resource/timeout tests;
- timezone and midnight boundary tests;
- permission/audit tests;
- UI timeline smoke test.

## Открытые вопросы

- бронь создаётся на конкретный ПК или сначала на группу/тип места;
- допускается ли бронь нескольких зон;
- нужна ли предоплата или только резерв;
- сколько минут grace period и когда наступает no-show;
- доступно ли online-бронирование в MVP;
- кто и как освобождает место после неявки.
