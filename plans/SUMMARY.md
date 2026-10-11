# GameClub / HubShell — сводка проекта

2026-10-11: размер карты мест по умолчанию изменён на 10 столбцов × 4 ряда.
Сохранённые настройки браузера имеют приоритет; 8 тестов MapScreen и production
build проходят. Контракт и frontend-план обновлены.

2026-10-11: исправлена повторная попытка автозакрытия кассы после ручного
открытия новой смены в тот же день (`uq_cash_shifts_close_idempotency_key`).
Расписание проверяет точные ключи выполненных действий; 18 unit-тестов кассы
и jobs проходят. Обновление работающего worker и PostgreSQL integration не выполнены.

Дата среза: `2026-09-17`<br>
Назначение: быстрый вход в проект без загрузки всего репозитория в контекст.

Этот файл фиксирует фактическое состояние кода, планов и проверок на дату среза.
Он не заменяет исходный код и детальные планы: при изменении контракта сначала
обновляются соответствующий план и проверка, затем эта сводка.

## 1. Как пользоваться сводкой

Порядок чтения для новой задачи:

1. `CODEX.md` — обязательные архитектурные и security-правила проекта.
2. Нужный раздел этой сводки — граница модуля, путь к коду и текущий статус.
3. Детальный владеющий план: [`plans/`](./),
   [`frontend/PLAN.md`](../frontend/PLAN.md) или [`win-client/PLAN.md`](../win-client/PLAN.md).
4. [`VERIFICATION.md`](VERIFICATION.md) — что реально проверено и где находится
   граница доказательства.

Обозначения статуса:

- `реализовано` — код и основной сценарий присутствуют;
- `проверено` — есть соответствующий тест, live smoke или другой указанный чек;
- `source-level` — подтверждено чтением/статическим контрактным чеком, но не
  полноценным запуском целевой платформы;
- `осталось` — следующая работа или ограничение, которое нельзя считать закрытым.

## V2: запланированная автономная событийная платформа

В ветке `V2` выполняется master-план
[`46-v2-offline-event-platform`](46-v2-offline-event-platform/PLAN.md). Это
целевая архитектура, не описание уже работающего кода. Она переводит только
Windows business-session path с server-owned gRPC расчёта на автономную сессию
после подписанного snapshot, Kafka, постоянные inbox/outbox и последующую
сверку сервером. V2 будет поставлена атомарной заменой: в конечном релизе нет
V1 runtime, режима workstation, fallback или постепенного переключения ПК.
Существующая PostgreSQL с бизнес-данными сохраняется как server-owned источник
snapshot и истории; V1-сессии не переносятся в V2 неявно.

План разделён на контрактные решения, event contracts, client ledger, server
reconciliation, deposit/payments, analytics, Grafana/Loki/Tempo/Prometheus,
migration и verification. До его выполнения текущие gRPC/product-contract
правила остаются действующими. Нельзя считать V2 реализованным по наличию схем
Storm BPMN или этого плана: нужны реальные PostgreSQL, Kafka, browser и native
Windows доказательства.

Checkpoint `CP-001` от `2026-09-27`: product contracts получили V2-границу, а
в backend добавлен изолированный `eventing_v2` foundation — канонический event
envelope и in-memory inbox duplicate/conflict boundary. Это подтверждено
4 focused unit-тестами и Ruff; Kafka, PostgreSQL outbox/inbox, Windows client,
платёжная доставка и observability ещё не реализованы.

Checkpoint `CP-002` от `2026-09-27`: добавлена additive migration
`20260927_0063_v2_event_inbox` и PostgreSQL adapter с уникальным ключом
producer/operation. 5 focused unit-тестов, Ruff и `alembic heads` прошли;
настоящая PostgreSQL concurrency-проверка не запускалась, потому что в
окружении нет `GAMECLUB_TEST_POSTGRES_DSN`.

Checkpoint `CP-003` от `2026-09-27`: inbox разделён на логические границы по
`consumer_name`, поэтому независимые worker groups смогут один раз обработать
один confirmed event каждая. 6 focused unit-тестов подтверждают duplicate и
fan-out in-memory; реальные Kafka workers и PostgreSQL concurrency evidence
ещё отсутствуют.

Checkpoint `CP-004` от `2026-09-27`: в backend добавлен FastStream поверх
Kafka и постоянная server outbox. Она сохраняет неизменяемый V2-конверт и
не отмечает его отправленным, пока Kafka не подтвердит публикацию; при ошибке
запись остаётся ожидающей повторной отправки. Есть точка подключения группы
`client_session_facts`, но настоящий процесс с PostgreSQL и Kafka ещё не
запускался. 10 focused unit-тестов, Ruff, проверка миграции и `git diff --check`
прошли; это не доказывает работу с реальным брокером или базой.

Checkpoint `CP-005` от `2026-09-27`: V2-конверт получил обязательные связи
причин (`causation_id`), сессии обработки (`correlation_id`) и W3C-трассу
`traceparent`. Входящий Kafka-конверт проходит строгую проверку до вызова
бизнес-обработчика, а FastStream передаёт trace context в заголовках Kafka.
13 focused unit-тестов это проверяют; реальная Kafka/OpenTelemetry-проверка и
совместимость с Windows-клиентом ещё не выполнялись.

Checkpoint `CP-006` от `2026-09-27`: создан общий Protobuf-контракт
`gameclub.events.v2.EventEnvelope`. FastStream теперь передаёт его bytes в
Kafka, а C# transport-проект подключает тот же исходный `.proto`. Номера полей
и reserved range защищены контрактным тестом. 36 Python-проверок и Linux-сборка
C# прошли; они не подтверждают реальное подключение Kafka или запуск на
Windows-ПК.

Checkpoint `CP-007` от `2026-09-27`: в переносимом C# ядре Windows-клиента
реализована V2-модель локального ledger. Она автономно расходует grant,
пакеты и поминутный баланс, покупает известные пакеты, корректно ведёт себя при
раннем выходе и применяет server balance delta один раз. 56 C# тестов прошли
на Linux; долговременное локальное хранилище, Kafka и реальный Windows-ПК ещё
не проверялись.

Checkpoint `CP-008` от `2026-09-27`: V2 ledger и client outbox сохраняются
одним DPAPI-защищённым Windows-файлом. Локальный координатор не позволит
сначала изменить баланс, а потом отдельно пытаться добавить событие в outbox.
58 C# тестов и Linux-сборка Windows-проекта прошли; DPAPI, сбой питания,
диск и права файлов всё ещё требуют проверки на реальном Windows-ПК.

Checkpoint `CP-009` от `2026-09-27`: в защищённый V2-снимок добавлен ClientInbox,
а outbox-отправитель удаляет факт только после ответа транспорта и не нарушает
порядок sequence при ошибке. C# сериализатор формирует полный общий Protobuf
конверт из сохранённого факта. 61 C# тест прошёл; реальный Kafka client/gateway,
retry и проверка Windows всё ещё не реализованы.

Checkpoint `CP-010` от `2026-09-27`: определён подписываемый
`OfflineSessionSnapshot` с balance, grant, пакетами и тарифными снимками.
Клиент создаёт ledger только после проверки подписи; Python и C# проверяют
одинаковые детерминированные bytes payload. 37 Python-проверок и 64 C# теста
прошли. Реальная выдача, ключи подписи и V2 login ещё не реализованы.

Checkpoint `CP-011` от `2026-09-27`: server domain проверяет непрерывность
sequence и hash-chain V2-фактов. Он не может незаметно принять пропуск или
подменённый предыдущий hash. 39 Python-тестов прошли; checkpoint пока не
записан в PostgreSQL и не соединён с реальным FastStream consumer.

Checkpoint `CP-012` от `2026-09-27`: `v2_session_chains` и PostgreSQL
compare-and-save adapter добавляют постоянный checkpoint sequence/hash-chain.
40 Python-тестов прошли. Нужна отдельная проверка на настоящей PostgreSQL с
`GAMECLUB_TEST_POSTGRES_DSN`: локальные тесты не доказывают блокировки и гонки
реальной базы.

Checkpoint `CP-013` от `2026-09-27`: backend подготовлен к подписи snapshot
через изолированный port, без хранения приватного ключа в V2-коде. 41 Python
тест прошёл. Реальный ключ Ed25519, key rotation и выдача snapshot при входе
ещё не реализованы.

