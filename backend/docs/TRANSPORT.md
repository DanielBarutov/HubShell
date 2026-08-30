# Transport boundary

В первой версии используются два транспорта с разными потребителями:

- web frontend → HTTP JSON FastAPI BFF на `/api/v1`;
- Windows-клиент и будущие внутренние deployment units → native gRPC.

Обычный браузер не вызывает native gRPC напрямую, поэтому frontend не получает
доступ к внутренним application ports или PostgreSQL. `frontend/src/api.ts`
является единственной typed boundary для web-запросов. Protobuf-файлы в
`proto/gameclub/v1/` остаются source of truth для gRPC, а generated Python/C# код
не редактируется вручную.

Каждая изменяющая операция получает deadline на gRPC-границе и idempotency key,
если повторная доставка может создать финансовый, reservation или workstation
эффект. HTTP BFF возвращает безопасные `code/message` и `x-request-id`.
