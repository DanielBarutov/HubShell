# Cash Shifts — producer contract

Этот документ фиксирует границу между наличным ledger и producer-модулями.
Конкретный платёжный провайдер ещё не выбран, поэтому application contract не
зависит от его SDK, webhook-формата или deployment-модели.

## Что является наличным движением

`Cash Shifts` принимает только подтверждённое движение, которое оператор или
доверенный внутренний producer может однозначно связать с источником:

| Producer | `reference_type` | `reference_id` | Разрешённое направление |
| --- | --- | --- | --- |
| Billing cash settlement | `billing_settlement` | immutable charge/settlement ID | `cash_in` |
| External Payment | `external_payment` | provider + payment ID | `cash_in` или `cash_out` |
| Operator correction | отсутствует либо отдельная correction reference | audit/request ID | `correction` |

`reference_type` и `reference_id` передаются вместе. Пара уникальна во всём
cash ledger, а повторная доставка с тем же источником должна использовать тот
же `Idempotency-Key` и возвращать уже сохранённое движение. Движение нельзя
редактировать или удалять; ошибка исправляется новой корректировкой.

## Billing boundary

Текущий `SessionCharge` списывает клиентский баланс и не создаёт наличное
движение автоматически. Это намеренная граница: внутреннее списание не доказывает,
что оператор получил наличные.

`BillingCashSettlementProducer` сначала принимает подтверждённый immutable
settlement record, затем вызывает публичный Cash Shifts application command с:

- `shift_id` и `amount_cents`;
- `reference_type=billing_settlement`;
- стабильным `reference_id` settlement-а;
- producer-derived idempotency key;
- причиной и actor/service identity.

Cash Shifts не читает таблицы Billing напрямую и не меняет `SessionCharge`.
Если settlement ещё не подтверждён, producer не имеет права записывать
`cash_in`.

## External Payment boundary

`ExternalPaymentProducer` принимает результат provider adapter. Сам adapter должен
нормализовать webhook/response в собственную запись
платежа и отправлять движение только после проверки подписи, статуса и суммы.
Повторный webhook, неизвестный payment ID, несовпадение суммы или попытка
использовать reference повторно должны завершаться конфликтом/ручным review,
а не вторым движением.

До выбора конкретного провайдера producer использует provider-neutral
`ExternalPayment` DTO. Raw webhook, подпись, секреты и PII не проходят в Cash
Shifts и не сохраняются в его ledger.

## Supervisor approval

Для рискованных операций действует отдельное право `cashier.supervise` и
immutable approval record для:

- signed `correction`, если она меняет ожидаемый остаток;
- закрытия смены с ненулевым `difference_cents`;
- ручного `cash_out`, если политика клуба задаст порог.

Approval ссылается на target idempotency key, содержит supervisor subject, время и
причину. Операторское право `cashier.manage` не означает supervisor approval.
Correction дополнительно требует `cashier.correct`, а закрытие с расхождением —
`cashier.supervise` и approval. Approval выдаётся через HTTP/gRPC command и
сохраняется в `cash_approvals`; отказ остаётся видимым в общем audit trail.
Проверка approval выполняется также внутри `CashShiftService`, а не только в
transport handler; закрытие использует optimistic expected-balance check, чтобы
гонка с новым движением не превратила неподтверждённую разницу в закрытую смену.

## Acceptance criteria

- producer не имеет прямого доступа к таблицам Cash Shifts;
- duplicate webhook не меняет ожидаемый остаток второй раз;
- один immutable reference не может быть связан с двумя движениями;
- неподтверждённый settlement не появляется в cash ledger;
- producer-ы не имеют прямого доступа к Cash Shift repository;
- approval и отказ видны в audit без записи платёжных секретов или PII.