Checkpoint `CP-014` от `2026-09-27`: добавлен изолированный Compose profile
`v2` с Kafka KRaft, явным созданием V2 topics и FastStream-процессом
`v2-server-outbox`. Процесс доставляет постоянный server outbox только после
подтверждения Kafka. Compose config, 42 Python-теста, Ruff и `git diff --check`
прошли; consumer клиентских фактов намеренно не включён до готовой одной
PostgreSQL-транзакции inbox+state.

Checkpoint `CP-015` от `2026-09-27`: живой Compose smoke подтвердил цепочку
PostgreSQL `v2_server_outbox` → FastStream → Kafka → Protobuf consumer. В ходе
проверки исправлены отсутствие `faststream[cli]` в образе и передача Kafka key
строкой вместо bytes; уже сохранённый pending факт был корректно доставлен.
Это не доказывает consumer клиентских фактов, финансы, observability или
Windows transport.

Checkpoint `CP-016` от `2026-09-27`: подготовлен source-level контур
наблюдаемости V2: FastStream получает OpenTelemetry/Prometheus middleware,
Compose — Collector, Prometheus, Loki, Tempo, Alloy и Grafana с начальной
панелью. Перед Loki типовые секреты маскируются. Конфигурация Compose и 42
contract-теста прошли, но Docker daemon не смог скачать новые образы из-за
недоступного IPv6 пути к registry; живое доказательство Grafana/метрик/логов/
трасс и Windows instrumentation пока отсутствуют.

Checkpoint `CP-017` от `2026-09-27`: добавлена атомарная server boundary V2
для пополнения. Один PostgreSQL commit пишет balance ledger, payment parts,
cash shift при наличном платеже, audit, immutable deposit и два outbox-факта;
клиент получает только идемпотентную delta без абсолютного баланса и payment
reference. В живой Compose PostgreSQL повтор изменил баланс ровно раз, Kafka
прочитала оба Protobuf facts для клиента и аналитики, а ошибка cash shift
откатила всё. Открыты HTTP/auth/session target, global ledger version,
refund/correction, operator UI, analytics consumer и C# inbound dispatcher.

Checkpoint `CP-018` от `2026-09-27`: исправлена V2 inbox-схема, чтобы один
Kafka факт мог попасть в несколько логических consumer groups. Новый атомарный
PostgreSQL reconciliation boundary проверяет тип/duplicate/hash-chain и одним
commit создаёт inbox, confirmed source fact, audit и result outbox; live test
подтвердил fan-out без второго side effect. Kafka consumer всё ещё намеренно
не включён до device/snapshot/lease validation, controlled reject/DLQ и
финансовых projections по фактам.

Checkpoint `CP-019` от `2026-09-27`: reconciliation теперь требует
server-owned активный неистёкший V2 lease, совпадающий по client/device/session;
без него нельзя записать inbox или outbox side effect. Migration `0066`
применена и PostgreSQL тест проходит. Выдача/revoke lease после device auth и
подписанного snapshot, а также публичный V2 login, пока не реализованы.

Checkpoint `CP-020` от `2026-09-27`: V2 deposit также требует matching active
lease до единого финансового commit. PostgreSQL test доказал отказ без lease и
однократный credit с повтором после lease. V1 UI top-up остаётся отдельным
совместимым маршрутом, пока не появятся V2 login/snapshot и V2 operator API.

Checkpoint `CP-021` от `2026-09-27`: V2 lease может быть бессрочным для
длительного offline, issuer запрещает второй active lease client/device, а
snapshot factory собирает новый подписываемый Protobuf payload из старых
server-owned Client/Session/Entitlement/Tariff данных. Production signer,
C# verifier и V2 login endpoint ещё отсутствуют.

Checkpoint `CP-022` от `2026-09-27`: backend подписывает snapshot отдельным
Ed25519 private key из server settings, а Windows transport проверяет его
набором public keys по `key_id`. Python/C# подтвердили общий standard vector и
подпись полного deterministic protobuf payload. Также `debt_limit_cents`
исправлен на единый неотрицательный предел долга для server snapshot и client
ledger. Ключи пока не подключены к production secret storage/deployment, а
device-authenticated V2 login с atomic lease/outbox ещё отсутствует.

Checkpoint `CP-023` от `2026-09-27`: migration `0068` сохраняет exact signed
snapshot, key id и hash рядом с V2 lease. В одной PostgreSQL-транзакции
создаются lease, `LoginSnapshotIssued` в outbox и audit; повтор возвращает те
же bytes без второго side effect. Server теперь отвергает client fact, если
его `snapshot_id`/версия не совпадают с lease. Реальный gRPC V2 login и выдача
snapshot в Windows access-gate пока не подключены.

Checkpoint `CP-024` от `2026-09-27`: migration `0069` вводит явный режим
рабочего места — все существующие ПК остаются в V1, а `v2_local_ledger`
включается отдельно. Новый V2 gRPC-вход требует совпадающую device identity и
пароль клиента, создаёт только V2-сессию и возвращает signed snapshot из
server-owned данных. Повтор после потери ответа возвращает сохранённый
snapshot без второго outbox/audit; это проверено unit, gRPC и настоящей
PostgreSQL. Новый proto подключён в C# transport, но access-gate его пока не
вызывает.

Checkpoint `CP-025` от `2026-09-27`: V2 login теперь сохраняет новую Session,
signed snapshot, lease, audit и login outbox одной PostgreSQL-транзакцией.
Sessions предоставляет узкий transaction writer, поэтому V2 не обращается к
его таблице напрямую. Настоящая PostgreSQL-проверка принудительно создаёт
конфликт lease после подготовки Session и подтверждает rollback без «висячей»
активной сессии. Нужна новая сборка контейнеров и ручной V2 gRPC-сценарий;
access-gate, public-key deployment, ротация и revoke пока не реализованы.

Checkpoint `CP-026` от `2026-09-27`: режим V1/V2 проходит через API,
операторский редактор и карту ПК. Backend сам запрещает смену режима при
активной сессии, а UI отключает этот выбор заранее. TypeScript typecheck,
11 frontend-тестов и backend-проверки прошли. Нужно открыть интерфейс в
обычном браузере и вручную проверить сценарий; тесты не подтверждают
расположение и читаемость элементов на экране.

Checkpoint `CP-027` от `2026-09-27`: появился защищённый HTTP-маршрут
V2-пополнения. Он требует operator permission, ключ идемпотентности и целевую
V2 session/device, проверяет lease и возвращает `pending_delivery` без
абсолютного баланса. API и PostgreSQL-проверки прошли. Операторский экран ещё
не использует этот маршрут и не показывает доставку на ПК.

Checkpoint `CP-028` от `2026-09-28`: пополнение из панели занятого V2-ПК
передаёт его активные session/device только в защищённый V2-маршрут, фиксирует
получателя и после server commit показывает `pending_delivery`. Экран не
выдаёт это за факт получения Windows-клиентом. TypeScript typecheck, component
test и frontend production build прошли; нужно открыть интерфейс в обычном
браузере и вручную пройти сценарий с настоящим серверным lease.

Checkpoint `CP-029` от `2026-09-28`: Windows-клиент проверяет адресный
`BalanceCreditApplied` до изменения локального баланса: server producer,
payload hash и client/session/device. ClientInbox применяет дельту ровно раз,
а чужое событие отклоняется без изменения ledger. Linux `dotnet test` прошёл:
69 тестов, включая отказ при подмене payload. Реального Kafka consumer и server-side подтверждения доставки ещё
нет, поэтому операторский экран пока честно показывает только pending.

Checkpoint `CP-030` от `2026-09-28`: Compose V2 получил отдельный FastStream
worker `v2-client-facts`. Он передаёт факт в PostgreSQL reconciliation без
server minute confirmation; accepted/duplicate завершают commit до Kafka
offset, а invalid/conflict сначала переносятся в закрытый DLQ. Добавлены
Prometheus/Grafana/Loki source configuration. Focused Python + PostgreSQL
проверки: 29 passed. Worker собран и работает: реальный факт прошёл Kafka →
PostgreSQL, consumer group имеет нулевой lag. Не проверены DLQ, restart между
commit и offset, TLS/SASL/ACL и Windows Kafka transport.

Checkpoint `CP-031` от `2026-09-28`: живой контур V2 наблюдаемости запущен в
Compose. Grafana видит Prometheus/Loki/Tempo и V2-панели; Prometheus видит
`v2-client-facts` как `up`. Реальный Kafka-факт дал два спана в Collector,
одну трассу в Tempo и записи worker в Loki. Исправлены runtime-настройки
Tempo, Collector, Loki и Alloy. Не доказаны redaction на реальном секрете,
alerting, RBAC/backup, metric→trace→log→audit drill-down и Windows telemetry.

