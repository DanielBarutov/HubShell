# Планы проекта

Это общий индекс архитектурных и implementation-планов игрового клуба. Планы описывают согласованный объём работы, а не факт реализации. Реализация считается готовой только после выполнения задач, проверок и критериев готовности.

Фактические результаты проверок и непроверенные платформенные ограничения
сведены в [`VERIFICATION.md`](VERIFICATION.md).

Корневой [`docker-compose.yml`](../docker-compose.yml) является воспроизводимым
dev-стеком для всех доступных серверных частей и frontend; отдельный
`backend/docker-compose.yml` сохраняет infra-only сценарий.

Последний прикладной срез: управление зонами и ПК, компактная пространственная
карта с режимом редактирования и контекстными действиями, анонимный гость,
canonical phone, карточки выбора тарифа, категории каталога, CRUD клиентов и
товаров с остатками/закупочными ценами, расписание кассовых смен и 90-дневная
web-сессия. Native Windows build и настоящий kiosk deployment остаются
платформенными задачами Windows. Для этого среза уже добавлены декларативная
lockdown policy группы, heartbeat-передача в Win-клиент и обратимый preview/apply
bootstrap для Shell Launcher; фактическая Windows-проверка остаётся отдельной
платформенной задачей.
Общий operator redesign закреплён отдельным frontend-срезом: тёмный shell с
постоянной навигацией, рабочим topbar, контрастными состояниями и едиными
поверхностями для dashboard, карты, каталога, бронирований и sliding panels.
Следующий прикладной срез закрывает продажу товаров клиенту или гостю с оплатой
из баланса/кассы и идемпотентным списанием, а также read-only аналитику клуба и
клиентов по завершённым сессиям, charges и продажам. Аналитика расширена до
динамики по дням/часам, загрузки клуба, зон/ПК/тарифов/оплат, маржинальности и
сегментов клиентов, versioned gRPC read contract и CSV-выгрузки из web-панели.

## Порядок работы

| Порядок | Папка | Назначение | Статус |
| --- | --- | --- | --- |
| 00 | [`backend/PLAN.md`](../backend/PLAN.md) | план backend и порядок реализации | `in_progress` |
| 01 | [`backend/plans/00-foundation/PLAN.md`](../backend/plans/00-foundation/PLAN.md) | каркас репозитория, инструменты, инфраструктура и общие контракты | `in_progress` |
| 02 | [`backend/plans/01-workstations/PLAN.md`](../backend/plans/01-workstations/PLAN.md) | регистрация, состояние и команды игровых ПК | `in_progress` |
| 03 | [`backend/plans/02-clients-guests/PLAN.md`](../backend/plans/02-clients-guests/PLAN.md) | клиенты, гости, поиск, баланс и бонусы | `in_progress` |
| 04 | [`backend/plans/03-catalog-time-tariffs/PLAN.md`](../backend/plans/03-catalog-time-tariffs/PLAN.md) | товары, игровое время, тарифы и правила цены | `in_progress` |
| 05 | [`backend/plans/04-auth-security/PLAN.md`](../backend/plans/04-auth-security/PLAN.md) | JWT, роли, permissions, безопасность и аудит | `in_progress` |
| 06 | [`backend/plans/05-reservations/PLAN.md`](../backend/plans/05-reservations/PLAN.md) | бронирование мест и времени | `in_progress` |
| 07 | [`backend/plans/06-sessions/PLAN.md`](../backend/plans/06-sessions/PLAN.md) | фактические игровые сессии и lifecycle | `in_progress` |
| 08 | [`backend/plans/07-billing/PLAN.md`](../backend/plans/07-billing/PLAN.md) | списание за завершённую сессию и финансовый snapshot | `in_progress` |
| 09 | [`backend/plans/08-reports-dashboard/PLAN.md`](../backend/plans/08-reports-dashboard/PLAN.md) | read-only отчёты и live-показатели dashboard | `in_progress` |
| 10 | [`backend/plans/09-cash-shifts/PLAN.md`](../backend/plans/09-cash-shifts/PLAN.md) | кассовые смены и наличный ledger | `in_progress` |
| 11 | [`backend/plans/10-product-sales/PLAN.md`](../backend/plans/10-product-sales/PLAN.md) | продажи товаров, остатки и settlement | `in_progress` |
| 12 | [`backend/plans/11-analytics/PLAN.md`](../backend/plans/11-analytics/PLAN.md) | клиентская и клубная аналитика | `in_progress` |
| 13 | [`frontend/PLAN.md`](../frontend/PLAN.md) | операторская веб-оболочка и dashboard | `in_progress` |
| 14 | [`win-client/PLAN.md`](../win-client/PLAN.md) | Windows-виджет, темы и связь с backend | `in_progress` |
| 15 | [`backend/plans/12-live-metered-billing/PLAN.md`](../backend/plans/12-live-metered-billing/PLAN.md) | поминутное списание, последовательные тарифы и операции с карты ПК | `in_progress` |
| 16 | [`backend/plans/13-payment-methods/PLAN.md`](../backend/plans/13-payment-methods/PLAN.md) | настраиваемые способы оплаты в настройках клуба | `done` |

