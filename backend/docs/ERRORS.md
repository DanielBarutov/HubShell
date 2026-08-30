# Ошибки, дедлайны и request ID

Это общий контракт transport-слоя backend. Application-слой возвращает
`ApplicationError` с одним из кодов, а HTTP/gRPC adapters переводят его в
соответствующий внешний статус.

## Коды

| Application code | HTTP | gRPC | Когда используется |
| --- | ---: | --- | --- |
| `invalid_argument` | 400 | `INVALID_ARGUMENT` | Невалидное поле, период или payload |
| `unauthenticated` | 401 | `UNAUTHENTICATED` | Нет или недействителен JWT |
| `permission_denied` | 403 | `PERMISSION_DENIED` | У principal нет требуемого permission |
| `not_found` | 404 | `NOT_FOUND` | Ресурс не найден |
| `conflict` | 409 | `ALREADY_EXISTS`/`ABORTED` | Конфликт idempotency или ресурсов |
| `dependency_unavailable` | 503 | `UNAVAILABLE` | Временная недоступность PostgreSQL/Redis |
| `internal` | 500 | `INTERNAL` | Непредвиденная ошибка |

HTTP-ошибка имеет JSON-форму:

```json
{
  "code": "conflict",
  "message": "Workstation is already reserved"
}
```

В production сообщение не должно содержать JWT, секреты, SQL, stack trace и
лишние персональные данные.

## Request ID

Клиент может прислать `X-Request-ID`. Если заголовок отсутствует, HTTP-прослойка
создаёт UUID. Тот же идентификатор возвращается в response header, включая
ошибки. Для gRPC request ID передаётся через metadata `x-request-id`; до
выделения общего interceptor handlers должны сохранять deadline и cancellation
контекста при вызове application-портов.

## Дедлайн и отмена

- Изменяющий HTTP-запрос должен завершаться с понятным timeout на gateway.
- Изменяющий gRPC-вызов должен получать deadline от клиента и проверять
  cancellation до дорогого I/O.
- Повторяемые финансовые, reservation и workstation-команды обязаны иметь
  idempotency key.
- `429` зарезервирован для rate limiting и не заменяет `400`, `401`, `403` или
  `409`.