Checkpoint `CP-032` от `2026-09-28`: confirmed серверное событие V2
пополнения получило суммы по методам оплаты для будущей аналитики. В Windows
сообщение эти суммы и платёжные ссылки не передаются. Переводчик создаёт по
одному идемпотентному analytics outbox факту на метод оплаты и отвергает raw
client event. Есть отдельный логический inbox `confirmed_analytics` с
безопасным повтором. 6 проверок, Ruff и diff-check прошли; FastStream consumer
и PostgreSQL-граница ещё впереди.

Checkpoint `CP-033` от `2026-09-28`: запущен отдельный worker
`v2-confirmed-analytics`. Он принимает только server-confirmed факты из
`v2.confirmed-domain-events`, одной PostgreSQL-транзакцией пишет logical inbox
и analytics outbox и не меняет деньги, сессии либо пакетные права. Повтор
безопасен, а conflict и повреждённый/неподтверждённый факт перед offset commit
попадают в `v2.failed-events`. 6 focused-тестов, Ruff, Compose config и
diff-check прошли; живой Kafka → worker → PostgreSQL контур и Prometheus
`up = 1` подтверждены. Backfill/projection, расходование депозита и следующие
типы confirmed фактов остаются отдельной работой.

Checkpoint `CP-034` от `2026-09-28`: `scheduler` ставит read-only
`analytics-projection`, а новый `analytics-worker` обслуживает только
analytics queues. Он переносит immutable analytics outbox в projection и не
возвращает неиспользуемый результат Dramatiq. Живой Compose-путь Kafka →
confirmed analytics inbox/outbox → Dramatiq projection подтвердил появление
`analytics_projection_events`; 6 integration и 11 unit-проверок прошли.
Backfill, метрики расходования депозита и новые типы confirmed фактов ещё не
реализованы.

Checkpoint `CP-035` от `2026-09-28`: подтверждённый сервером
`PER_MINUTE_DEBIT` стал отдельным V2 analytics fact. В client payload теперь
обязательны `amount_cents` и `tariff_id`; старый `debit_delta_cents` сервер
отклоняет. После проверки lease/snapshot/цепочки сервер пишет public confirmed
event без локального остатка баланса. Analytics считает его как
`wallet_debit_cents`, не увеличивая доход или пополнение второй раз. Unit,
настоящая PostgreSQL и Compose Kafka → outbox → analytics → Dramatiq projection
проверки прошли. Не реализованы backfill и события package/session/refund/
correction; также требуется отдельная проверка Kafka-транспорта на реальном
Windows-ПК.

Checkpoint `CP-036` от `2026-09-28`: backfill V2-поминутных списаний стал
возобновляемым. PostgreSQL хранит историческую границу, cursor и durable skip;
одна транзакция восстанавливает только server-owned факт, пишет analytics
outbox и продвигает cursor. Legacy `debit_delta_cents` не угадывается и не
считается. Настоящая PostgreSQL-проверка подтвердила skip, resume и повтор без
второй метрики. Пересборка Docker-контейнеров с этим кодом пока не прошла из-за
недоступного Docker Hub; действующие контейнеры ещё не выполняют новый actor.

Checkpoint `CP-037` от `2026-09-28`: продуктовое решение заменило постепенную
миграцию атомарным V2 cutover. Поставляемый релиз не поддерживает V1 runtime,
feature flag, per-PC mode или fallback; PostgreSQL с бизнес-данными остаётся.
До удаления V1 нужен полный V2-сценарий. В тестовом cutover server flow
принудительно завершает active V1 sessions; автоматически переносить их в V2
запрещено.

Checkpoint `CP-038` от `2026-09-29`: Linux V2-клиент после входа получает
отдельный V2-снимок кабинета через `OfflineSessionService`, поэтому тарифы,
история, баланс и операции покупки больше не зависят от V1 portal RPC. Старый
компактный размер Linux developer host восстановлен: после входа используется
виджет 390×700, а содержимое кабинета прокручивается внутри него; Windows host
продолжает применять собственный native window adapter. Сценарий сброса пароля
теперь показывает ошибку прямо в форме, не очищает поля при неудаче и повторно
входит после успешного сохранения нового пароля.
Добавлена проверка gRPC-сценария входа, тарифного каталога и истории: backend
5 focused-тестов, C# client 91 тест, сборка Avalonia без предупреждений.
Контейнеры backend пересобраны, `/health/ready` подтверждает PostgreSQL/Redis.
Остаётся ручная проверка в новом Linux-клиенте: купить тариф с достаточным
балансом и открыть «История аккаунта»; автоматические тесты не подтверждают
раскладку элементов native-окна.

Checkpoint `CP-039` от `2026-09-30`: Linux Avalonia-клиент получил ранний
локальный журнал запуска с ротацией 2 МБ и переменной
`GAMECLUB_CLIENT_LOG_PATH`. В журнал попадают выбранные адреса V2, enrollment,
состояние подключения, вход, сброс пароля и gRPC-код/причина ошибки; пароли,
токены и содержимое авторизации не записываются. Проверены Linux-сборка без
предупреждений, 91 C# тест и реальный старт с созданием `/tmp/hubshell-client.log`.

Checkpoint `CP-040` от `2026-09-30`: по журналу Linux-входа найден зависший
активный V2 lease, связанный уже с завершённой серверной сессией. В тестовой
базе этот lease точечно отозван. Backend теперь переводит конфликт lease в
понятный gRPC-код `ALREADY_EXISTS`, а consumer факта `SESSION_STOPPED` в одной
транзакции завершает server session и отзывает lease. Backend gRPC и worker
пересобраны, `/health/ready` подтверждает PostgreSQL/Redis; ручной повтор входа
после обновления клиента ещё требуется.

Checkpoint `CP-041` от `2026-09-30`: устранена причина отклонения всех Linux
client facts. C# Protobuf-сериализатор больше не передаёт пустой
`optional previous_hash` у первого события: в proto3 это считалось бы
присутствующим значением и backend отклонял envelope как `invalid_envelope`,
после чего следующие sequence получали `reconciliation_gap`. Worker теперь
пишет в журнал точную причину invalid envelope и reconciliation rejection.
Добавлен регрессионный C# assertion для отсутствия `previous_hash` у первого
факта; 91 C# тест, 6 backend focused-тестов, Ruff и `git diff --check` прошли.
Реальные Kafka/worker контейнеры пересобраны и запущены; повторный ручной вход
и принятие первого факта новым session id ещё нужно подтвердить.

Checkpoint `CP-042` от `2026-09-30`: добавлен отдельный поведенческий набор из
33 тестов для расчёта времени, поминутного списания, пакетов, тарифных
ограничений и гостевых продаж. 22 C# теста проверяют V2 runner/ledger: пять
бесплатных минут, переход на поминутку, списание каждой due-minute, задержку и
повторный tick, откат часов, лимит долга, exhaustion, приоритет пакета,
покупку/идемпотентность и early exit. 11 Python-тестов проверяют гостевые
наличные/безналичные и смешанные платежи, идемпотентность, аудит границ
количества, аудиторию, канал продажи, зону, занятую станцию и кассовую смену.
Полный C# набор прошёл `113` тестов, backend-срез поминутки/каталога — `53`,
новый гостевой файл — `11`. В ручной Linux-сессии
`582467e4-6726-4d5a-8c09-0b69e00b90f0` сервер принял sequence 1–9: пять
`login_grant_consumed`, три `per_minute_debit` по 100 копеек и
`session_stopped` после нулевого баланса; lease отозвана после завершения.

## 2. Назначение и границы продукта

GameClub / HUBSHELL — операторская система игрового клуба: карта мест и состояние ПК,
клиенты и гости, бронирования, игровые сессии, тарифы, продажи, касса,
аналитика и Windows-клиент рабочего места.

Сейчас это **модульный асинхронный монолит backend**, а не набор отдельных
микросервисов. Границы модулей и публичные application-порты оставлены так,
чтобы выделение сервиса позже было возможным, но преждевременное дробление не
делается.

Основные внешние поверхности:

