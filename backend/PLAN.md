# Backend — общий план

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `backend/`

## Цель

Создать backend как модульный асинхронный монолит с чёткими bounded contexts, protobuf/gRPC-контрактами и возможностью последующего выделения отдельных модулей в микросервисы.

## Входит в план

- общий backend-каркас и правила зависимостей;
- порядок реализации модулей;
- ownership данных и межмодульные контракты;
- общие требования к async I/O, PostgreSQL, Redis, Dramatiq, gRPC и безопасности;
- сквозные проверки и MVP-интеграция.

## Не входит

- реализация всех модулей в одном изменении;
- frontend и WinUI implementation;
- production deployment до отдельного deployment-плана;
- автоматическое выделение модулей в микросервисы без подтверждённой причины.

## Порядок реализации

1. `../plans/00-foundation` — каркас, инструменты, инфраструктура и общие контракты.
2. `../plans/04-auth-security` — базовая identity/auth policy параллельно с foundation.
3. `../plans/01-workstations` — ПК, группы, heartbeat и команды.
4. `../plans/02-clients-guests` — клиенты, поиск, ledger баланса.
5. `../plans/03-catalog-time-tariffs` — товары, время и расчёт тарифов.
6. `../plans/05-reservations` — доступность и бронирование мест.
7. `../plans/06-sessions` — фактические игровые сессии и lifecycle.
8. `../plans/07-billing` — списание за завершённую сессию и financial snapshot.
9. `../plans/08-reports-dashboard` — read-only показатели и отчётная выручка.
10. `../plans/09-cash-shifts` — кассовые смены и наличный ledger.
11. `../plans/10-product-sales` — продажи товаров, snapshots и settlement.
12. `../plans/11-analytics` — клиентская и клубная read-only аналитика.
13. `../plans/13-payment-methods` — настройки способов оплаты клуба.
14. `../plans/29-contract-alignment` — сквозное выравнивание обязательных
    backend/frontend/WinUI контрактов и закрытие подтверждённых разрывов.
    Декомпозиция реализации: планы [`30`](../plans/30-entitlements-meter/PLAN.md),
    [`31`](../plans/31-settlement-reconciliation/PLAN.md),
    [`32`](../plans/32-session-snapshot-entry/PLAN.md),
    [`33`](../plans/33-session-transfer/PLAN.md),
    [`34`](../plans/34-durable-offline/PLAN.md) и
    [`37`](../plans/37-platform-integration-evidence/PLAN.md).

Frontend и Windows-клиент начинают интеграцию после фиксации нужных контрактов,
но их UI-каркас может разрабатываться параллельно. Сквозные обязательные
разрывы зафиксированы в
[`../plans/29-contract-alignment/PLAN.md`](../plans/29-contract-alignment/PLAN.md);
наличие текущих модулей не означает выполнение продуктового контракта.

## Границы модулей

| Модуль | Владеет | Не владеет |
| --- | --- | --- |
| Workstations | ПК, device identity, техническое состояние, группы, theme settings и команды | клиентами, ценами и балансами |
| Clients | профилем, поиском, discount category и balance ledger | техническим состоянием ПК и тарифной сеткой |
| Catalog | товарами, временем, тарифами и правилами цены | фактическим началом сессии и профилем клиента |
| Reservations | жизненным циклом брони и проверкой конфликтов | identity ПК, профилем клиента и оплатой |
| Sessions | фактическими игровыми сессиями и их lifecycle | тарифами, балансом и техническим управлением ПК |
| Billing | charge за завершённую сессию, quote snapshot, reconciliation и связь с ledger operation | lifecycle сессии, текущим балансом клиента и внешними платежами |
| Auth/Security | identity, token policy, permissions и security audit | бизнесовыми данными модулей |
| Reports/Dashboard | read-only показатели из публичных application boundaries | изменение бизнес-данных, кассовый журнал и сырые таблицы модулей |
| Cash Shifts | lifecycle кассовой смены и наличный ledger | клиентский balance, session charge и read-only reports |
| Product Sales | факт продажи товара, stock reservation, price snapshots и settlement reference | карточку товара, клиентский ledger и lifecycle кассы |
| Analytics | read-only агрегации сохранённых сессий, charges и продаж | изменение бизнес-данных и текущие денежные балансы |
| Payment Methods | настройки доступных способов оплаты и их отображаемые названия | проведение платежа, клиентский balance и cash ledger |

## Архитектурные ограничения

- Domain не импортирует FastAPI, gRPC, PostgreSQL, Redis и Dramatiq.
- Application работает через порты на `typing.Protocol`.
- SQL и ORM-модели не выходят за Repository/Infrastructure.
- Межмодульное взаимодействие идёт через публичные application ports, команды, DTO и события.
- Денежные операции транзакционны и идемпотентны.
- Изменяющие gRPC-команды имеют deadline, cancellation и безопасную обработку повторов.
- Redis является техническим хранилищем/брокером, но не источником истины для денег и настроек.
- JWT проверяется на входе и permissions повторно проверяются в use case.
- Конфигурация темы группы хранится у Workstations; Windows получает её через heartbeat и не принимает произвольные theme keys.

