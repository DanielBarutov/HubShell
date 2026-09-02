# План 31 — единый settlement и reconciliation

Статус: `in_progress`
Приоритет: `P0`
Владелец: `backend/`
Зависимости: `02-clients-guests`, `07-billing`, `09-cash-shifts`,
`10-product-sales`, `13-payment-methods`,
[`29-contract-alignment`](../29-contract-alignment/PLAN.md)

## Цель

Довести уже опубликованный `PaymentPart` до атомарного и повторяемого
финансового сценария для top-up, product sale и guest direct payment. Ни один
частично проведённый mixed payment не должен оставлять неясное состояние между
balance ledger, cash ledger, sale/payment fact и stock reservation.

## Контрактная граница

Источник правил: [`backend/PRODUCT-CONTRACT.md`](../../backend/PRODUCT-CONTRACT.md)
и [`CODEX.md`](../../CODEX.md).

- `PaymentPart` provider-neutral: method, positive amount, optional reference;
  сумма частей равна total.
- Balance part возможен только для зарегистрированного клиента.
- Cash part требует открытой смены и сохраняет ссылку на cash movement.
- Payment method settings не являются проведением платежа.
- Повтор idempotency key возвращает исходный результат, а не повторяет debit,
  cash movement, unlock или stock reservation.

## Текущее состояние

DTO, JSONB snapshots и mixed sale boundary уже добавлены. Известный разрыв —
последовательное проведение частей может оставить частичное settlement при
ошибке следующей части; guest payment fact и cash movement также ещё не имеют
полной reconciliation границы.

## Реализовано в текущем срезе

Payment parts, immutable snapshots, pending sale reservation и статус
`needs_review` подключены к memory/PostgreSQL repositories и frontend. Ошибка
после начала balance/cash side effect больше не отменяет sale автоматически;
review rows доступны оператору через `list_sales`.

## Входит в план

- единый settlement intent/fact с immutable total и part snapshots;
- transaction boundary между owner-модулями через публичные application ports;
- durable reconciliation status `pending/completed/needs_review`;
- deterministic ledger keys для каждой операции и части;
- retry worker с тем же idempotency key и безопасным manual review;
- top-up, sale и guest payment failure matrix;
- audit/permission/approval checks без внешних provider integrations.

## Не входит

- эквайеры, webhooks, refund/chargeback и bonus spending;
- basket/order semantics и возврат товара;
- прямой доступ Sales к таблицам Clients/Cash Shifts;
- автоматическое скрытие финансовой ошибки от оператора.

## Порядок задач

1. [x] Описать settlement state machine и ownership: intent создаёт owner
   операции, ledger adapters публикуют результат, reconciliation владеет
   recovery-состоянием.
2. [x] Зафиксировать уникальные ключи для top-up, sale, guest payment и каждой
   части; добавить conflict response при повторе с другим payload.
3. [x] Ввести compensating `needs_review` flow там, где общей БД-транзакции
   компенсирующий `needs_review` flow, если атомарная БД-граница невозможна.
4. [x] Переписать mixed sale так, чтобы stock reservation, parts и итоговый
   sale не публиковались как completed при частичном сбое.
5. [x] Связать guest direct payment с cash movement и server confirmation;
   session start разрешать только по завершённому payment fact.
6. [ ] Добавить reconciliation worker, retry/backoff, audit и operator review;
   worker не должен молча повторять cash side effect.
7. [x] Обновить HTTP/gRPC responses и frontend DTO для `pending/needs_review`.
8. [ ] Покрыть PostgreSQL-повторы и fault injection между каждым шагом settlement.

## Критерии готовности

- completed sale/payment имеет все parts и подтверждённые owner-ledger refs;
- при неопределённом результате создаётся `needs_review`, а не второй debit;
- guest session не стартует по одной только локальной UI-операции;
- денежные суммы и references неизменяемы после завершения;
- настройки метода оплаты не обходят cash-shift/permission boundary.

## Проверки и evidence

- unit/API/gRPC idempotency tests;
- PostgreSQL transaction/concurrency tests с реальными locks/constraints;
- fault injection между debit/cash/stock/fact шагами;
- reconciliation retry и duplicate-delivery tests;
- live Compose smoke только после обновления миграций.

## Открытые решения

- единый PostgreSQL UoW для нескольких owner-репозиториев или outbox+
  reconciliation как обязательный MVP-путь;
- допустима ли ручная коррекция `needs_review` только через supervisor approval;
- какие payment methods разрешаются в MVP beyond `balance`/`cash`.

## Остаток и release blocker

Денежный ledger, cash ledger, stock и sale пока не объединены общей
PostgreSQL-транзакцией; review является безопасным компенсирующим контуром.
Нужны worker/review action и fault-injection matrix для неизвестного cash
результата, а также PostgreSQL evidence.