| Потребитель | Транспорт | Назначение |
| --- | --- | --- |
| Browser/operator UI | HTTP JSON через FastAPI BFF | dashboard, карта, CRM, каталог, продажи, касса, настройки, аналитика |
| Windows client | gRPC + Protobuf | MAC enrollment, device auth, heartbeat, команды, user portal, подтверждённый выход и session gateway |
| Background workers | Dramatiq/Redis | billing reconciliation, reservation no-show, кассовое расписание |
| PostgreSQL/Redis | infrastructure adapters | долговременные факты/настройки и технический кэш/брокер |

Сравнение с обязательными продуктовыми контрактами выполнено и оформлено в
[`plans/29-contract-alignment/PLAN.md`](29-contract-alignment/PLAN.md). Текущий
срез добавляет durable entitlement queue и consumption с окнами/auto-next,
device login-grant, payment parts, guest paid-start prerequisite, entry
decision, one-active-client guard, session snapshot, transfer, offline replay,
durable settlement retry/audit и portal/Avalonia queue activation. В качестве
следующего архитектурного решения зафиксирован Avalonia как единственный
Windows UI production path: Linux становится development-host для
build/run/test, тогда как Windows остаётся производственной платформой и
финальной platform-smoke границей. Историческая миграция описана в
[`plans/38-avalonia-linux-first`](38-avalonia-linux-first/PLAN.md). Полное
контрактное закрытие ещё не достигнуто: открыты production cross-owner UoW/
provider policy, полная browser/accessibility matrix и native Windows evidence.
Остаток нарезан на планы
[`30–34`](30-entitlements-meter/PLAN.md), [`35`](35-frontend-contract-consumers/PLAN.md),
[`36`](36-windows-client-contract-consumers/PLAN.md), [`37`](37-platform-integration-evidence/PLAN.md)
и [`38`](38-avalonia-linux-first/PLAN.md). Локальный development-only инструмент
для Figma authoring описан отдельно в
[`39-figma-local-bridge`](39-figma-local-bridge/PLAN.md): он не входит в
runtime Windows-клиента и не служит доказательством Figma cloud-access.

## 3. Карта репозитория

| Путь | Что находится внутри | Роль |
| --- | --- | --- |
| [`backend/`](../backend/) | Python-приложение, модули, миграции, proto, тесты | API, бизнес-правила и инфраструктура |
| [`backend/src/gameclub_backend/`](../backend/src/gameclub_backend/) | composition root, application, modules, jobs, HTTP/gRPC | реализация backend |
| [`backend/src/gameclub_backend/modules/`](../backend/src/gameclub_backend/modules/) | bounded contexts | домен, use cases, repositories, handlers |
| [`backend/proto/gameclub/v1/`](../backend/proto/gameclub/v1/) | source-of-truth `.proto` | native gRPC-контракты |
| [`backend/alembic/versions/`](../backend/alembic/versions/) | миграции `0001`…`0061` | схема PostgreSQL; локальная команда `uv run --directory ./backend alembic heads` на 2026-09-20 показывает `20260918_0061` |
| [`backend/tests/`](../backend/tests/) | unit, API, contract, jobs, PostgreSQL checks | автоматические проверки backend |
| [`frontend/`](../frontend/) | React/Vite-приложение и nginx image | операторская web-оболочка |
| [`frontend/src/app/`](../frontend/src/app/) | композиция App, shell, PanelHost, Redux store/hooks и API facade | UI orchestration и серверный state boundary |
| [`frontend/src/features/`](../frontend/src/features/) | feature-экраны и контекстные панели operator UI | локальный UI-flow по bounded feature-модулям |
| [`frontend/src/api/`](../frontend/src/api/) | DTO, HTTP API client и нормализаторы | typed API boundary; вызовы экранов проходят через Redux facade |
| [`frontend/src/styles/`](../frontend/src/styles/) | каскад operator UI, разложенный по тематическим блокам | сохранённый порядок CSS-правил |
| [`win-client/`](../win-client/) | Linux-first Core/Avalonia solution, Windows production adapters, scripts, tests | клиент игрового ПК |
| [`win-client/src/GameClub.Client/`](../win-client/src/GameClub.Client/) | Domain/Application/Infrastructure/Presentation | Windows implementation |
| [`win-client/src/GameClub.Client.Core/`](../win-client/src/GameClub.Client.Core/) | portable Domain/Application/ports, safe infrastructure helpers and shared `MainViewModel` | `net8.0` migration core |
| [`win-client/src/GameClub.Client.Avalonia/`](../win-client/src/GameClub.Client.Avalonia/) | shared Avalonia App/MainWindow, resources and Linux developer host | Avalonia `11.3.2` UI host |
| [`win-client/src/GameClub.Client.Windows/`](../win-client/src/GameClub.Client.Windows/) | Windows production composition for the shared Avalonia window | DPAPI/restart/command plus fullscreen/widget/tray adapters; native smoke remains open |
| [`plans/README.md`](README.md) | общий индекс и зависимости | навигация по планам |
| [`plans/`](./) | детальные планы backend-модулей, Windows-lockdown и связанные контракты | единое хранилище implementation-планов |

Ранее в корне существовали пустые каталоги `plans/00-foundation`…
`plans/06-win-client`, а фактические backend-планы находились в `backend/plans/`.
Теперь детальные планы перенесены в корневой `plans/`; старые пустые каталоги
удалены. `backend/PLAN.md`, `frontend/PLAN.md` и `win-client/PLAN.md` остаются
короткими owner-level входами без копирования детальных implementation-планов.

## 4. Технологический стек

### Backend

- Python `>=3.12,<3.13` и `uv`;
- FastAPI + Uvicorn — HTTP/BFF и health endpoints;
- gRPC `grpcio` + Protocol Buffers — native/internal transport;
- SQLAlchemy async + `asyncpg` — PostgreSQL access;
- Alembic — migrations;
- PostgreSQL `16-alpine` — источник истины бизнес-фактов;
- Redis `7-alpine` — Dramatiq broker, refresh-token storage и технический cache;
- Dramatiq — фоновые/retry-задачи;
- FastStream поверх Kafka — V2 publisher/consumer для событий автономной
  сессии; процесс и Kafka-инфраструктура пока не развернуты;
- PyJWT — JWT access/refresh/device tokens;
- Pydantic Settings — конфигурация через `GAMECLUB_*`;
- pytest/pytest-asyncio/httpx — тесты; Ruff — lint и форматирование.

Основные ограничения зависимостей и версии находятся в
[`backend/pyproject.toml`](../backend/pyproject.toml). В domain нельзя импортировать
FastAPI, PostgreSQL, Redis, gRPC или Dramatiq; application работает через
`typing.Protocol`, SQL остаётся в infrastructure.

### Frontend

- React `19.1.x` + ReactDOM;
- TypeScript `5.9.x`;
- Vite `7.1.x`;
- Tailwind CSS `4.1.x` через `@tailwindcss/vite`;
- Lucide React `0.468.x`;
- Node `22-alpine` для build image;
- nginx `1.27-alpine` для раздачи и proxy `/api`.

### Windows client

- C# / .NET `8`;
- текущая production реализация: Avalonia `11.3.2`, shared Core/Tests и Windows
  production composition на
  `net8.0` собираются с SDK `8.0.425` в Linux; Windows-only adapters
  изолированы в `GameClub.Client.Windows` и публикуются только для `win-*`;
- минимальная Windows deployment ОС сохраняется Windows 10 build `17763`;
- `Grpc.Net.Client 2.66.0`, `Google.Protobuf 3.28.2`, `Grpc.Tools 2.66.0`;
- x86, x64 и ARM64; тестовый проект сейчас рассчитан на x64;
- xUnit и Microsoft.NET.Test.Sdk для unit-тестов.

### Локальная инфраструктура

Корневой [`docker-compose.yml`](../docker-compose.yml) поднимает:

`postgres:5432` → `redis:6379` → `backend-migrate` → `backend-http:8100`,
`backend-grpc:51051`, `worker`, `scheduler` и `frontend:80`. По умолчанию на
host опубликованы frontend `3100`, HTTP `8100`, gRPC `51051`, PostgreSQL `55432`
и Redis `56379`; значения можно переопределить через `.env`.

Frontend image проксирует `/api` в `backend-http`. Windows-клиент подключается к
опубликованному host-порту gRPC, а не к Docker-имени `backend-grpc`.

## 5. Архитектура и потоки

