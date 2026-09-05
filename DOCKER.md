# Docker Compose

Корневой `docker-compose.yml` поднимает полный локальный стек модульного
монолита:

- `postgres` — PostgreSQL 16;
- `redis` — Redis 7 с AOF;
- `backend-migrate` — одноразовый `alembic upgrade head`;
- `backend-http` — FastAPI HTTP/BFF на host-порту `8100`;
- `backend-grpc` — gRPC на host-порту `51051`;
- `worker` — Dramatiq workers для no-show и billing reconciliation;
- `scheduler` — постановка периодических задач;
- `frontend` — production Vite build, который nginx отдаёт на host-порту `3100` и
  проксирует `/api` в `backend-http`.

Для локального подключения host-порты по умолчанию такие: PostgreSQL `55432`,
Redis `56379`, HTTP `8100`, gRPC `51051`, frontend `3100`. Внутри Docker-сети
PostgreSQL и Redis остаются на `5432` и `6379`, а backend — на `8100` и `51051`.

## Запуск

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

После запуска:

- web: <http://127.0.0.1:3100>;
- HTTP health: <http://127.0.0.1:8100/health/ready>;
- gRPC: `127.0.0.1:51051`.

Для Windows-клиентов из private LAN backend публикуется на LAN-интерфейсах.
При необходимости ограничить его только loopback укажите в `.env`
`GAMECLUB_BIND_HOST=127.0.0.1`. Для обычного LAN deployment используйте:

```dotenv
GAMECLUB_BIND_HOST=0.0.0.0
GAMECLUB_HTTP_PORT=8100
GAMECLUB_GRPC_PORT=51051
```

После этого пересоздайте только backend-контейнеры:

```bash
docker compose up -d --force-recreate backend-http backend-grpc
docker compose ps
```

В `PORTS` должны появиться `0.0.0.0:8100->8100/tcp` и
`0.0.0.0:51051->51051/tcp`. Разрешите эти порты только для private network в
firewall; не публикуйте их в Интернет.

Dev-оператор берётся из `.env`: по умолчанию `operator` / `change-me-locally`.
Эти значения предназначены только для локальной разработки.

Миграции запускаются отдельным контейнером до backend-сервисов. При изменении
кода для пересборки достаточно выполнить:

```bash
docker compose up -d --build backend-http backend-grpc worker scheduler frontend
```

Логи и остановка:

```bash
docker compose logs -f backend-http
docker compose down
```

`docker compose down` сохраняет named volumes. Для полного сброса локальной базы
и Redis используйте только осознанно:

```bash
docker compose down -v
```

Это dev-compose. Для закрытого private-LAN production нужны secret storage,
непредсказуемые credentials, backup/restore и отдельные deployment policies;
TLS/reverse proxy обязательны только при внешнем доступе к backend.
Windows-клиент подключается к опубликованному host-порту gRPC `51051`, а не к
имени `backend-grpc` из Docker-сети. Host-порты можно переопределить через
`GAMECLUB_FRONTEND_PORT`, `GAMECLUB_BIND_HOST`, `GAMECLUB_HTTP_PORT`, `GAMECLUB_GRPC_PORT`,
`GAMECLUB_POSTGRES_PORT` и `GAMECLUB_REDIS_PORT` в `.env`.
