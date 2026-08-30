# План 02 — Clients / Guests

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: `00-foundation`, базовые решения `04-auth-security`

## Цель

Создать bounded context клиентов и гостей с быстрым поиском, расширяемыми скидочными категориями и безопасной моделью баланса/бонусов.

## Входит в план

- guest/client lifecycle;
- `id`, `nickname`, `phone`;
- `client_discount_category`;
- `balance`, `balance_bonus`;
- даты создания, изменения, блокировки и другие утверждённые даты;
- нормализация и поиск;
- balance ledger и история операций;
- ручное top-up с idempotency key;
- privacy-safe logging и audit.

## Не входит

- эквайринг и внешние платежи;
- списание за игровую сессию;
- полный каталог тарифов;
- импорт Gizmo/SmartShell;
- полноценная CRM.

## Домен и правила

Нужно определить guest/registered status, nickname constraints, canonical phone format, категории скидок и бонусную единицу. Persisted guest profile не имеет баланса и ledger; баланс принадлежит только registered client. Деньги хранятся как integer minor units или PostgreSQL `NUMERIC`, но не как `float`.

`BalanceOperation` содержит тип, сумму, причину, автора, reference и idempotency key. Баланс не изменяется прямым присваиванием в handler'е. Повторный запрос не должен удваивать операцию.

Поиск запускается от 3 значимых символов nickname или 4 цифр телефона после нормализации. Короткий ввод не отправляется на backend.

## Задачи

1. [x] Зафиксировать lifecycle и правила идентификации в `DOMAIN-RULES.md`.
2. [x] Реализовать value objects nickname, phone, money и bonus.
3. [x] Спроектировать ledger и конкурентные транзакции; memory и PostgreSQL
   repositories применяют idempotency lock и атомарное изменение баланса.
4. [x] Описать protobuf/API для CRUD, search, balance и history.
5. [x] Реализовать Domain/Application через `typing.Protocol`.
6. [x] Реализовать PostgreSQL schema, indexes и migrations.
7. [x] Реализовать operator top-up с idempotency для последовательных повторов.
8. [x] Добавить базовые permissions; изменяющие операции попадают в общий audit trail Auth/Security.
9. [x] Добавить unit/API/DB smoke tests и memory/PostgreSQL concurrency tests; отдельные protobuf contract tests остаются.
10. [x] Открыть read-only историю balance ledger через HTTP/gRPC с ограничением выдачи и подключить её к карточке клиента в web.
11. [x] Добавить отдельный persisted Guest profile с CRUD/search через memory/PostgreSQL, HTTP и gRPC без баланса.
12. [x] Связать `guest_id` с Reservations и Sessions, сохраняя guest nickname как явный display snapshot и поддерживая legacy `guest_name` для разового гостя.
13. [x] Зафиксировать российский canonical phone как 11 цифр с префиксом `7`:
    ввод `8XXXXXXXXXX` и `XXXXXXXXXX` нормализуется до одного значения до
    сохранения и поиска; анонимный walk-in не создаёт persisted guest profile.
14. [x] Добавить защищённые operator-операции редактирования профиля,
    мягкой деактивации и генерации временного пароля; в хранилище сохраняется
    только password hash, а выдаваемый temporary password не попадает в логи.
    Начисление основного и бонусного баланса остаётся ledger-операцией.

## Критерии готовности

- поиск соблюдает пороги и нормализацию;
- баланс/бонусы не используют float;
- top-up имеет историю, автора, причину и idempotency key;
- оператор видит последние ledger-операции клиента без изменения данных;
- гость может быть найден и назначен на бронь/сессию без доступа к клиентскому балансу;
- незарегистрированный посетитель может быть выбран как анонимный `Гость` без
  обязательного профиля;
- оператор может изменить ник, телефон и discount category, выдать временный
  пароль, мягко деактивировать клиента и открыть два раздельных balance flows;
- повторная отправка безопасна;
- конкурентные операции не теряются;
- PII не попадает в обычные логи.

## Риски

- неоднозначная нормализация телефона создаст дубли;
- ошибка ledger напрямую влияет на деньги;
- платежи в будущем могут потребовать расширения operation references.

## Проверки

- unit tests value objects/search;
- PostgreSQL integration tests;
- transaction/concurrency tests;
- duplicate/idempotency tests;
- gRPC contract и privacy tests.

## Открытые вопросы

- guest создаётся автоматически или вручную;
- допускаются ли одинаковые nickname;
- может ли телефон быть у нескольких аккаунтов;
- можно ли отдельно списывать bonus;
- какие даты обязательны в MVP.
