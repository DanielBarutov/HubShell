# Будущий финансовый срез

Документ фиксирует дизайн следующего этапа Billing. Он не означает, что внешние
платежи или бонусное списание уже доступны в текущем MVP.

## Кошельки и порядок списания

У клиента остаются два независимых денежных источника:

1. `balance_cents` — реальные средства;
2. `balance_bonus` — бонусные единицы, полученные по правилам пополнения или
   промо-операции.

Для каждого charge Catalog/Billing сохраняет policy snapshot:

- `cash_only` — текущий MVP и операции, где бонусы запрещены;
- `bonus_then_cash` — сначала бонусы, остаток из реального баланса;
- `cash_then_bonus` — специальная акция, включается только отдельным правилом.

Порядок нельзя выводить из текущей конфигурации задним числом: выбранная policy,
использованные источники и суммы фиксируются в charge snapshot. Ledger получает
отдельные компенсирующие операции по каждому источнику, а не одну неразличимую
сумму.

## Ledger operations

`BalanceOperationType` расширяется типами:

- `bonus_debit` — уменьшение `balance_bonus`;
- `refund` — компенсирующая операция после charge или кассовой операции;
- `cash_top_up` — ручное пополнение с указанием кассира и смены;
- `external_payment` — подтверждённое пополнение от провайдера.

Исторические операции не обновляются и не удаляются. Refund ссылается на исходную
операцию/charge, имеет собственный idempotency key и не может вернуть больше
непогашенного остатка. Все проверки источников и итогового баланса выполняются в
одной PostgreSQL-транзакции под блокировкой клиента.

## Касса и гости

Гостевая сессия не списывается автоматически с несуществующего профиля. Для неё
создаётся `CashierPayment`:

```text
pending -> accepted -> posted
                 \-> rejected
posted -> refunded
```

Минимальные поля: `id`, `session_id`, `amount_cents`, `payment_method`, `cashier_id`,
`shift_id`, `receipt_reference`, timestamps и idempotency key. `payment_method`
на первом этапе — `cash` или `card_terminal`; онлайн-эквайринг не должен
маскироваться под кассовую операцию.

Переход `accepted -> posted` создаёт ledger operation и charge snapshot атомарно.
Повторная команда возвращает уже опубликованный результат, а конфликт суммы,
сессии или смены требует ручной проверки.

## Внешние платежи

Провайдер не вызывается из Domain и не вызывается внутри PostgreSQL-транзакции.
Application использует порт:

```python
class PaymentProvider(typing.Protocol):
    async def create_intent(self, request: PaymentIntentRequest) -> PaymentIntent:
        ...

    async def refund(self, request: RefundRequest) -> RefundResult:
        ...
```

`PaymentIntent` имеет lifecycle:

```text
created -> pending -> authorized -> captured
                    \-> failed
captured -> refunded
```

Webhook provider-а проверяется по подписи, сохраняется до применения бизнес-эффекта
и обрабатывается идемпотентно по `(provider, event_id)`. Повторный webhook не создаёт
второе пополнение. Provider secret находится только в backend secret store; он не
попадает в JWT, frontend, Windows-клиент или журнал.

Надёжная последовательность:

1. создать PaymentIntent и durable outbox record;
2. вызвать provider вне DB transaction;
3. принять подписанное событие и записать provider event;
4. worker применяет один external-payment ledger operation;
5. отметить intent/outbox завершённым или перевести его в `needs_review`.

## Порядок реализации

1. Добавить source-aware ledger и atomic bonus debit.
2. Добавить cashier payment для guest session и смены кассира.
3. Добавить compensating refunds с ограничением остатка.
4. Добавить provider port, intent/event tables и один sandbox adapter.
5. Добавить reconciliation dashboards, audit и contract tests до подключения
   реального платёжного провайдера.

До прохождения этих этапов текущий Billing остаётся `cash_only`: он списывает
только `balance_cents`, а гостевой charge требует отдельного cashier flow.