```text
Browser
  -> host :3100 -> frontend/nginx :80
  -> /api -> backend-http/FastAPI :8100
  -> application use case / public module port
  -> PostgreSQL (facts, ledgers, settings) + Redis (technical state/cache)

Windows client
  -> configured host gRPC endpoint :51051
  -> auth metadata / device identity
  -> Workstation, Session, Catalog, Reservation, Billing, Analytics services

scheduler -> Dramatiq/Redis broker -> worker -> reservation/billing/cash jobs
```

Слои backend: `presentation` переводит HTTP/gRPC в команды, `application`
оркестрирует use case и транзакционные границы, `domain` содержит правила,
`infrastructure` содержит PostgreSQL/Redis/JWT/broker adapters.

Ключевые правила:

- frontend не подключается к PostgreSQL, Redis или внутренним gRPC-портам;
- backend-модули не читают сырые таблицы друг друга;
- Redis не является источником истины денег, продаж, сессий или настроек;
- деньги — integer cents, без `float`, с ledger/snapshot и автором операции;
- изменяющие и финансовые операции защищаются idempotency key, audit и явным
  подтверждением;
- на одном ПК допускается только одна active session;
- reservation владеет бронью, Sessions — фактом игры, Catalog — тарифом,
  Billing — charge, Clients — профилем и balance ledger, Cash Shifts — наличным
  ledger, Sales — фактом продажи, Analytics — read-only агрегациями;
- Windows получает только allowlisted команды и темы; произвольные shell/system
  commands запрещены.

## 6. Backend: фактические модули

Код всех модулей находится в
[`backend/src/gameclub_backend/modules/`](../backend/src/gameclub_backend/modules/).
HTTP handlers находятся рядом с модулем в `presentation/http.py`, а сборка
зависимостей выполняется в
[`presentation/http/app.py`](../backend/src/gameclub_backend/presentation/http/app.py).

| Модуль | Что уже есть | Контракт / следующий шаг |
| --- | --- | --- |
| Foundation | async app, config, health, resources, error contract, audit, migrations, generated proto | план помечен `in_progress`; закрыть интеграционные и deployment-вопросы |
| Auth/Security | JWT access/refresh/logout, hash refresh storage, permissions, audit, gRPC auth/TLS policy, dev device bootstrap | production enrollment hardening, token/key rotation, secret storage и внешняя TLS-конфигурация |
| Workstations | registration по device/MAC, heartbeat, stale/offline state, groups/zones, themes, commands, ACK, expiry, lockdown policy, manager verifier, management CRUD, installation binding | rebind policy/rate limit и native kiosk checks |
| Clients/Guests | client CRUD/search, canonical phone, balance ledger/top-up, discount category/password flow, server portal registration/login, password reset with one-time passwordless login and forced change, client-scoped JWT и истории; guest profile без balance и guest links | production credential rotation |
| Client groups | contract boundary для группы клиента, default group, settings CRUD и allow-negative/negative-limit policy | implementation есть; DSN migration/live сценарий и production audit evidence остаются по плану 44 |
| Catalog/Time/Tariffs | categories, products, stock/purchase cost, tariff lifecycle, `block`/`per_minute`, discounts, quote, snapshot, publish/archive, daily sale/usage windows, `time_restricted`, audience/channel filtering and entitlement snapshot | next-compatible auto-start и broader production/browser/native evidence; F-10 operator-only guest sale implementation есть в [`plans/44-fixes-features`](44-fixes-features/PLAN.md) |
| Reservations | availability preflight, conflict protection, lifecycle, multi-resource create, client/guest, async no-show sweep, HTTP/gRPC/timeline support, server `CheckEntry` with 30-minute lock | Avalonia/operator decision consumer and PostgreSQL concurrency matrix |
| Sessions | active/completed lifecycle, start/get/list/stop/interrupt, workstation lock, idempotency, device gateway, tariff quantity, meter integration with package fallback, остановкой по окончании бесплатных минут без денег или ставки и insufficient-balance stop, entitlement consumption/auto-next, one active client guard, guest payment link, login grant и server-backed session snapshot с time notifications; фоновое списание загружает правила клиентской группы для лимита долга | stop acknowledgement/access-gate/restart sequence, PostgreSQL package/debit UoW, transfer concurrency и heartbeat/native evidence остаются отдельной границей |
| Billing | completed-session charge, quote/financial snapshot, atomic balance debit, bounded group debt policy, reconciliation record/retry, metered billing with login-grant subtraction, entitlement mixed payment parts and durable settlement review/retry | automatic mixed-payment rollback, DSN concurrency и provider settlement остаются; bonus/refund/reserve/external finance — отдельный backlog |
| Reports/Dashboard | read-only current revenue/dashboard data and audit-backed activity | расширенные reports/read models по нагрузке |
| Cash Shifts | open/close, cash ledger, movements, references, approvals, schedules, provider-neutral producer boundary | реальные provider/webhook producers и отдельные finance integrations |
| Product Sales | client/guest sale, stock reservation, price/cost/category snapshots, balance/cash settlement boundary, mixed payment parts, idempotency, HTTP API | atomic cross-part reconciliation, basket/order, returns, bonuses, external acquirer |
| Notifications | notification rules CRUD, thresholds, stable event id, session snapshot/HTTP/gRPC transport, frontend settings editor, Win Core deduplication and Windows sound/balloon adapter | native Windows audio/toast smoke and folder-package permission checks остаются |
| Analytics | read-only overview/client analytics, daily/hourly dynamics, occupancy, zones/PC/tariffs/payment methods, margin, segments, CSV и gRPC read contract; модернизация по `stats.md` спроектирована в [`plans/11-analytics/PLAN.md`](11-analytics/PLAN.md) и [`METRICS-DICTIONARY.md`](11-analytics/METRICS-DICTIONARY.md) | финансовые факты Payment/Wallet/Revenue, retention/cohorts, deposit aging, profitability, period comparison, drill-down, фоновые отчёты и heavy projections |
| Payment Methods | CRUD `/api/v1/payment-methods`, validation, PostgreSQL repository, migration seeds `balance`/`cash`/`transfer`, settings UI | provider activation/settlement integrations добавляются отдельно |

### HTTP BFF surface

Основные prefixes: `/api/v1/auth`, `/workstations`, `/workstation-groups`,
`/clients`, `/guests`, `/catalog`, `/reservations`, `/sessions`, `/billing`,
`/cash-shifts`, `/sales`, `/analytics`, `/payment-methods`, `/client-groups`,
`/notification-rules`, `/audit`.

Для browser это единственная бизнес-точка входа. Защищённые use case повторно
проверяют permissions независимо от видимости кнопок во frontend. В частности,
`settings.manage` нужен для payment methods и настроек групп, `analytics.read` —
для аналитики, а финансовые действия имеют отдельные права/approval boundary.

### gRPC source of truth

В [`backend/proto/gameclub/v1/`](../backend/proto/gameclub/v1/) определены:

`SystemService`, `WorkstationService`, `ClientService`, `ClientPortalService`, `CatalogService`,
`ReservationService`, `SessionService`, `BillingService`, `CashShiftService` и
`AnalyticsService`. На runtime endpoint публично регистрируются только
`SystemService`, `WorkstationService`, `ClientPortalService`, `ReservationService`
и `SessionService`; операторские CRUD/read-сервисы остаются HTTP BFF-контуром.

Generated Python находится в `backend/src/gameclub/v1/`, а C# project напрямую
подключает исходные `.proto`. Payment Methods и Product Sales в текущем срезе
имеют HTTP BFF-контракт; отдельного protobuf service для них нет.

### Background jobs

- `jobs/reservations.py` — no-show/sweep;
- `jobs/billing.py` — reconciliation и связанные billing retries;
- `jobs/cash_shifts.py` — расписания кассовых смен;
- `jobs/scheduler.py` — периодическая постановка задач.

Для каждой фоновой операции важны retry, идемпотентность, timeout и понятное
поведение после окончательной ошибки.

## 7. Frontend: операторская оболочка

Frontend разделён на композиционный слой `frontend/src/app/`, feature-модули
экранов и панелей в `frontend/src/features/`, typed API boundary в
`frontend/src/api/`, адаптеры/mock data и переиспользуемые shared-компоненты.
`frontend/src/App.tsx` оставлен тонким re-export для совместимости, а
`frontend/src/app/App.tsx` содержит только auth-gate и композицию shell.
Redux Toolkit агрегирует auth, workspace и UI-контекст; API facade отправляет
асинхронные операции через thunk, поэтому screen components не создают API-клиент.
CSS сохранён в исходном каскадном порядке, но разбит на файлы в `frontend/src/styles/`.

