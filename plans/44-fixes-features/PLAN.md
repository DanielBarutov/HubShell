# План 44 — fixes.md: фиксы, фичи и правки интерфейса

Статус: `implementation_complete / external_evidence_open`
Приоритет: `P0/P1/P2`  
Владельцы: `backend/`, `frontend/`, `win-client/`  
Источник требований: [`fixes.md`](../../fixes.md), срез от 2026-09-17

## Цель

Закрыть накопленный список проблем вокруг жизненного цикла игровой сессии,
оплаты, групп клиентов, гостевых тарифов и отображения времени. План является
единым master-планом: отдельные задачи имеют собственный владеющий модуль, но
финансовые и session-правила сначала фиксируются в backend и продуктовых
контрактах.

`fixes.md` остаётся входным списком, а не каноническим контрактом. В частности,
его последняя строка оборвана на словах «разрешенный креди». До реализации
нужно отдельно утвердить смысл этого правила.

## Границы

Входит:

- server-backed переход с entitlement-пакета на поминутное списание;
- корректное завершение сессии с подтверждением, access-gate (экраном входа
  на Windows-клиенте) и безопасной командой перезапуска;
- политика способов оплаты и смешанных платежей;
- группы клиентов, отрицательный баланс и группа по умолчанию;
- гостевые тарифы и запрет подмены активного зарегистрированного клиента;
- понятное отображение пакетов, времени и уведомлений в Windows-клиенте;
- tooltip карты мест с актуальным session snapshot.

Не входит без отдельного решения:

- подключение реального эквайринга или внешнего payment provider;
- произвольные shell-команды Windows;
- возвраты денежных средств как отдельный provider flow;
- полная история завершённых пакетов в клиенте;
- изменение `fixes.md` задним числом.

## Текущее основание

Уже существуют связанные реализации и планы:

- [`30-entitlements-meter`](../30-entitlements-meter/PLAN.md) — очередь,
  расходование, auto-next и server snapshot;
- [`35-frontend-contract-consumers`](../35-frontend-contract-consumers/PLAN.md)
  — карта мест, checkout и контекст активного клиента;
- [`36-windows-client-contract-consumers`](../36-windows-client-contract-consumers/PLAN.md)
  — package UI, stop/logout/restart и уведомления;
- [`31-settlement-reconciliation`](../31-settlement-reconciliation/PLAN.md) —
  финансовая идемпотентность и reconciliation;
- [`03-catalog-time-tariffs`](../03-catalog-time-tariffs/PLAN.md) — тарифы,
  временные окна и audience-фильтрация.

Наличие этих слоёв не считается доказательством исправления заявленных
runtime-багов. Каждая задача начинается с воспроизводимого сценария и
регрессионного теста.

## Реестр задач

| ID | Тип | Приоритет | Область | Результат |
| --- | --- | --- | --- | --- |
| F-01 | fix | P0 | session/billing | пакет исчерпывается и атомарно передаёт сессию на per-minute либо завершает её по политике группы |
| F-02 | fix | P0 | win-client | плавный локальный таймер с коррекцией по server snapshot без увеличения остатка из-за polling |
| F-03 | fix | P0 | session/workstations | подтверждённый stop → access-gate → allowlisted restart с ошибками по этапам |
| F-04 | feature | P1 | payments/sales | авторизованный клиент не ограничивает выбор депозита, наличных или перевода |
| F-05 | feature | P1 | payments | один заказ поддерживает mixed payment ровно как наличные + перевод, audit и reconciliation |
| F-06 | fix | P1 | client portal/win-client | после пополнения баланс и доступное время пересчитываются из нового snapshot |
| F-07 | fix | P1 | frontend/map | пополнение из карточки занятого ПК получает активного клиента и защищает смену получателя |
| F-08 | feature | P1 | clients/billing | группа клиента задаёт разрешение и лимит отрицательного баланса |
| F-09 | feature | P1 | settings/clients | новые зарегистрированные пользователи получают группу по умолчанию |
| F-10 | feature/fix | P1 | catalog/sales | guest-only и operator-only политика тарифа проверяется в backend и UI |
| F-11 | ui fix | P2 | win-client | показываются только active/queued пакеты, понятные статусы и корректные поля времени |
| F-12 | feature | P2 | notifications | оператор настраивает пороги, звук, Windows notification и текст |
| F-13 | feature | P2 | frontend/map | hover-карточка показывает session snapshot, названия пакетов, баланс и расчёт окончания |

