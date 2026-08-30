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

Это dev-compose. Для production нужны secret storage, TLS/reverse proxy,
непредсказуемые credentials, backup/restore и отдельные deployment policies.
Windows-клиент подключается к опубликованному host-порту gRPC `51051`, а не к
имени `backend-grpc` из Docker-сети. Host-порты можно переопределить через
`GAMECLUB_FRONTEND_PORT`, `GAMECLUB_HTTP_PORT`, `GAMECLUB_GRPC_PORT`,
`GAMECLUB_POSTGRES_PORT` и `GAMECLUB_REDIS_PORT` в `.env`.
