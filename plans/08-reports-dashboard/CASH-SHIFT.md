# Cash shift — отдельный финансовый срез

Документ фиксирует границу между read-only Reports/Dashboard и будущим модулем
кассы. В текущем MVP кассовая смена не является частью `SessionCharge` и не
изменяет balance клиента.

## Ownership

Будущий Cashier/Cash Shifts модуль владеет lifecycle смены и журналом наличных
движений. Billing публикует только подтверждённый факт внутреннего списания или
внешнего платежа через публичное событие/DTO. Reports читает агрегаты, но не
открывает, закрывает и не исправляет смену.

## Lifecycle

Минимальное состояние:

```text
planned -> open -> closed
```

- `planned` — смена подготовлена, но денежные движения запрещены;
- `open` — зафиксированы оператор, касса, время открытия и opening balance;
- `closed` — закрывающий оператор зафиксировал фактический остаток, ожидаемый
  остаток и разницу; закрытая смена immutable.

В первой реализации у одного cash register допускается одна открытая смена.
Пересчёт и исправление выполняются отдельной корректирующей операцией с автором,
причиной и audit event, а не редактированием старой строки.

## Ledger

Каждое движение хранится integer cents и содержит `direction`, `reason`, `actor_id`,
`reference_type`, `reference_id`, `idempotency_key` и время. Минимальные направления:

- `cash_in` — наличное пополнение/приём оплаты;
- `cash_out` — выдача, возврат или расход;
- `correction` — только разрешённая корректировка с обязательной причиной.

`expected_close_cents = opening_balance_cents + cash_in_cents - cash_out_cents`.
Закрытие сравнивает его с `actual_close_cents` и сохраняет `difference_cents`.
Нельзя смешивать cash ledger с клиентским `balance_operations`: связь выполняется
через reference и immutable snapshot.

## Access и transport

Изменяющие команды требуют отдельного `cashier.manage` и audit. Чтение смен и
разницы требует `cashier.read` или агрегирующего `dashboard.read` согласно
политике роли. Для HTTP и gRPC используются одинаковые DTO, idempotency и
deadline/cancellation правила.

## Что нужно реализовать отдельным планом

1. Domain state machine и Money/Reference value objects.
2. PostgreSQL schema с unique open-shift constraint и immutable movement ledger.
3. Application ports, atomic open/record/close и audit policy.
4. HTTP/gRPC contracts и permission matrix.
5. Dashboard read model и отчёты по сменам/дню.
6. Concurrency, idempotency, close-day и reconciliation tests.
