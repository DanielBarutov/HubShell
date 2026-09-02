# Планы проекта

Это общий индекс архитектурных и implementation-планов игрового клуба. Планы описывают согласованный объём работы, а не факт реализации. Реализация считается готовой только после выполнения задач, проверок и критериев готовности.

Фактические результаты проверок и непроверенные платформенные ограничения
сведены в [`VERIFICATION.md`](VERIFICATION.md).

Корневой [`docker-compose.yml`](../docker-compose.yml) является воспроизводимым
dev-стеком для всех доступных серверных частей и frontend; отдельный
`backend/docker-compose.yml` сохраняет infra-only сценарий.

Текущий прикладной срез включает управление зонами и ПК, устойчивую spatial
карту, анонимного гостя, canonical phone, тарифы, каталог с остатками и
закупочными ценами, кассовые смены, продажи товаров, расширенную read-only
аналитику, live metered billing и CRUD способов оплаты. Операторский redesign
использует тёмный shell, topbar, контрастные состояния, dashboard, карту,
каталог, бронирования и sliding panels. Сквозной аудит контрактов и реализации
зафиксирован в плане 29. В текущем срезе реализованы backend payment/guest/entry/
session-invariant основы, durable entitlement queue, portal queue activation и
source-level WinUI widget; package consumption с окнами/auto-next, snapshot,
transfer, offline replay, settlement review и основные frontend/WinUI consumers
добавлены, но integration/native evidence ещё не закрыты.

Не закрыты доказательства и отдельные production-границы: общий PostgreSQL
UoW для финансового settlement, реальные lock/replay concurrency tests,
heartbeat/read-model fixtures, headed browser matrix, native Windows
build/runtime, настоящий kiosk deployment, hardening per-device enrollment,
внешние payment providers, тяжёлые фоновые отчёты и полноценный realtime
transport. Фактическая Windows-проверка остаётся отдельным чекапом на целевой
машине.

## Порядок работы и единое расположение планов

Все детальные implementation-планы хранятся в этой папке. Backend, frontend и
Windows сохраняют свои короткие owner-level входы в `backend/PLAN.md`,
`frontend/PLAN.md` и `win-client/PLAN.md`, но детальные планы и связанные
контракты не дублируются по компонентам.

