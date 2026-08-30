# План 04 — Auth / Security

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: `00-foundation`

## Цель

Создать единый контур аутентификации и авторизации для web, Windows-клиента и backend-модулей с JWT Bearer, минимальными claims и проверкой permissions внутри use cases.

## Входит в план

- identity операторов, администраторов и устройств;
- JWT access/refresh strategy;
- Bearer metadata для gRPC;
- роли и permissions;
- authorization policy в Application;
- bootstrap identity Windows-клиента;
- TLS и secret policy;
- audit/security events;
- безопасные ошибки и redaction.

## Не входит

- конкретный SSO без требования;
- отдельный IAM-продукт;
- PII и баланс в JWT;
- секреты в frontend bundle или Windows-клиенте;
- опасные команды по умолчанию.

## Базовая модель

Минимальные claims: `sub`, subject type, роли/permissions или ссылка на них, `iss`, `aud`, `iat`, `exp`, `jti`. На каждом защищённом входе проверяются подпись, expiry, issuer, audience и subject type. Permission проверяется повторно в use case.

Нужно зафиксировать audiences, rotation через JWKS или другой механизм, revoke refresh token и разные policies для web, Windows и internal services.

## Задачи

1. [x] Описать threat model и границы доверия в `THREAT-MODEL.md`.
2. [x] Определить identity types и роли MVP.
3. [x] Зафиксировать claims, TTL, issuer/audience; key rotation остаётся.
4. [x] Определить и реализовать access/refresh/logout/revocation flow.
5. [x] Реализовать auth ports через `typing.Protocol`.
6. [x] Реализовать gRPC audit interceptor; явная permission-проверка сохраняется в каждом handler.
7. [x] Реализовать базовую use-case authorization matrix.
8. [x] Спроектировать dev device bootstrap и reconnect boundary; per-device enrollment и rotation остаются.
9. [x] Добавить audit для финансовых и административных операций через HTTP BFF и gRPC.
10. [x] Добавить явную gRPC TLS-конфигурацию, запрет insecure gRPC в production,
    secret handling и error redaction policy.

Текущий срез добавил audit trail для изменяющих operator HTTP BFF- и gRPC-действий:
сохраняются actor id (или `null` для неавторизованного запроса), operation, transport
method/path, request id, status и outcome. Для PostgreSQL это отдельная таблица
`audit_events`; payload и чувствительные данные не попадают в событие. Для dev/operator flow
добавлены короткоживущий access JWT и непрозрачный refresh token с хранением только
SHA-256 хеша, атомарным consume, ротацией и logout-revoke; доступны memory и Redis
адаптеры. Device bootstrap выдаёт только access token. Per-device enrollment/rotation
и key rotation остаются production-этапами; базовая TLS-конфигурация для gRPC уже
реализована, а выпуск и управление production-сертификатами остаются deployment-задачей.

gRPC в dev по-прежнему может работать на loopback без TLS. В `prod`/`production`
окружении `create_server` требует сертификат и закрытый ключ через
`GAMECLUB_GRPC_TLS_CERT_FILE` и `GAMECLUB_GRPC_TLS_KEY_FILE`; mTLS включается
отдельно через client CA и `GAMECLUB_GRPC_TLS_REQUIRE_CLIENT_CERTIFICATE`.

## Критерии готовности

- invalid/expired/wrong issuer/audience/subject отклоняются;
- одинаковая policy работает для gateway, gRPC и background jobs;
- JWT не содержит PII и изменяемых бизнес-данных;
- secrets не попадают в Git, logs и builds;
- sensitive actions имеют audit record;
- revoke/rotation документированы;
- ошибки не раскрывают внутренние детали.

## Риски

- широкие claims увеличивают последствия утечки;
- разные policies создадут обход авторизации;
- ручное управление signing keys усложнит rotation и revoke.

## Проверки

- token validation и policy matrix unit tests;
- gRPC interceptor tests;
- JWKS/signing integration fixtures;
- negative tests expiry/audience/issuer/subject/permissions;
- secret scanning и log redaction;
- TLS smoke test.

## Открытые вопросы

- кто выпускает токены и где хранится signing key;
- нужен ли club/location scope;
- роли MVP;
- как входит Windows-клиент;
- нужен ли mTLS после выделения сервисов.