Реализованные области:

- тёмный shell с постоянной навигацией, topbar, статусом соединения и доступными
  keyboard/focus/error states;
- dashboard и spatial map как главный workspace;
- карта с фиксированной карточкой места `112x84px`, восемью колонками,
  внутренним scroll-frame и отдельной легендой/панелью; grid не зависит от
  ширины окна так, как прежняя fluid-сетка;
- polling карты и операционных данных с целевой задержкой до 5 секунд; backend snapshot cache
  в Redis — ключ `gameclub:workstations:snapshot:v2`, bounded TTL 20 секунд;
  кэш сохраняет `session_mode`, а новая версия ключа отбрасывает снимки старого формата;
- карта/панель ПК с V2-командами блокировки и перезапуска; исторические V1-сессии
  доступны только для чтения. Панель фиксирует режим активной сессии, не
  переключает набор команд при polling и содержит одну точку входа в продажу;
- причина чередования V1/V2 в панели была в Redis snapshot cache без `session_mode`;
  новый формат сохраняет поле и использует новый ключ. Migration `20261002_0071`
  переводит оставшиеся строки PostgreSQL в V2, но откажется идти дальше при
  активной V1-сессии до подтверждённого cutover;
- сохранение session/product idempotency keys в рамках одной попытки checkout,
  чтобы повторный запрос не создавал вторую сессию или второе списание;
- один retry через refresh token для BFF `401/403`; stale operator permissions
  восстанавливаются dev-refresh до выпуска нового access token;
- CRM, debounce-поиск от 3 символов ника или 4 цифр телефона, canonical phone,
  top-up и просмотр balance ledger;
- каталог: категории, товары, остатки, закупочная цена, draft/publish/archive
  тарифы и discount rules;
- reservations timeline, availability preflight и conflict states;
- кассовые смены, движения, approvals для correction/close discrepancy;
- настройки зон/ПК/тем Windows и CRUD способов оплаты: добавить, изменить,
  деактивировать или удалить;
- аналитика с отдельными отчётами «Обзор», «Посещаемость», «Занятость» и
  «Продажи»; выбор периода, фильтры, сравнение и экспорт CSV. Графики показывают
  выручку по дням, посещаемость по дням и игровое время по часам; таблицы — места,
  залы, товары, оплаты и клиентов. Признанный доход и пополнения депозита берутся
  из v2 финансового отчёта; сервис передаёт выбранный период в хранилище, а
  списания с баланса не добавляются к выручке повторно.

Бизнес-расчёты и финансовая истина не дублируются в React. Frontend отображает
ответы BFF и управляет operator flow; окончательные проверки конфликтов,
permissions, баланса, stock и идемпотентности выполняются backend.

Отложено на стороне frontend: полноценный realtime transport, расширенная
browser/device matrix, order checkout для смешанных тарифов сверх базовой
entitlement queue, production-scale UI для тяжёлых отчётов и native Windows
flows.

## 8. Windows client

Основной проект: [`win-client/src/GameClub.Client/`](../win-client/src/GameClub.Client/).

| Слой | Содержимое |
| --- | --- |
| `Domain` | connection state, heartbeat, command/session snapshots, lockdown policy |
| `Application` | access-gate и session coordinators, ports для backend/token/executor |
| `Infrastructure` | gRPC adapter, bearer metadata, health, enrollment, token storage, Windows command/power adapters, endpoint policy |
| `Presentation` | portable `MainViewModel` and Avalonia bindings; Avalonia `MainWindow` contains access-gate, manager, portal/session, tariffs, transfer, history and booking surfaces |
| `tests` | Linux: access-gate, session coordinator, password verifier, endpoint policy и Avalonia headless smoke; Windows adapters проверяются отдельным native smoke |

Уже реализовано в source-level срезе:

- borderless fullscreen locked gate; после авторизации compact borderless
  widget, always-on-top и hide/show tray button;
- MAC enrollment, installation identity в AppData, device JWT и bearer metadata;
- server-streaming command receiver с `expires_at`, ACK/NACK, reconnect backoff
  и ограниченным in-memory duplicate guard;
- allowlist `display.lock`, `theme.apply`, `session.start/stop` и структурный
  payload; произвольные shell-команды не принимаются;
- группы передают theme key через heartbeat; неизвестная тема возвращается к
  `standard`;
- locked startup/access-gate, manager maintenance через отдельный credential и
  локальный `Ctrl+Alt+P` route на сфокусированном access-gate, idle relock,
  relock при auth 401/403;
- manager shortcut открывает только password form, а успешная проверка переводит
  в maintenance без пользовательской сессии; session locked/zero-balance handling
  и controlled restart после подтверждённого stop;
- план [`43-manager-maintenance-hotkey`](43-manager-maintenance-hotkey/PLAN.md)
  добавляет локальный `Ctrl+Alt+P` route: shortcut открывает только manager
  password form на сфокусированном Locked gate; OS shell disable остаётся
  отдельным native Windows/policy этапом.
- deployment/publish/kiosk preview scripts с backup/restore и явным `-Apply`;
  `build-portable-exe.ps1` собирает single-file self-contained EXE с заранее
  зашитыми non-secret HTTP/HTTPS endpoint metadata для передачи на клиентский ПК;
  закрытая private LAN допускает HTTP без белого IP.
- server-backed register/login/profile/history screen показывает баланс,
  операции, списания времени, товары, тарифы/сессии и доступное время; portal
  snapshot теперь передаёт ordered package queue, explicit activation RPC/UI,
  каталог тарифов для подтверждённой покупки и будущие подтверждённые брони
  клиента для текущего места;
- операторский сброс пароля очищает старый hash без генерации временного
  секрета; сброшенный аккаунт входит без пароля только до обязательной смены
  пароля в Avalonia-клиенте с повтором и серверным подтверждением.

Windows-клиент не хранит баланс и не выполняет финансовые операции. Сервер
остаётся источником истины сессии и billing.

Не закрыто: cross-owner settlement/reconciliation UoW и fault-injection matrix,
production hardening enrollment/rebind/token rotation, native
`dotnet restore/build/test`, запуск под обычным пользователем, реальный
reconnect/theme/restart smoke и Assigned Access/Shell Launcher с ограничением
Explorer/Alt+Tab/других приложений. App-level lock не считается заменой Windows
security boundary. Каноническая матрица профилей и rollback — в
[`plans/22-windows-lockdown/POLICY.md`](22-windows-lockdown/POLICY.md); детали
evidence — в
[`win-client/docs/SUPPORT-MATRIX.md`](../win-client/docs/SUPPORT-MATRIX.md) и
[`plans/29-contract-alignment/PLAN.md`](29-contract-alignment/PLAN.md).

## 9. История сделанных срезов

Последовательность работы, зафиксированная планами и кодом:

1. Foundation: async backend, config, health, error/status conventions,
   repositories, migrations, generated protobuf и Compose.
2. Auth/Security: JWT access/refresh/logout, permissions, audit, gRPC auth/TLS
   policy и dev bootstrap для device.
3. Workstations: регистрация/heartbeat, состояние ПК, команды, группы, темы,
   management и lockdown policy.
4. Clients/Catalog/Reservations: профили, guests, canonical phone, ledger,
   товары/категории/остатки, тарифы/discounts, quote, бронирования и timeline.
5. Sessions/Billing: фактический lifecycle `active -> completed`, locks,
   idempotency, interrupt, charge snapshot, debit и reconciliation.
6. Cash Shifts: отдельный наличный ledger, approvals, schedules и producer
   boundary без смешивания с клиентским balance.
7. Operator redesign: единый dark shell, spatial map, sliding panels, checkout,
   CRM, catalog, cash desk и live BFF flows.
8. Product Sales/Analytics: товарные продажи со stock/settlement snapshots и
   read-only analytics по завершённым sessions, charges и sales.
9. Live metered billing: per-minute delta, grace minutes, insufficient-balance
   stop и sequential block quantity.
   - Исправлен общий Dramatiq broker для job actors; live metering вынесен в
     отдельную очередь и worker, чтобы billing retry backlog не блокировал
     списание активных сессий.
   - Исправлена проверка промежуточного списания: метр проверяет только новую
     дельту, сохраняет дробные секунды между тиками и не закрывает длинную
     сессию при достаточном балансе; добавлены подробные данные в журнал отказа
     списания и регрессии для длинных/последовательных сессий.