## Контрактные решения до кода

До задач F-01, F-04, F-05, F-08 и F-10 обновить три обязательных документа:
`backend/PRODUCT-CONTRACT.md`, `frontend/PRODUCT-CONTRACT.md` и
`win-client/PRODUCT-CONTRACT.md` — только в тех частях, которые принадлежат
конкретному потребителю.

Нужно утвердить:

1. Отрицательный баланс действует только для поминутной тарификации или также
   для покупки пакетов, товаров и других списаний.
2. Лимит хранится как максимальный долг в integer cents; что происходит при
   достижении лимита и при изменении группы во время сессии.
3. Может ли оператор купить пакет активному зарегистрированному пользователю
   за наличные/карту/смешанно; если да, какая часть меняет депозит и как пакет
   связывается с текущей сессией.
4. Является ли «только оператором» отдельным полем канала продажи или
   следствием permission и session context.
5. Как трактуется «возврат» смешанного платежа: автоматическая пропорция,
   ручное подтверждение или пока только отмена до settlement.
6. Для уведомлений: где хранятся mp3/wav, размер/тип файла, кто имеет доступ,
   выполняется ли воспроизведение локально при offline и как правило не
   срабатывает повторно после server sync.
7. Для tooltip: интервал обновления, допустимая stale-давность и формула
   окончания при отрицательном балансе/разрешённом кредите.
8. Полный текст оборванного требования в `fixes.md`, строка 351.

Пока решения не утверждены, код не должен выводить поведение «по аналогии».

## Порядок реализации

### Фаза 0 — воспроизведение и контрактная фиксация

1. [x] Завести regression matrix для F-01…F-13: входные данные, ожидаемый
   backend result, UI result и уровень доказательства.
2. [partial: автоматические regression-сценарии воспроизведены локально; live Compose/Windows воспроизведение остаётся]
   Воспроизвести три критических бага на тестовом backend/Compose-контуре:
   auto-next/fallback, timer polling и stop/logout/restart.
3. [x] Зафиксировать текущие контрактные границы и обновить product contracts,
   owner plans и `plans/SUMMARY.md`. Открытые решения остаются release gate до
   перехода к P1-финансовым use cases.
4. [x] Проверить обратную совместимость миграций и DTO; protobuf не менялся,
   а новые client-group, sale-channel, payment-parts и notification DTO внесены
   отдельными миграциями/регрессиями. Полный upgrade/DSN smoke остаётся отдельной
   границей доказательств.

Результат текущего среза: regression test F-01 был сначала красным как строгий
`xfail`, затем positive-balance fallback, bounded group debt и stop при
исчерпании исправлены в `BillingService`; связанный backend slice проходит.
Для F-03 добавлен Core test порядка stop → restart policy, а для F-02 —
server-anchored local projection и Core test slice. Для F-04…F-13 добавлены
backend/frontend/Core-реализации и регрессии, включая durable settlement review
для неопределённого cash-результата и явное подтверждение смены получателя.
Все оставшиеся production gaps и platform boundaries описаны в
[`REGRESSION-MATRIX.md`](REGRESSION-MATRIX.md): DSN, live browser/Compose и
native Windows не выдаются за локальные unit/source проверки.

### Фаза 1 — P0: источник истины сессии

5. [x] **F-01.** [implementation complete: positive-balance fallback, bounded group debt и stop при исчерпании реализованы и покрыты; DSN/live остаются]
   Сделать end-to-end сценарий `ACTIVE package → EXHAUSTED →
   next compatible package/per-minute`; остаток должен стать нулём, не
   расходоваться дважды и не перескакивать назад. При недостатке средств
   применить group policy: завершить сессию либо разрешить долг до лимита.
6. [x] **F-02.** [implementation complete: Core projection и 1-секундный refresh реализованы; Windows visual smoke остаётся]
   Ввести в Win Client разделение server anchor и monotonic local
   countdown. Polling корректирует drift только при подтверждённом snapshot;
   переход между источниками времени не увеличивает отображаемый остаток.
