# V2.04 — депозит, платежи и идемпотентная balance delta

Статус: `in_progress`
Владельцы: `backend/`, `frontend/`, `win-client/`
Зависимости: `V2.00`, `V2.01`, `V2.03`

## Цель

Сделать пополнение наблюдаемым и повторяемо безопасным во время offline
клиентской сессии.

## Задачи

1. [partial: V2 HTTP route создаёт стабильный `payment_operation_id` из
   client/header key и repository отличает другой payload; операторский UI
   pending/delivery остаётся] Описать операторское `payment_operation_id`/
   `Idempotency-Key`: повтор с тем же hash возвращает прежний результат,
   другой payload — error/review.
2. [~] В одной server transaction создать `DepositCredit`, payment parts,
   автора, cash shift/reference, audit, balance ledger delta и ServerOutbox
   `BalanceCreditApplied`.
3. [~] Определить event payload: `event_id`, `deposit_operation_id`,
   `amount_delta_cents`, currency, ledger version, occurred_at, causation id.
   Запрещено передавать только absolute balance.
4. [~] Клиент применяет credit в своей локальной транзакции лишь один раз по
   `event_id` и `deposit_operation_id`; pending local debits суммируются с ним.
5. [ ] Отдельно обработать refund/correction как новые противоположные факты,
   не редактируя исходный DepositCredit. При недостатке локального остатка
   correction может потребовать `NEEDS_REVIEW`.
6. [partial: операторский экран направляет пополнение с V2 ПК в защищённый
   V2 route, фиксирует session/device и показывает initial `pending_delivery`;
   подтверждение фактического получения Windows-клиентом ещё не приходит]
   Отразить V2 delivery/pending состояние в operator UI: оператор видит,
   что деньги приняты сервером, а offline ПК ещё не получил событие.

## Проверки

- double click, timeout/retry, одинаковая сумма с разными ключами;
- top-up до, во время и после offline с pending purchase/debit;
- mixed payment/audit compatibility и отсутствие двойного признания дохода.

## CP-017 — 2026-09-27: серверная transaction boundary для пополнения

Выполнено:

- добавлен `V2DepositCreditCommand`: серверный `payment_operation_id` служит
  ключом идемпотентности, а canonical request hash отличает повтор от другой
  операции с тем же ключом;
- migration `0064` добавляет неизменяемую связь между payment operation,
  действующим `balance_operations` ledger и двумя event id;
- один PostgreSQL commit включает увеличение balance, `balance_operations` с
  payment parts, движение открытой cash shift (если есть cash), audit,
  `v2_deposit_credits` и две записи outbox: клиентскую
  `v2.server-events` и подтверждённую `v2.confirmed-domain-events`;
- клиентское событие содержит только `amount_delta_cents`, currency,
  `deposit_operation_id` и типы способов оплаты: абсолютный баланс и payment
  reference туда не попадают. У него key `client_id/session_id`;
- migration применена к живой локальной Compose PostgreSQL. Smoke подтвердил:
  первый credit меняет balance ровно раз, повтор даёт duplicate, созданы один
  ledger/audit/deposit и два outbox-факта. Отдельные Kafka consumer прочли оба
  Protobuf события. Ошибка несуществующей cash shift откатила весь commit:
  balance, ledger, deposit и outbox не изменились;
- выполнены 46 focused Python тестов, Ruff, `alembic heads` (`0064`) и
  `git diff --check`.

Осталось:

- пока нет защищённого operator HTTP/gRPC endpoint и server-owned привязки
  активного V2 session/device, поэтому запрос пока собирается только из
  доверенного application boundary, а не из публичного API;
- сервер хранит `balance_operation_id` как стабильную ссылку ledger, но событие
  не притворяется глобальным monotonic `ledger_version`: такого счётчика нет в
  текущей схеме и его нельзя выдавать за реализованный;
- C# умеет применить идемпотентную delta, но Kafka inbound dispatcher ещё не
  извлекает payload и не вызывает этот путь;
- refund/correction, operator pending/delivery UI, analytics consumer и
  успешный cash-shift smoke остаются отдельными задачами.

## CP-020 — 2026-09-27: lease guard для V2 пополнения

Выполнено:

- перед финансовым commit V2 deposit теперь блокирует и проверяет active,
  неистёкший server-owned lease с теми же client/device/session;
- без lease не создаются balance operation, audit, deposit или outbox; после
  выдачи matching lease первый credit принимается, а повтор остаётся duplicate;
- добавлена настоящая PostgreSQL integration-проверка этого сценария.

Осталось:

- V2 login и lease выдаются production route, но операторский UI ещё не
  выбирает V2 target session/device и не показывает pending delivery.

## CP-027 — 2026-09-27: защищённый HTTP-маршрут V2 пополнения

Выполнено:

- `POST /api/v1/clients/{client_id}/v2-deposits` требует право
  `clients.manage`, header `Idempotency-Key`, цель `session_id`/`device_id`,
  состав оплаты и валюту. Сервер выводит `payment_operation_id` только из
  клиента и ключа, а repository проверяет active V2 lease;
- ответ сообщает созданные event/ledger identifiers, сумму, время и
  `pending_delivery`, не раскрывая абсолютный баланс Windows-клиенту;
- API-тест подтвердил identity оператора, стабильный ключ операции, нормализацию
  валюты и pending результат. PostgreSQL-проверки сохраняют атомарный ledger,
  audit и два outbox-события.

Осталось:

- нет server-to-operator статуса фактического получения конкретного event на
  Windows-клиенте: экран честно показывает только `pending_delivery` после
  server commit. Нужна read-model/обновление по acknowledged client inbox и
  проверка в обычном браузере.

## CP-028 — 2026-09-28: V2-пополнение из панели игрового места

Выполнено:

- кнопка пополнения в панели занятого V2 ПК передаёт только активные
  `session_id` и `device_id`; экран фиксирует получателя и не может случайно
  вызвать старый V1 `top-up`;
- новый frontend API вызывает `/clients/{client_id}/v2-deposits` с отдельным
  `Idempotency-Key`; после ответа отображается «принято сервером» и честный
  `pending_delivery`, без абсолютного баланса и без утверждения, что Windows
  уже получил событие;
- component test проверяет адресацию к сессии/устройству, блокировку смены
  получателя и отсутствие V1-маршрута. TypeScript typecheck, этот test и
  production build frontend прошли.

Осталось:

- карточка ПК пока не знает конечный статус delivery: нужен server read-model
  подтверждённого client inbox и его показ на карте/в панели;
- нужно открыть интерфейс в обычном браузере и вручную пройти V2-сценарий;
  модульный тест и production build не проверяют вид, состояние сети и
  реальный серверный lease.