10. Последний прикладной срез по запросам пользователя:
    - исправлены fixed-size map cards, отдельный scroll-frame и короткий polling карты;
    - добавлен Redis snapshot cache с TTL 20 s;
    - checkout защищён от повторного session/product submit;
    - stale permissions при BFF `403` обновляются через refresh;
    - в Settings добавлен CRUD payment methods;
    - analytics BFF/live flow проверен после исправления authorization path.
11. Deployment-подготовка Windows-клиента:
    - внешние host-порты Compose разделены с системными default-портами;
    - добавлен unpackaged single-file self-contained publish для одного EXE;
    - endpoint defaults клиента синхронизированы с новым HTTP/gRPC-профилем.
12. Автоматическое подключение и user portal:
    - MAC enrollment с installation binding, `pending/approved/disabled` и
      миграциями `0032/0033`;
    - `ClientPortalService` в gRPC с device-scoped registration/login и
      client-scoped JWT, histories и available time;
    - Avalonia pre-auth fullscreen gate и server-backed login/register/profile/history;
    - portable publish получил baked HTTP/HTTPS endpoint parameters и не требует
      env/bootstrap/token setup на игровом ПК.
    - enrollment получает понятный rejected-state при конфликте installation id;
      уже привязанное место нельзя случайно изменить на другой MAC без отдельной
      rebind-операции.
    - добавлен in-process gRPC smoke для portal registration/snapshot с проверкой
      client/device scope.
    - portal login/register теперь создаёт server-backed active session на текущем
      ПК; Avalonia-клиент и карта администратора получают snapshot через короткие циклы
      gRPC/HTTP polling, WebSocket для MVP не вводился.
    - password reset flow не возвращает временный пароль и переводит Avalonia-клиент в
      обязательную форму установки нового пароля.
13. Восстановление после restart/reconnect и зональные тарифы:
    - heartbeat возвращает active session snapshot, а device-authenticated
      `ClientPortalService.Resume` восстанавливает именованный portal session
      без хранения клиентского пароля или portal token на диске;
    - global tariffs и tariffs текущей workstation zone выдаются в Win portal
      и operator sale checkout; backend дополнительно блокирует несовместимые
      session start и guest payment;
    - source/unit/API/gRPC/frontend проверки прошли, native Windows
      restart/reconnect smoke остаётся отдельной границей плана 41.

Детальные задачи и решения: [`plans/README.md`](README.md) и таблица
проверок ниже. В README есть небольшое расхождение: Product Sales уже имеет
`plans/10-product-sales/PLAN.md` со статусом `done`; индекс обновлён и больше
не использует старый путь `backend/plans/`. Для фактического доказательства
приоритет у кода, детального плана и `VERIFICATION.md`.

## 10. Чекапы и границы доказательства

### Уже выполнено на текущем checkout

| Чекап | Результат | Что именно доказывает |
| --- | --- | --- |
| `uv run --directory ./backend pytest -q` | `174 passed, 19 skipped` без `GAMECLUB_TEST_POSTGRES_DSN` на срезе 2026-09-17; PostgreSQL suites пропускаются без DSN | unit/API/contract/jobs, включая groups/debt, sale channel, mixed entitlement payment, durable entitlement reconciliation, notification snapshot transport, sale/usage windows and protobuf/gRPC contracts |
| `uv run --directory ./backend pytest -q -m "not integration and not slow"` | `153 passed, 18 deselected` на срезе 2026-09-16 | явный offline/release-safe прогон без инфраструктурных suites |
| `uv run --directory ./backend pytest -q -m "api or contract"` | `41 passed, 138 deselected` на срезе 2026-09-17 | отдельная проверка HTTP/gRPC/protobuf boundaries, включая tariff audience/window contracts |
| `uv run --directory ./backend ruff check .` | успешно (повторено 2026-09-02) | lint backend |
| `uv run --directory ./backend ruff format --check <затронутые Python-файлы>` | успешно | форматирование текущего среза; полный checkout дополнительно содержит 2 старых неформатированных файла |
| `npm --prefix ./frontend run typecheck` | успешно (повторено 2026-09-15) | TypeScript compile/type boundary; Redux workspace snapshot и stale-response guards |
| `npm --prefix ./frontend run lint` | успешно (2026-09-15) | noUnusedLocals/noUnusedParameters TypeScript boundary |
| `npm --prefix ./frontend run build` | успешно на срезе 2026-09-15 | TypeScript build и production Vite build, включая zone-scoped tariff requests |
| `npm --prefix ./frontend run test` | `25 passed` на срезе 2026-09-17 | Vitest API boundary плюс component/accessibility slice для login, map/tooltip, sale/payment parts, deposit recipient confirmation, booking, offline-routing, confirmation и settings resources; browser visual/realtime matrix ещё не закрыта |
| `npm --prefix ./frontend run test:coverage` | `19 passed`; line coverage `17.18%`, guardrail `17%` | первый измеренный frontend baseline; coverage не заменяет behavior/accessibility tests |
| `uv run --directory ./backend pytest --cov=src/gameclub_backend --cov-report=term-missing` | `154 passed, 18 skipped`; line coverage `70.10%`, guardrail `70%` | первый измеренный backend baseline без DSN; integration coverage не доказана |
| `docker compose config --quiet` | успешно | Compose syntax/config |
| `docker compose up -d --build` | исторически успешно в прогоне 2026-09-02 | backend stack тогда был пересобран/restarted; PostgreSQL/Redis/HTTP/gRPC/frontend healthy, migration head `20260902_0048`, HTTP и gRPC smoke прошли; после новых миграций этот Compose-чек нужно повторить; native Windows client в compose не входит |
| Изолированный PostgreSQL test stack | `docker-compose.postgres-test.yml`, `scripts/prepare-postgres-test.sh`, `scripts/run-postgres-tests.sh`; контейнер `hubshell-test-postgres` на `127.0.0.1:55434`, Alembic head `20260918_0061`, repeatable seed | проверено 2026-09-21: полный backend с `GAMECLUB_TEST_POSTGRES_DSN` — `234 passed`; PostgreSQL marker run — `21 passed, 213 deselected`; повторный seed не создаёт дубли | это отдельная локальная test-база; Redis-тесты требуют отдельного `GAMECLUB_TEST_REDIS_URL`, production backup policy не доказывается |
| Backend static quality | `uv run --directory ./backend ruff check .`, `ruff format --check src tests alembic/versions`, `mypy src tests` | проверено 2026-09-21: все проверки успешны; mypy без ошибок в `253` файлах, форматирование `314` файлов | статические проверки не заменяют browser, Redis, Compose и native Windows evidence |
| live `POST /api/v1/auth/device-enrollment` без назначенного MAC | `202 pending` | опубликованный BFF enrollment route и безопасный ответ без device/operator token |
| Linux enrollment после Compose restart | успешно | клиент ограничил список MAC до 16 адресов, получил `200 approved`, а операторская карта получила свежий heartbeat `Avalonia Linux smoke`; native Windows-ПК этой проверкой не покрыт |
| Live HTTP smoke | успешно | fresh operator token, `/auth/me`, payment methods, analytics 200, sales 200, auth-aware error path |
| Redis cache smoke | TTL около `16 s` сразу после чтения | cache key created with bounded 20 s TTL; Redis не заменяет DB |
| Playwright headed smoke | частично успешно | login, dashboard/map/PC context, bookings, clients, catalog sale confirmation, analytics, cash, settings, offline heartbeat lock и disabled sale/booking actions; полная contract/browser matrix ещё не закрыта |
| Product/catalog smoke | `PUT` существующего товара → `200` | regression after backend rebuild |

### Чеки, которые ещё нужны