Статусы:

- `planned` — план подготовлен, работа не начата;
- `in_progress` — текущая рабочая область;
- `blocked` — есть внешняя или неразрешённая зависимость;
- `done` — задачи и критерии готовности выполнены и проверены.

## Зависимости

```text
backend/PLAN.md
├── backend/plans/00-foundation
├── backend/plans/04-auth-security
├── backend/plans/01-workstations
├── backend/plans/02-clients-guests
├── backend/plans/03-catalog-time-tariffs
├── backend/plans/05-reservations
├── backend/plans/06-sessions
├── backend/plans/07-billing
├── backend/plans/08-reports-dashboard
├── backend/plans/09-cash-shifts
├── backend/plans/10-product-sales
├── backend/plans/11-analytics
├── backend/plans/13-payment-methods
├── frontend/PLAN.md
└── win-client/PLAN.md
```

Auth является платформенной зависимостью для защищённых сценариев, но его базовые контракты можно проектировать параллельно с бизнес-модулями. Frontend и Windows-клиент не должны начинать интеграцию до фиксации необходимых protobuf/API-контрактов. Бронирование зависит от идентичности ПК, клиентов и правил тарифов.

## Общие правила планов

Каждый `PLAN.md` содержит:

- цель и границы;
- что входит и не входит в работу;
- архитектурные решения и нерешённые вопросы;
- задачи с порядком выполнения;
- ожидаемые артефакты;
- критерии готовности;
- проверки;
- риски и зависимости.

Новые решения, которые влияют на несколько областей, сначала добавляются сюда или в соответствующий план, затем отражаются в `AGENTS.md`, если становятся постоянным правилом проекта.

## Общий MVP-контур

Первый сквозной вертикальный срез должен позволять:

1. авторизованному оператору открыть web dashboard;
2. увидеть зарегистрированные ПК и их актуальное состояние;
3. найти клиента по нику или телефону;
4. выполнить защищённое пополнение баланса с идемпотентностью;
5. создать бронь клиента или гостя на свободное место;
6. завершить именованную игровую сессию и выполнить защищённое списание по quote;
7. передать Windows-клиенту безопасную команду и получить подтверждение;
   8. продать товар клиенту или гостю и увидеть результат операции;
   9. увидеть результат операций и клиентскую статистику в web-интерфейсе.

До этого среза не нужно реализовывать весь список будущих сервисов, внешние
платёжные интеграции и автоматическое выделение модулей в отдельные deployment
units. Cash Shifts уже выполнен как отдельный финансовый срез после внутреннего
session charge. Provider-neutral producer boundary и supervisor approvals
реализованы; конкретные webhook/эквайринг-адаптеры остаются отдельным этапом.

## Отложенный backlog

После внутреннего session charge отдельно планируются реализация бонусного
списания, корзина заказов, конкретная producer-интеграция Cash Shifts с Billing/платежами,
сотрудники и роли, уведомления, расширенные отчёты и аудит,
обновления клиента, Windows Assigned Access/Shell Launcher deployment и
выделение модулей в микросервисы.