| Порядок | Папка | Назначение | Статус |
| --- | --- | --- | --- |
| B | [`backend/PLAN.md`](../backend/PLAN.md) | обзор backend и порядок реализации | `in_progress` |
| 00 | [`00-foundation/PLAN.md`](00-foundation/PLAN.md) | каркас репозитория, инструменты, инфраструктура и общие контракты | `in_progress` |
| 01 | [`01-workstations/PLAN.md`](01-workstations/PLAN.md) | регистрация, состояние и команды игровых ПК | `in_progress` |
| 02 | [`02-clients-guests/PLAN.md`](02-clients-guests/PLAN.md) | клиенты, гости, поиск, баланс и бонусы | `in_progress` |
| 03 | [`03-catalog-time-tariffs/PLAN.md`](03-catalog-time-tariffs/PLAN.md) | товары, игровое время, тарифы и правила цены | `in_progress` |
| 04 | [`04-auth-security/PLAN.md`](04-auth-security/PLAN.md) | JWT, роли, permissions, безопасность и аудит | `in_progress` |
| 05 | [`05-reservations/PLAN.md`](05-reservations/PLAN.md) | бронирование мест и времени | `in_progress` |
| 06 | [`06-sessions/PLAN.md`](06-sessions/PLAN.md) | фактические игровые сессии и lifecycle | `in_progress` |
| 07 | [`07-billing/PLAN.md`](07-billing/PLAN.md) | списание за завершённую сессию и финансовый snapshot | `in_progress` |
| 08 | [`08-reports-dashboard/PLAN.md`](08-reports-dashboard/PLAN.md) | read-only отчёты и live-показатели dashboard | `in_progress` |
| 09 | [`09-cash-shifts/PLAN.md`](09-cash-shifts/PLAN.md) | кассовые смены и наличный ledger | `in_progress` |
| 10 | [`10-product-sales/PLAN.md`](10-product-sales/PLAN.md) | продажи товаров, остатки и settlement | `done` |
| 11 | [`11-analytics/PLAN.md`](11-analytics/PLAN.md) | клиентская и клубная аналитика | `in_progress` |
| 12 | [`12-live-metered-billing/PLAN.md`](12-live-metered-billing/PLAN.md) | поминутное списание, последовательные тарифы и операции с карты ПК | `in_progress` |
| 13 | [`13-payment-methods/PLAN.md`](13-payment-methods/PLAN.md) | настраиваемые способы оплаты в настройках клуба | `done` |
| 14 | [`../frontend/PLAN.md`](../frontend/PLAN.md) | owner-level план операторской веб-оболочки и dashboard | `in_progress` |
| 15 | [`../win-client/PLAN.md`](../win-client/PLAN.md) | owner-level план Windows-клиента, тем и связи с backend | `in_progress` |
| 22 | [`22-windows-lockdown/PLAN.md`](22-windows-lockdown/PLAN.md) | Windows app gate, kiosk policy и provisioning | `in_progress` |
| 23 | [`23-windows-enrollment-member-portal/PLAN.md`](23-windows-enrollment-member-portal/PLAN.md) | автоматическое подключение по MAC, access-gate и личный кабинет | `in_progress` |
| 23a | [`23-device-enrollment/PLAN.md`](23-device-enrollment/PLAN.md) | MAC enrollment и device identity | `in_progress` |
| 24 | [`24-windows-shell/PLAN.md`](24-windows-shell/PLAN.md) | pre-auth gate и post-auth desktop/widget flow | `in_progress` |
| 25 | [`25-client-portal/PLAN.md`](25-client-portal/PLAN.md) | регистрация, вход и личный кабинет пользователя | `in_progress` |
| 26 | [`26-frontend-device-assignment/PLAN.md`](26-frontend-device-assignment/PLAN.md) | назначение MAC и статусы устройства в админке | `in_progress` |
| 27 | [`27-portable-deployment/PLAN.md`](27-portable-deployment/PLAN.md) | один portable EXE без console setup | `in_progress` |
| 28 | [`28-integration-checks/PLAN.md`](28-integration-checks/PLAN.md) | сквозные backend/frontend/Windows чекапы | `in_progress` |
| 29 | [`29-contract-alignment/PLAN.md`](29-contract-alignment/PLAN.md) | аудит и реализация разрывов трёх продуктовых контрактов | `in_progress` |
| 30 | [`30-entitlements-meter/PLAN.md`](30-entitlements-meter/PLAN.md) | entitlement lifecycle, consumption, auto-next и login grant | `in_progress` |
| 31 | [`31-settlement-reconciliation/PLAN.md`](31-settlement-reconciliation/PLAN.md) | единый settlement и recovery финансовых операций | `in_progress` |
| 32 | [`32-session-snapshot-entry/PLAN.md`](32-session-snapshot-entry/PLAN.md) | session snapshot, heartbeat и entry decision transport | `in_progress` |
| 33 | [`33-session-transfer/PLAN.md`](33-session-transfer/PLAN.md) | атомарный перенос сессии между ПК | `in_progress` |
| 34 | [`34-durable-offline/PLAN.md`](34-durable-offline/PLAN.md) | durable offline journal и batch replay | `in_progress` |
| 35 | [`35-frontend-contract-consumers/PLAN.md`](35-frontend-contract-consumers/PLAN.md) | operator consumers новых backend DTO | `in_progress` |
| 36 | [`36-winui-contract-consumers/PLAN.md`](36-winui-contract-consumers/PLAN.md) | WinUI snapshot, transfer и offline consumers | `in_progress` |
| 37 | [`37-platform-integration-evidence/PLAN.md`](37-platform-integration-evidence/PLAN.md) | integration, native, kiosk и release evidence | `in_progress` |

Статусы:

- `planned` — план подготовлен, работа не начата;
- `in_progress` — текущая рабочая область;
- `blocked` — есть внешняя или неразрешённая зависимость;
- `done` — задачи и критерии готовности выполнены и проверены.

## Зависимости

```text
backend/PLAN.md
├── plans/00-foundation
├── plans/04-auth-security
├── plans/01-workstations
├── plans/02-clients-guests
├── plans/03-catalog-time-tariffs
├── plans/05-reservations
├── plans/06-sessions
├── plans/07-billing
├── plans/08-reports-dashboard
├── plans/09-cash-shifts
├── plans/10-product-sales
├── plans/11-analytics
├── plans/12-live-metered-billing
├── plans/13-payment-methods
├── plans/22-windows-lockdown
├── plans/23-windows-enrollment-member-portal
├── plans/23-device-enrollment
├── plans/24-windows-shell
├── plans/25-client-portal
├── plans/26-frontend-device-assignment
├── plans/27-portable-deployment
├── plans/28-integration-checks
├── plans/29-contract-alignment
│   ├── plans/30-entitlements-meter
│   ├── plans/31-settlement-reconciliation
│   ├── plans/32-session-snapshot-entry
│   ├── plans/33-session-transfer
│   ├── plans/34-durable-offline
│   ├── plans/35-frontend-contract-consumers
│   ├── plans/36-winui-contract-consumers
│   └── plans/37-platform-integration-evidence
├── frontend/PLAN.md
└── win-client/PLAN.md
```

Auth является платформенной зависимостью для защищённых сценариев, но его базовые контракты можно проектировать параллельно с бизнес-модулями. Frontend и Windows-клиент не должны начинать интеграцию до фиксации необходимых protobuf/API-контрактов. Бронирование зависит от идентичности ПК, клиентов и правил тарифов. `plans/` является единственным canonical location для детальных планов.

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

Новые решения, которые влияют на несколько областей, сначала добавляются сюда или в соответствующий план, затем отражаются в `CODEX.md`, если становятся постоянным правилом проекта.

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
