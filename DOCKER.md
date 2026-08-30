# Docker Compose

Корневой `docker-compose.yml` поднимает полный локальный стек модульного
монолита:

- `postgres` — PostgreSQL 16;
- `redis` — Redis 7 с AOF;
- `backend-migrate` — одноразовый `alembic upgrade head`;
- `backend-http` — FastAPI HTTP/BFF на порту `8000`;
- `backend-grpc` — gRPC на порту `50051`;
- `worker` — Dramatiq workers для no-show и billing reconciliation;
- `scheduler` — постановка периодических задач;
- `frontend` — production Vite build, который nginx отдаёт на порту `3000` и
  проксирует `/api` в `backend-http`.

## Запуск

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

После запуска:

- web: <http://127.0.0.1:3000>;
- HTTP health: <http://127.0.0.1:8000/health/ready>;
- gRPC: `127.0.0.1:50051`.

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
Windows-клиент подключается к опубликованному host-порту gRPC, а не к имени
`backend-grpc` из Docker-сети.
