# План 09 — Cash Shifts / кассовые смены

Статус: `in_progress`  
Приоритет: `P1`  
Владелец: `plans/09-cash-shifts/`
Зависимости: `07-billing`, `08-reports-dashboard`, `04-auth-security`

## Цель

Добавить отдельный модуль кассовых смен и наличного ledger без смешивания
клиентского баланса, session charge и read-only отчётов.

## Реализованный срез

- открытие одной смены на кассовый register;
- запись `cash_in`, `cash_out` и signed `correction` движений;
- атомарное обновление ожидаемого остатка;
- закрытие смены с фактическим остатком и разницей;
- HTTP и gRPC contracts с permissions `cashier.read`/`cashier.manage`, а для
  signed-корректировки — отдельным `cashier.correct`;
- memory/PostgreSQL adapters, unique constraints и advisory locks;
- idempotency для открытия, движения и закрытия;
- обязательная парная ссылка `reference_type`/`reference_id` и уникальность
  immutable reference для Billing/внешнего платежа;
- application producers для подтверждённого Billing settlement и внешнего payment
  capture без прямого доступа к repository;
- supervisor approvals для correction и закрытия смены с ненулевым расхождением;
- approval records в memory/PostgreSQL с отдельным `cashier.supervise`;
- application-слой повторно проверяет approval для correction/расхождения и
  атомарно закрывает смену только если ожидаемый остаток не изменился после чтения;
- audit для изменяющих HTTP/gRPC методов.

## Ownership

Cash Shifts владеет только наличной сменой, движениями и approval records. Billing
не пишет в repository напрямую: подтверждённый settlement проходит через
`BillingCashSettlementProducer`, внешний provider — через
`ExternalPaymentProducer`. Reports
читает публичные DTO, но не изменяет смену.

## Задачи

1. [x] Зафиксировать domain state machine и integer-cents invariants.
2. [x] Добавить PostgreSQL schema, indexes и partial unique open-shift constraint.
3. [x] Реализовать application ports, atomic open/record/close и idempotency.
4. [x] Добавить HTTP/gRPC contracts и permission matrix.
5. [x] Подключить отдельный cashier UI в frontend: открытие смены, приход/расход/
   корректировка, закрытие и история через typed BFF.
6. [x] Добавить unit/API/contract tests и выполнить PostgreSQL smoke/concurrency.
7. [x] Добавить immutable reference fields с парной валидацией и уникальностью,
   а также policy корректирующих операций с отдельным permission и audit.
8. [x] Подключить application producer-контракты Billing/внешнего платежа и
   supervisor approval для рискованных операций; provider-neutral граница
   зафиксирована в [`PRODUCER-CONTRACT.md`](PRODUCER-CONTRACT.md).
9. [x] Добавить расписание кассы с часовым поясом, автооткрытием и автозакрытием
   через Dramatiq scheduler; ручные open/close остаются доступны. Автозакрытие
   без физического пересчёта использует ожидаемый ledger-остаток, а фактический
   пересчёт с расхождением выполняется оператором вручную.

## Проверки

- unit tests state machine, negative cash и idempotency;
- API/gRPC contract tests;
- PostgreSQL unique-open and concurrent movement tests;
- Ruff, generated protobuf check and frontend type/build check.

## Открытые вопросы

- один register на клуб или отдельный register на филиал;
- нужен ли дополнительный двухэтапный review для особо крупных сумм;
- какой внешний payment provider создаёт reference;
- нужен ли отдельный cashier UI для разных касс/филиалов; MVP уже подключает
  кассу отдельным разделом операторской web-оболочки.