7. [x] **F-03.** [implementation complete: Core stop acknowledgement и restart policy реализованы; native access-gate/restart остаются]
   Описать stop state machine: request sent, backend stopped,
   client acknowledged, access-gate opened, restart requested/acknowledged.
   Повторное нажатие должно быть безопасным, а ошибка каждого этапа — видимой
   и recoverable без локального финансового действия.

Ожидаемые артефакты: domain/application tests, API/gRPC contract tests,
PostgreSQL concurrency/UoW checks, Win Client Core tests и отдельный Windows
native smoke для access-gate, restart и power/session failure.

### Фаза 2 — P1: деньги, депозит и группы

8. [x] **F-04.** [implementation complete: entitlement API и active-session UI поддерживают депозит, наличные и перевод; live/native finance smoke остаётся]
   Разделить контекст активной игровой сессии и разрешённые
   operator payment methods. Backend повторно проверяет method policy, balance
   limits, permission и idempotency; frontend не скрывает допустимые методы
   только из-за авторизации клиента.
9. [x] **F-05.** [implementation complete: mixed payment наличные+перевод, durable settlement review/retry и regression реализованы; automatic rollback остаётся за MVP-границей]
   Обобщить payment parts на entitlement/tariff order: сумма частей
   равна order total, каждая часть имеет свой метод и audit reference, повторная
   отправка идемпотентна. Отдельно описать отмену и reconciliation; provider
   integration остаётся за границами плана.
10. [x] **F-06.** [implementation complete: backend snapshot и Win Core projection покрыты; live polling остаётся]
    После top-up публиковать/получать новый server snapshot и
    пересчитывать доступное per-minute время по актуальному zone tariff.
    Пакетный источник времени не должен заменяться балансом до его исчерпания.
11. [x] **F-07.** [implementation complete: PanelHost → DepositPanel, явное подтверждение смены получателя и component test реализованы; live/browser smoke остаётся]
    Передавать `active_session.client_id` из карты ПК в
    `DepositPanel`, предзаполнять и показывать имя клиента, а смену получателя
    делать явным подтверждённым действием. Backend остаётся последней проверкой.
12. [x] **F-08.** [implementation complete: domain/repository/API/meter policy, settings editor, выбор группы в карточке клиента и unit tests реализованы; DSN/live остаются]
   Добавить bounded client-group policy: allow-negative и
    `negative_limit_cents`; проверять её в debit/quote/meter/session stop,
    а не только в UI.
13. [x] **F-09.** [implementation complete: default regular, migration backfill, assignment при создании/редактировании клиента и settings CRUD реализованы; DSN migration/live остаются]
   Добавить настройку default group с audit и безопасным поведением
    при удалении/деактивации группы; assignment новых пользователей должен быть
    транзакционным и не менять существующих клиентов.

Ожидаемые артефакты: migrations/repositories/use cases, HTTP DTO, API tests,
PostgreSQL ledger/concurrency tests, settings/client UI tests и обновлённые
финансовые contract fixtures.

### Фаза 3 — P1: гостевые тарифы и operator checkout

14. [x] **F-10.** [implementation complete: disabled guest selector, pre-payment busy-session guard, audience/channel filtering, operator checkout и frontend API реализованы; browser/native smoke остаются]
    Развести audience (`guest`/`registered`) и channel
    (`operator`/`self-service`) в каталоге/quote. Зарегистрированный активный
    клиент не может быть переименован в guest через UI; backend отклоняет guest
    tariff sale для занятого ПК с его session. Самостоятельный Win Client flow
    не должен видеть operator-only tariff.
15. [x] Добавить frontend regression matrix для guest/user selector,
    активного клиента, operator-only каталога, backend 4xx и retry без двойной
    продажи.

### Фаза 4 — P2: Win Client UI и уведомления

16. [x] **F-11.** [implementation complete: Core/ViewModel фильтрация, приоритет active package и скрытие balance-time блока покрыты; visual smoke остаётся]
    На основании server snapshot показывать локализованные
    `Активный`/`В очереди`, остаток и длительность; скрывать `EXHAUSTED`/
    `BURNED`, поле balance-derived time во время active package и отдельную
    кнопку завершения тарифа.
