# План 06 — Sessions / Игровые сессии

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: `00-foundation`, `01-workstations`, `02-clients-guests`, `05-reservations`

## Цель

Зафиксировать фактическое использование игрового ПК отдельной сущностью с
идемпотентным lifecycle. Сессия не заменяет бронь: бронь планирует время, а
сессия отражает реально начавшуюся игру.

## Первый срез

- `active` и `completed` lifecycle;
- один активный сеанс на один ПК;
- клиент или гость как владелец сеанса;
- ссылка на бронь и источник запуска;
- operator HTTP BFF и versioned gRPC;
- memory/PostgreSQL repositories и конкурентная защита;
- списание вынесено в отдельный Billing use case после завершения сессии;
  Sessions не меняет баланс напрямую.

## Архитектурные правила

- Sessions владеет только фактом сессии и её lifecycle.
- Workstations владеет техническим ресурсом и его disabled-состоянием.
- Clients владеет профилем клиента и балансом.
- Reservations остаётся планом времени; активация брони и старт сессии
  связываются явно, без cross-module SQL.
- Тариф/quote и списание выполняются Billing use case с snapshot и ledger;
  Sessions предоставляет только lifecycle и публичный lookup-порт.

## Задачи

1. [x] Зафиксировать domain state machine и ownership.
2. [x] Добавить versioned protobuf для start/get/list/stop.
3. [x] Реализовать application ports и memory repository.
4. [x] Реализовать PostgreSQL schema, indexes и advisory-lock strategy.
5. [x] Подключить HTTP BFF и gRPC handlers с operator permissions.
6. [x] Добавить unit/API/contract/concurrency tests.
7. [x] Спроектировать и реализовать billing quote/snapshot и списание через
   client ledger в отдельном Billing-модуле.
8. [x] Связать device-команды `session.start/stop` с Session use case через
   device-authenticated gRPC gateway и структурированный payload; локальный
   запуск игровых процессов остаётся вне среза.
9. [x] Передать выбранный опубликованный `tariff_id` через HTTP/gRPC start и
   сохранять его в сессии; Billing использует этот тариф для фиксированного
   quote, а при отсутствии выбора сохраняется legacy duration quote.
10. [x] Добавить отдельную operator-only HTTP-операцию `interrupt` для
    досрочного завершения уже активной сессии; повторный вызов остаётся
    безопасным no-op, а списание выполняется отдельным Billing flow.

## Критерии готовности первого среза

- второй конкурентный start на тот же ПК получает объяснимый conflict;
- disabled или неизвестный ПК не запускает сессию;
- клиент/гость валидируются одинаково в HTTP и gRPC;
- ссылка на бронь проверяется по существованию, ПК и допустимому reservation status;
- повторный stop не меняет завершённую сессию;
- активные сессии видны оператору и не смешиваются с reservation status;
- деньги не меняются при start/stop; отдельный Billing use case списывает
  средства только после завершения именованной сессии.

## Открытые вопросы

- запускает ли сессию оператор, device-команда или оба сценария;
- является ли старт по броне отдельной атомарной операцией;
- как считать поминутный/блочный тариф и когда резервировать баланс;
- нужна ли пауза сессии и как учитывать downtime ПК.