## Сквозные артефакты

- versioned protobuf package;
- error/status convention;
- миграции PostgreSQL;
- structured logging и correlation ID;
- конфигурация environment/secrets;
- health/readiness checks;
- unit, integration и contract tests;
- README и команды воспроизводимого запуска.

## Задачи

1. Выполнить foundation и зафиксировать технический стек.
2. Зафиксировать ownership и публичные контракты всех backend-модулей.
3. Реализовать auth policy до подключения защищённых изменяющих операций.
4. Реализовать Workstations, Clients, Catalog, Reservations, Sessions и Billing отдельными вертикальными срезами.
5. После каждого среза обновлять protobuf, миграции, тесты и статус плана.
6. Собрать общий MVP smoke test через gateway, backend и Windows mock/client.

Текущий прикладной срез расширил MVP operator management: зоны и ПК редактируются
через Workstations, карта получает устойчивую spatial-модель, Catalog поддерживает
категории товаров/напитков, Sessions принимает выбранный тариф, Reservations и
Sessions поддерживают анонимного `Гостя`, а Cash Shifts — расписание автооткрытия
и автозакрытия. Web refresh-сессия рассчитана на 90 дней. Native Windows kiosk и
Assigned Access по-прежнему требуют проверки на Windows и не считаются закрытыми
этим backend/frontend срезом.

Контрактный аудит выявил отдельный P0-срез: durable entitlement queue и login
grant, guest paid-start, payment parts, reservation entry decision, one-active-
client invariant, transfer, session snapshot и offline batch protocol. В текущем
срезе backend имеет migrations `20260902_0034`–`0046`, payment parts,
guest-payment prerequisite, `CheckEntry`, package consumption с time windows и
auto-next, snapshot, transfer owner transaction, offline replay и
one-active-client guard. Account-portal login не выдаёт игровой grant без
device session start. Общий cross-owner settlement UoW,
PostgreSQL concurrency и transport/native evidence остаются открытыми. Эти
возможности не следует добавлять локальными обходами в BFF или WinUI; порядок
реализации и transport boundaries описаны в планах 29–37.
Дополнительно Clients получил защищённые operator-команды редактирования,
мягкой деактивации и выдачи временного пароля с сохранением только хеша; Catalog
получил CRUD товара, закупочную цену и остаток. Эти поля добавлены в HTTP BFF и
обратно совместимый versioned protobuf Product contract; миграционная цепочка
закончена на `20260828_0024`.

Следующий прикладной срез — продажи товаров и расширенная аналитика. Продажа
сохраняет цену/себестоимость на момент операции, а аналитика считает часы,
сессионные и товарные траты отдельно и вместе только из завершённых фактов.
Продажа и аналитика реализованы в первом вертикальном срезе; в следующем этапе
нужно подключить статистику к основной карточке клиента, добавить versioned
gRPC read contract и экспорт. Текущий Analytics-срез уже включает динамику по
дням/часам, загрузку, зоны, ПК, тарифы, оплату, маржинальность и сегменты
клиентов; retention/cohorts и тяжёлые фоновые отчёты остаются отдельным этапом.

## Критерии готовности

- каждый модуль имеет владельца данных и публичный контракт;
- модуль можно тестировать без реальной инфраструктуры на Domain/Application уровне;
- основные финансовые, reservation и workstation-команды защищены от duplicate delivery;
- нет прямых cross-module database queries;
- backend skeleton и проверки запускаются согласно foundation-плану;
- фактически реализованное состояние отражено в соответствующем плане.

## Проверки

- запуск всех backend checks из foundation;
- contract compatibility для protobuf;
- integration tests PostgreSQL/Redis;
- проверка направленности импортов и отсутствия циклических зависимостей;
- security review изменяющих RPC;
- сквозной MVP smoke test после готовности зависимых модулей.

## Риски

- browser transport потребует gateway/BFF или grpc-web-совместимый слой;
- отдельный deployment каждого модуля не нужен до появления подтверждённой нагрузки или требований изоляции;
- Cash Shifts уже выделен в отдельный срез после внутреннего session charge;
  producer-интеграция с Billing/внешними платежами остаётся отдельным backlog;
  reconciliation входит в текущий billing-срез.

## Открытые вопросы

- окончательный выбор async ORM/driver и способа генерации protobuf ещё не закреплён;
- требуется ли отдельный gateway deployment или достаточно BFF в первом релизе;
- какие критерии нагрузки будут основанием для выделения модуля.
