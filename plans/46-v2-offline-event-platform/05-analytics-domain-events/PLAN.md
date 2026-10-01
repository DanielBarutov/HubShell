# V2.05 — подтверждённые domain events и аналитика

Статус: `planned`
Владельцы: `backend/`, `frontend/`
Зависимости: `V2.01`, `V2.03`, `V2.04`

## Цель

Сделать все побочные бизнес-эффекты прозрачными, не превратив аналитику в
write-path денег.

## Задачи

1. [ ] Определить публичные confirmed events и владельцев: deposit, balance
   debit, purchase, grant/package consume/burn, session lifecycle, refund,
   correction, reconciliation outcome.
2. [ ] Из ServerOutbox публиковать только server-confirmed events после
   финансовой транзакции; raw client events в analytics topic не допускаются.
3. [ ] Реализовать идемпотентный analytics consumer/read-model и backfill из
   immutable facts; consumer не изменяет balance/session/entitlement.
4. [ ] Разделить полученные деньги, доход от пополнения, расход депозита,
   package purchase, per-minute debit, возвраты и корректировки. Deposit не
   становится доходом второй раз при расходовании баланса.
5. [ ] Добавить operator read-model для V2 sync: last accepted sequence,
   pending age, rejected/needs-review reason без раскрытия лишней PII.
6. [ ] Версионировать новые analytics DTO/CSV additive-полями и сохранить
   совместимость текущих reads.

## Проверки

- replay domain event не удваивает метрику/выручку;
- analytics totals сверяются с financial ledger на фиксированном наборе фактов;
- pending/rejected события не попадают в confirmed revenue.

## CP-032 — 2026-09-28: контракт подтверждённого пополнения для аналитики

Выполнено:

- `BalanceCreditApplied` теперь имеет два разных payload: сообщение для
  Windows-клиента по-прежнему содержит только безопасную delta и типы методов,
  а server-only confirmed event содержит суммы по каждому методу оплаты;
- ссылки платёжного провайдера не попадают ни в клиентское, ни в confirmed
  Kafka-сообщение. Контрактная проверка подтверждает эту границу.
- добавлен application-переводчик confirmed deposit в независимые
  идемпотентные analytics outbox facts по каждому методу оплаты. Повтор того же
  Kafka-события не удваивает `deposit_income_cents`; raw client event туда не
  допускается.
- добавлен отдельный логический inbox `confirmed_analytics`. При duplicate он
  снова запускает идемпотентную запись analytics outbox, закрывая безопасным
  повтором окно между двумя сохранениями.

Осталось:

- projection/backfill и отдельные метрики расходования депозита без двойного
  признания дохода.

## CP-033 — 2026-09-28: отдельный consumer подтверждённой V2-аналитики

Выполнено:

- добавлен `v2-confirmed-analytics`: отдельная FastStream consumer group
  `confirmed_analytics` читает только `v2.confirmed-domain-events`;
- один PostgreSQL commit создаёт логический inbox и analytics outbox. Повтор
  возвращает `duplicate`, конфликт или повреждённый/неподтверждённый факт до
  offset commit переносится в закрытый `v2.failed-events`;
- worker не получает client facts и не имеет операций изменения balance,
  session или entitlement. Prometheus и Grafana получили отдельный target и
  панель состояния/logs;
- 6 focused тестов, Ruff, Compose config и `git diff --check` прошли. Живой
  Compose-контур подтвердил Kafka → worker → PostgreSQL и `up = 1` в
  Prometheus.

Осталось:

- projection/backfill confirmed facts и метрики расходования депозита без
  двойного признания дохода; затем confirmed события для списаний, пакетов,
  сессий, возвратов и корректировок.

## CP-034 — 2026-09-28: projection confirmed V2-фактов

Выполнено:

- scheduler ставит `analytics-projection` вместе с другими периодическими
  задачами, но не исполняет business rules;
- отдельный `analytics-worker` обслуживает только `analytics-projection` и
  `analytics-reports`, не смешивая read-model с billing/session workers;
- actor применяет immutable outbox и только логирует число обработанных фактов,
  не возвращая неиспользуемый результат Dramatiq;
- живой Compose-тест подтвердил Kafka → analytics inbox/outbox → Dramatiq
  projection → `analytics_projection_events`. Шесть integration проверок
  прошли, а временные факты теста удаляются.

Осталось:

- backfill immutable facts и метрики расходования депозита без двойного
  признания дохода; confirmed события для списаний, пакетов, сессий, возвратов
  и корректировок.

## CP-035 — 2026-09-28: подтверждённое поминутное списание

Выполнено:

- для `PER_MINUTE_DEBIT` закреплён payload версии 1: обязательны
  `amount_cents` и `tariff_id`; старое поле `debit_delta_cents` не является
  V2-контрактом и сервер не подтверждает такой факт;
- после проверки lease, snapshot, sequence/hash-chain и записи immutable
  client fact reconciliation в той же PostgreSQL-транзакции создаёт отдельное
  `server:reconciliation` событие в `v2.confirmed-domain-events`. В нём нет
  локального `balance_after_cents`, только сумма, тариф и ссылка/hash исходного
  факта;
- analytics переводит это событие в идемпотентный `wallet_debit_cents`.
  Это расходование ранее пополненного депозита, поэтому `revenue_cents` и
  `deposit_income_cents` не увеличиваются;
- unit-проверки подтвердили метрику, отсутствие локального баланса в public
  событии и отказ устаревшего поля. Настоящий Compose-контур подтвердил путь
  Kafka client fact → server reconciliation/outbox → confirmed analytics →
  analytics projection; временные записи теста удаляются.

Осталось:

- backfill уже сохранённых immutable V2 facts; подтверждённые события и
  отдельные аналитические правила для package purchase/consume/burn, session
  lifecycle, refund и correction. Их финансовая семантика не добавляется этим
  checkpoint.

## CP-036 — 2026-09-28: возобновляемый backfill поминутных списаний

Выполнено:

- additive migration создаёт сохранённое состояние исторического запуска:
  фиксированную верхнюю границу и keyset-курсор `(confirmed_at, event_id)`;
  новые факты после границы по-прежнему обрабатывает обычный Kafka consumer;
- одна транзакция выбирает порцию immutable `v2_confirmed_client_facts`,
  восстанавливает только server-owned confirmed debit, записывает analytics
  inbox/outbox и сдвигает курсор. Повтор не создаёт вторую метрику;
- legacy/повреждённый payload получает durable skip с причиной и не блокирует
  следующую порцию. Сумма из `debit_delta_cents` не угадывается;
- actor использует существующую analytics queue и после `completed` становится
  безопасным no-op.

Проверено:

- настоящая PostgreSQL: одинаковый `confirmed_at`, legacy skip, продолжение по
  cursor, completion и повтор без второй analytics записи.

Осталось:

- собрать и перезапустить Docker-контейнеры с этим кодом после восстановления
  доступа к образу `python:3.12-slim`; текущая сеть Docker Hub недоступна, а
  запущенные контейнеры не содержат новый actor.