17. [x] **F-12.** [implementation complete: backend rules/event id, settings UI, snapshot/gRPC transport, Win deduplicator и Windows adapter реализованы; native smoke остаётся]
    Добавить notification rules в settings/API/DTO и локальный
    Windows adapter для sound/toast. Событие должно иметь deduplication key,
    не повторяться на каждом heartbeat и безопасно обрабатываться при offline/
    reconnect. Linux/source-level тесты не заменяют Windows toast/audio smoke.

### Фаза 5 — P2: карта мест и наблюдаемость

18. [x] **F-13.** [implementation complete: MapView имеет отдельную hover/focus-карточку server snapshot с названиями пакетов, stale marker и component tests; live/browser smoke остаются]
    Добавить hover/focus tooltip на основе server snapshot:
    клиент, баланс, доступное время, названия активного и ожидающих пакетов,
    суммарное время и ориентировочное окончание. Показать признак устаревших
    данных и время снимка; не
    отображать технические UUID.
19. [partial: unit/component regression покрыта; live refresh после top-up, package auto-next, stop, смены группы и потери связи требует отдельного smoke]
    Проверить refresh после top-up, package auto-next, stop, смены группы и
    потери связи. При нулевом балансе UI показывает 0 минут, а backend решает
    продолжать или завершать поминутную сессию по политике группы.

## Матрица проверок

### Backend

- unit: transition/negative-balance/payment-policy/notification rule;
- API: guest vs registered, operator vs self-service, mixed parts, idempotency;
- gRPC/protobuf: snapshot, stop acknowledgement, unknown enum/field;
- PostgreSQL/DSN: ledger, package consume + debit в одной транзакционной
  границе, concurrent ticks, top-up refresh, migration upgrade.

Запуск из корня checkout:

```bash
cd /home/daniel/HubShell
uv run --directory ./backend pytest -q
uv run --directory ./backend ruff check .
```

DSN-проверки запускаются отдельно и не маскируются unit-результатом:

```bash
cd /home/daniel/HubShell
GAMECLUB_TEST_POSTGRES_DSN=... GAMECLUB_TEST_REDIS_URL=... uv run --directory ./backend pytest -q
```

### Frontend

- Vitest: payment selector, active-client deposit prefill, guest guard,
  package/time rendering, tooltip stale/error states;
- headed browser smoke: sale, map, PC panel, deposit, settings and reconnect;
- accessibility: keyboard focus, disabled selector, confirmation/error states.

```bash
cd /home/daniel/HubShell
npm --prefix ./frontend run typecheck
npm --prefix ./frontend run build
npm --prefix ./frontend run test -- --run
```

### Windows

- portable Core unit tests: countdown correction, source switch, notification
  dedupe and stop state machine;
- Avalonia visual/source checks on Linux;
- native Windows x64: access-gate, restart command, sound/toast, reconnect,
  ordinary user and failure recovery.

Linux compile/source evidence не утверждает Windows runtime, kiosk policy,
перезапуск или системные toast/audio.

## Критерии готовности плана

- все F-01…F-13 имеют regression test и указанное evidence boundary;
- финансовые решения описаны в product contracts до реализации;
- session/billing rules не дублируются в frontend или Win Client;
- операции оплаты, stop, top-up и notification имеют idempotency/deduplication;
- миграции обратимо применимы на существующей базе;
- отдельные отчёты показывают unit/API, DSN, browser и Windows native evidence;
- `fixes.md` не считается закрытым по наличию UI: каждый пункт подтверждён
  наблюдаемым поведением.

## Риски и зависимости

- F-01/F-02/F-03 зависят от общего session snapshot и корректной transaction
  boundary, а не только от polling/UI.
- F-04/F-05/F-08 требуют согласованной финансовой модели и могут затронуть
  существующие mixed product sales.
- F-10 зависит от различия audience и channel; одного enum guest недостаточно.
- F-12 зависит от Windows platform adapter и folder-based package layout;
  аудиофайл остаётся локальным путём, отдельное upload-хранилище не вводится.
- F-13 использует отображение 0 минут при отрицательном балансе; продолжение
  сессии определяется backend-политикой группы, а не расчётом кредитного времени.

## Связанные планы

`03`, `06`, `07`, `12`, `13`, `29`, `30`, `31`, `32`, `35`, `36`, `37`, `40`.
После утверждения решений задачи следует разносить в owner plans, сохраняя этот
документ master backlog и точку сверки по `fixes.md`.
