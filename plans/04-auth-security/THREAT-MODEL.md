# Auth / Security — threat model MVP

## Границы доверия

1. Операторский browser считается недоверенным клиентом: frontend не хранит
   signing secret и не решает permissions самостоятельно.
2. HTTP BFF и gRPC gateway — публичные точки входа backend. Каждый вход валидирует
   Bearer JWT, а application use case повторяет permission boundary.
3. Windows-клиент считается скомпрометируемым устройством: ему выдаётся только
   device subject с `workstations.connect`; operator permissions и refresh token ему
   не выдаются.
4. PostgreSQL и Redis — доверенные внутренние зависимости, но их отказ не должен
   превращать ошибку в успешную финансовую операцию.
5. Dramatiq worker — внутренний сервисный consumer с теми же idempotency и
   reconciliation правилами, что и синхронный use case.

## Основные угрозы и меры

| Угроза | Мера MVP |
| --- | --- |
| Кража access JWT | короткий TTL, минимальные claims, TLS на production gRPC, HTTPS на edge |
| Повтор refresh token | opaque token, хранится только SHA-256 hash, atomic consume/rotation |
| Device token используется как операторский | отдельный `subject_type`, permission `workstations.connect`, handler checks |
| Подмена группы/команды ПК | JWT, device identity, allowlist команд и тем, acknowledgement/expiry |
| Удвоение пополнения или списания | idempotency key, unique constraint, row/advisory locks, ledger |
| Утечка PII в audit/logs | audit хранит actor/action/path/status/request id без payload; секреты не логируются |
| Подробная внутренняя ошибка раскрыта клиенту | единый безопасный error contract; детали остаются в server-side diagnostics |
| Компрометация signing key | текущий HS256 secret только в secret store/env; rotation/JWKS — production backlog |

## JWT policy

В access token находятся только `sub`, `subject_type`, roles/permissions, `iss`,
`aud`, `iat`, `exp` и `jti`. В него не помещаются nickname, phone, balance,
discount category, device capabilities или состояние сессии. Изменяемые данные
перечитываются из backend.

## Transport policy

Закрытый deployment клуба может использовать insecure HTTP/gRPC на loopback или
приватных LAN IPv4-адресах (`10/8`, `172.16/12`, `192.168/16`), включая
`production`, если backend не доступен из внешней сети. Для внешнего доступа
обязательны TLS через `GAMECLUB_GRPC_TLS_*` и контролируемый ingress/reverse
proxy; при необходимости включается mTLS. Отсутствие белого IP не заменяет
firewall и сетевую изоляцию.

Bootstrap device token — временный dev-механизм. До production нужны per-device
enrollment, rotation/revocation и защищённое хранилище Windows; bootstrap secret
не должен попадать в исходники, frontend bundle, логи или audit payload.
