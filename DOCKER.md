# Docker Compose

Корневой `compose.local.yml` поднимает полный локальный стек модульного
монолита:

- `postgres` — PostgreSQL 16;
- `redis` — Redis 7 с AOF;
- `backend-migrate` — одноразовый `alembic upgrade head`;
- `backend-http` — FastAPI HTTP/BFF на host-порту `8100`;
- `backend-grpc` — gRPC на host-порту `51051`;
- `worker` — Dramatiq workers для no-show и billing reconciliation;
- `meter-worker` — периодический meter для server-owned/V1-сессий;
- `scheduler` — постановка периодических задач;
- `kafka` и `kafka-v2-topics` — локальный Kafka KRaft и создание V2 topics;
- `v2-client-facts`, `v2-server-outbox`, `v2-confirmed-analytics` — приём и доставка V2 Kafka-событий;
- `otel-collector`, `prometheus`, `loki`, `tempo`, `pyroscope`, `alloy`, `grafana` — локальная наблюдаемость;
- `frontend` — production Vite build, который nginx отдаёт на host-порту `3100` и
  проксирует `/api` в `backend-http`.

Для локального подключения host-порты по умолчанию такие: PostgreSQL `55432`,
Redis `56379`, HTTP `8100`, gRPC `51051`, frontend `3100`, Pyroscope `4040`.
Внутри Docker-сети PostgreSQL и Redis остаются на `5432` и `6379`, backend — на
`8100` и `51051`, Pyroscope — на `4040`.

## Запуск

```bash
cd /home/daniel/HubShell
cp .env.example .env
docker compose -f compose.local.yml up -d --build
docker compose -f compose.local.yml ps
```

После запуска:

- web: <http://127.0.0.1:3100>;
- HTTP health: <http://127.0.0.1:8100/health/ready>;
- Grafana: <http://127.0.0.1:3300> (Explore → Pyroscope);
- Pyroscope UI: <http://127.0.0.1:4040>;
- gRPC: `127.0.0.1:51051`.

`backend-http` непрерывно отправляет CPU-профили в локальный Pyroscope. Имя
приложения по умолчанию — `gameclub-backend-http`, частота — 100 samples/s;
профили памяти выключены. Параметры можно переопределить через
`GAMECLUB_PYROSCOPE_APPLICATION_NAME` и `GAMECLUB_PYROSCOPE_SAMPLE_RATE`.
Pyroscope хранит данные в named volume `gameclub-pyroscope-data`.

Для Windows-клиентов из private LAN backend публикуется на LAN-интерфейсах.
При необходимости ограничить его только loopback укажите в `.env`
`GAMECLUB_BIND_HOST=127.0.0.1`. Для обычного LAN deployment используйте:

```dotenv
GAMECLUB_BIND_HOST=0.0.0.0
GAMECLUB_HTTP_PORT=8100
GAMECLUB_GRPC_PORT=51051
```

После изменения переменных пересоздайте нужные сервисы; для единой пересборки
всего стека используйте:

```bash
docker compose -f compose.local.yml up -d --build
docker compose -f compose.local.yml ps
```

В `PORTS` должны появиться `0.0.0.0:8100->8100/tcp` и
`0.0.0.0:51051->51051/tcp`. Разрешите эти порты только для private network в
firewall; не публикуйте их в Интернет.

Dev-оператор берётся из `.env`: по умолчанию `operator` / `change-me-locally`.
Эти значения предназначены только для локальной разработки.

Миграции запускаются отдельным контейнером до backend-сервисов. Код и весь стек
пересобираются одной командой из корня репозитория:

```bash
docker compose -f compose.local.yml up -d --build
```

Логи и остановка:

```bash
docker compose -f compose.local.yml logs -f backend-http
docker compose -f compose.local.yml down
```

`docker compose -f compose.local.yml down` сохраняет named volumes. Для полного сброса локальной базы
и Redis используйте только осознанно:

```bash
docker compose -f compose.local.yml down -v
```

Это dev-compose. Для закрытого private-LAN production нужны secret storage,
непредсказуемые credentials, backup/restore и отдельные deployment policies;
TLS/reverse proxy обязательны только при внешнем доступе к backend.
Windows-клиент подключается к опубликованному host-порту gRPC `51051`, а не к
имени `backend-grpc` из Docker-сети. Host-порты можно переопределить через
`GAMECLUB_FRONTEND_PORT`, `GAMECLUB_BIND_HOST`, `GAMECLUB_HTTP_PORT`, `GAMECLUB_GRPC_PORT`,
`GAMECLUB_POSTGRES_PORT`, `GAMECLUB_REDIS_PORT` и `GAMECLUB_PYROSCOPE_PORT` в
`.env`.


## Серверное развёртывание

`compose.local.yml` собирает приложение из исходников для Linux-разработки;
`compose.deploy.yml` запускает опубликованные образы, без build/extends/специальных YAML-тегов.
Файл в Dockhand: `compose.deploy.yml`, ветка `main`, имя стека/проекта `hubshell`.
Feature-ветки проходят проверки pull request; выпуск собирается после попадания в main.
Три `HUBSHELL_*_IMAGE` берутся из подписанного images.env одного выпуска (digest-ссылки).
Автообновление всего парка включается только после Windows pilot и общего CD barrier.

```bash
docker compose --env-file /path/to/secrets/stack.env -f compose.deploy.yml up -d
docker compose --env-file /path/to/secrets/stack.env -f compose.deploy.yml ps
python3 scripts/check-compose.py
```

`HUBSHELL_BIND_HOST` задаёт LAN IP, по умолчанию 127.0.0.1. Порты:
`HUBSHELL_FRONTEND_PORT=3100`, `HUBSHELL_HTTP_PORT=8100`,
`HUBSHELL_GRPC_PORT=51051`, `HUBSHELL_STEAM_GUEST_PORT=8200`.
Базы, Redis, Kafka и observability наружу не публикуются.
Секреты хранятся вне Git; локальные значения .env.example не являются серверными.

При первом запуске hubshell создаются новые hubshell_* volumes. Данные прежнего
тестового стека не переносятся. Пользователь подключит отдельно свои volumes
с существующей клиентской базой и ПК. До подключения нужно остановить писателей
и проверить совместимость схем/образов и backup; volumes не удаляются.
Локальный проект gameshell оставлен для сохранения Linux developer volumes.
