# Backend — Billing / Session Charges

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `plans/07-billing/`
Зависимости: Clients, Catalog, Sessions, Auth/Security

## Цель

Добавить первый финансовый вертикальный срез: после завершённой именованной
игровой сессии рассчитать стоимость по тарифу и категории скидки, атомарно
списать spendable balance клиента и сохранить неизменяемый снимок расчёта.

## Границы первого среза

Входит:

- `debit` в клиентском ledger с отрицательной операцией и типом `debit`;
- защита от отрицательного баланса, duplicate delivery и гонок PostgreSQL;
- расчёт billable duration целыми минутами с округлением вверх;
- `SessionCharge` с tariff/discount/amount snapshot;
- HTTP BFF и защищённый gRPC-контракт `ChargeSession`/`GetSessionCharge`;
- повторяемый recovery path: durable reconciliation record создаётся до debit,
  ledger idempotency key выводится из session ID, а retry выполняется worker;
- unit, API, contract, PostgreSQL concurrency и gRPC smoke проверки.

Не входит:

- внешние эквайеры, онлайн-платежи, касса и возвраты;
- списание `balance_bonus` — бонусы остаются отдельным будущим правилом;
- автоматическое списание гостя без клиентского профиля;
- резервирование денег до начала сессии;
- изменение Session-модуля или запись тарифа в саму сессию;
- распределение billing в отдельный deployment до появления причины.

## Решения и инварианты

- Billing владеет фактом charge и его ценовым snapshot; Clients владеет ledger и
  текущим балансом; Catalog владеет quote; Sessions владеет lifecycle сессии.
- Списывается только `balance_cents`; `balance_bonus` не изменяется в первом
  срезе и явно возвращается в ответе для UI.
- Charge допустим только для `completed` session с `client_id` и положительной
  длительностью. Гостевой сценарий проходит через будущий кассовый flow.
- Цена фиксируется в `SessionCharge` и не пересчитывается из сохранённого charge.
- На одну сессию допускается один charge. Повтор по тому же или другому ключу
  не создаёт второе списание; конфликт ключа для другой сессии возвращается явно.
- Если процесс завершился после debit и до сохранения charge, reconciliation
  record сохраняет retryable-состояние, а worker повторяет операцию с тем же
  ledger key. При изменившемся quote операция не маскируется: запись получает
  `needs_review` для операторской диагностики.
- Все суммы — integer cents; `float` не используется.

## Задачи

1. [x] Расширить Clients ledger типом операции и атомарным debit.
2. [x] Добавить домен и memory/PostgreSQL repository для `SessionCharge`.
3. [x] Добавить миграцию `20260827_0012` и индексы уникальности session/key.
4. [x] Добавить HTTP BFF и protobuf/gRPC-контракты с permission `billing.manage`.
5. [x] Подключить Billing в HTTP/gRPC composition root.
6. [x] Проверить повторные запросы, нехватку средств и конкурентные списания.
7. [x] Добавить durable reconciliation/outbox для надёжной обработки разрыва
   debit → charge, retry worker и операторскую диагностику.
8. [x] Спроектировать бонусное списание, возвраты, кассу и внешние платежи;
   дизайн зафиксирован в [`FUTURE-FINANCE.md`](FUTURE-FINANCE.md), реализация
   остаётся отдельными будущими вертикальными срезами.

## Артефакты

- `src/gameclub_backend/modules/billing/`;
- `proto/gameclub/v1/billing.proto` и сгенерированные Python/C# consumers;
- `alembic/versions/20260827_0012_billing.py`;
- `alembic/versions/20260827_0013_billing_reconciliation.py`;
- HTTP routes `/api/v1/billing/sessions/{session_id}/charge`;
- HTTP route `/api/v1/billing/reconciliation`;
- Dramatiq actor `gameclub_backend.jobs.billing:reconcile_billing_charges`;
- обновлённый Clients ledger и тесты.

## Критерии готовности первого среза

- незавершённая или гостевая сессия не списывает деньги;
- недостаточный баланс не уходит в отрицательное значение;
- повтор и параллельная доставка создают один debit и один charge;
- в charge видны тариф, длительность, скидка и итоговая сумма на момент расчёта;
- HTTP/gRPC защищены JWT permission и используют versioned contract;
- миграция применяется на чистую и текущую PostgreSQL базу;
- разрыв между debit и сохранением charge оставляет retryable record и
  восстанавливается повторным запуском worker;
- unit и integration checks проходят, а клиентский WinUI build помечен отдельно,
  если платформа Linux не позволяет его выполнить.

## Отложенный backlog

- reservation prepayment/deposit hold;
- дневные/ночные и поминутные правила тарификации;
- расход бонусов с приоритетом источников;
- корректирующие операции, возвраты и закрытие смены;
- отчёты и расширенный audit trail.
- реализация bonus wallet, cashier, refunds и external payment provider.