| Направление | Почему не закрыто |
| --- | --- |
| PostgreSQL integration/concurrency | без DSN 18 тестов пропускаются; при dev DSN все 157 backend-тестов проходят, включая package/transfer/offline/settlement mixed-fault evidence; production cross-owner UoW/provider policy остаётся открытой |
| Avalonia migration | Core/Avalonia/tests Linux solution собрана SDK `8.0.425`: Debug build без warnings, `34 passed`; `win-x64` framework-dependent artifact собран cross-publish. `MainViewModel` emitted only из portable Core; access-gate и portal перенесены |
| Windows native | `GameClub.Client.Windows.sln` ведёт на Avalonia production host; Linux source build без warnings и self-contained `win-x64` folder-publish создаёт PE GUI artifact с `hostfxr.dll`. DPAPI, restart/power, command stream, fullscreen/скруглённый compact widget и native tray изолированы в Windows adapter; Windows runtime и kiosk evidence остаются обязательны |
| Kiosk security | `NoRun=1` provisioning доступен только как optional full-kiosk profile; базовый `app_gate` возвращает `Win+R` после входа. Assigned Access/Shell Launcher, обычный пользователь, edition, Explorer/Alt+Tab, recovery и restore требуют целевой Windows-машины |
| Browser matrix/realtime | подтверждён локальный headed smoke основных routes и offline/confirmation guards; полноценный набор браузеров, queue/entry/transfer/guest/error/accessibility matrix и realtime transport не выполнялись |
| Production security | нужны real secret storage, enrollment rate-limit/rebind, backups и deployment policy; TLS/mTLS certificates обязательны только при внешнем доступе |
| Heavy analytics | текущий overview/client/CSV синхронный read model; финансовое разделение Payment/Wallet/Revenue и расширенные показатели из `stats.md` требуют отдельных вертикальных срезов; фоновые отчёты с retry/status/file ещё не сделаны |

## 11. Следующие задачи

### P0 — тестовый контур

Выполняется план [`42-test-overhaul`](42-test-overhaul/PLAN.md): backend сохраняет
рабочий unit/API/contract слой, устаревшие source-level assertions обновлены,
крупные test modules разделены по bounded context, а русские behavior-docstring
закреплены convention guard-тестом. Для backend добавлены явные unit/API/contract
и PostgreSQL/Redis/concurrency markers с offline-командами. Frontend получил
Vitest foundation; C# Linux-runnable solution восстановила компиляцию после
Avalonia-миграции. Открыты browser visual/realtime, DSN и native Windows gates;
coverage guardrail установлен на измеренном старте.

### P0 — доказать текущий MVP

0. Завершить [`план 40`](40-avalonia-product-flows/PLAN.md): interaction-level
   UI tests и native Windows publish/run tray/window/kiosk smoke.
   Linux Core/Avalonia build/test/run и `win-x64` cross-compile artifact уже
   получены; это не Windows runtime proof.

1. Repo-side задачи планов [`30`](30-entitlements-meter/PLAN.md)–[`36`](36-windows-client-contract-consumers/PLAN.md)
   закрыты доступными source/unit/API/visual checks; native/runtime границы
   остаются явно отмеченными в [`37`](37-platform-integration-evidence/PLAN.md)
   и его evidence report.

2. На целевой Windows-машине выполнить native verification и kiosk rehearsal;
   локальный backend suite с dev PostgreSQL/Redis уже прошёл: `157 passed`.
2. На Windows выполнить:

   ```powershell
   Set-Location "C:\Git\HubShell"
   .\win-client\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
   ```

   После этого вручную проверить access-gate, обычного пользователя,
   reconnect, theme, session stop/restart и отсутствие секретов в файлах/логах.
   Для передачи на клиентский ПК собрать portable-файл:

   ```powershell
   Set-Location "C:\Git\HubShell"
   $authAddress = Read-Host "Production AuthAddress (http://private-LAN или https://external)"
   $grpcAddress = Read-Host "Production GrpcAddress (http://private-LAN или https://external)"
   .\win-client\scripts\build-portable-exe.ps1 `
     -Architecture x64 `
     -Configuration Release `
     -EnvironmentName production `
     -AuthAddress $authAddress `
     -GrpcAddress $grpcAddress
   ```
3. Проверить основной browser flow в поддерживаемых браузерах и определить
   порог нагрузки/частоту polling; при необходимости перейти от polling к
   согласованному realtime transport.
4. Реализовать плановую задачу Analytics по background reports через Dramatiq:
   status, retry, хранение результата и безопасная выдача файла.
5. Выполнить ручной Figma Desktop setup плана
   [`39`](39-figma-local-bridge/PLAN.md) и проверить ограниченный local bridge
   на двух новых artboards; до этого его status остаётся `source-level`.

### P1 — production readiness

- hardening per-device enrollment: rebind policy, rate limit, pairing, rotation;
- access/refresh key rotation, revocation policy и полноценный secret storage;
- external production HTTPS/gRPC TLS, при необходимости mTLS, certificate issuance/rotation;
  для закрытой private LAN допустим insecure HTTP/gRPC без белого IP;
- Windows Credential Manager hardening и kiosk provisioning Assigned Access/
  Shell Launcher с обратимой политикой;
- backup/restore, deployment/observability policy и load checks.

### Product backlog

- [`plans/45-steam-guest-launcher/PLAN.md`](45-steam-guest-launcher/PLAN.md) —
  отдельный контур разрешённых гостевых Steam-аккаунтов: собственный
  PostgreSQL-контейнер, HTTP-сервис на порту `8200`, Windows-агент
  `HubShellSteam.exe` и самостоятельное подтверждение работы раз в 30 секунд.
  При отсутствии подтверждений пять минут сервис освобождает аккаунт.
  Контур не использует таблицы, деньги или команды HubShell. Есть исходный код
  и unit-тесты аренды/освобождения; ещё нужно вручную проверить запуск
  контейнеров с настоящими секретами и работу Steam на реальном Windows-ПК.
- Сводный backlog из [`fixes.md`](../fixes.md) вынесен в
  [`plans/44-fixes-features/PLAN.md`](44-fixes-features/PLAN.md): P0 — переход
  package→per-minute, локальный таймер без перезапуска от одинакового heartbeat
  и stop/access-gate/restart; P1 — платежи,
  группы, отрицательный баланс и guest policy; P2 — Windows UI, уведомления и
  tooltip карты. Для отрицательного баланса формула credit-времени не нужна:
  UI показывает `0 минут`, а backend применяет политику группы.
- внешние payment provider/webhook integrations;
- basket/returns и order-семантика сверх entitlement queue из P0-плана;
- bonus spending, reservations of funds, refunds и guest cashier flow;
- retention/cohort/LTV и тяжёлые read projections, XLSX/PDF reports;
- notifications, employees/roles, расширенный audit;
- только после подтверждённой нагрузки — выделение модулей в deployment units.

## 12. Повторяемые команды

Из корня:

```bash
cd /home/daniel/HubShell
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f backend-http
```

Backend:

```bash
cd /home/daniel/HubShell
uv sync --project ./backend
uv run --directory ./backend python scripts/generate_proto.py
uv run --directory ./backend alembic upgrade head
uv run --directory ./backend pytest -q
uv run --directory ./backend ruff check .
uv run --directory ./backend ruff format --check src tests alembic/versions/20260830_0031_payment_methods.py
```

Интеграционные проверки требуют DSN:

```bash
cd /home/daniel/HubShell
GAMECLUB_TEST_POSTGRES_DSN=... GAMECLUB_TEST_REDIS_URL=... uv run --directory ./backend pytest -q
```

Для отдельной локальной PostgreSQL-проверки:

```bash
cd /home/daniel/HubShell
./scripts/prepare-postgres-test.sh
./scripts/run-postgres-tests.sh
```

Скрипты поднимают только контейнер `hubshell-test-postgres`, применяют Alembic,
добавляют повторяемые тестовые факты и передают приложению
`GAMECLUB_TEST_POSTGRES_DSN`. Остальные контейнеры Compose при этом не запускаются.

Frontend:

```bash
cd /home/daniel/HubShell
npm --prefix ./frontend install
npm --prefix ./frontend run typecheck
npm --prefix ./frontend run build
```

Windows — только PowerShell на Windows:

```powershell
Set-Location "C:\Git\HubShell"
.\win-client\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
dotnet test win-client\GameClub.Client.sln --configuration Debug -p:Platform=x64
```

Для solution используется `-p:Platform=x64`; `--arch` для solution не является
эквивалентом и приводит к ошибке SDK `NETSDK1134`.

## 13. Правила обновления Summary

После каждого substantive-среза обновлять минимум:

1. фактический статус нужного детального плана;
2. соответствующую строку/раздел `VERIFICATION.md` с границей доказательства;
3. этот файл: историю, изменённые контракты, новые пути и открытые задачи;
4. migration head/protobuf/API surface, если они изменились;
5. список чекапов — отдельно для unit, PostgreSQL/Redis integration, Compose,
   browser visual/live и Windows native.

Не считать задачу закрытой только потому, что она есть в плане или UI-кнопка
видна: нужен проверяемый backend use case и подходящий чек уровня требования.
