# План 00 — Foundation и каркас backend

Статус: `in_progress`  
Приоритет: `P0`  
Зависимости: нет

## Цель

Создать минимальный рабочий backend-каркас с async I/O, PostgreSQL, Redis, FastAPI, gRPC и воспроизводимыми проверками.

## Входит в план

- backend package structure по слоям;
- FastAPI и gRPC entrypoints без бизнес-логики;
- выбор версий Python, PostgreSQL и Redis;
- async driver/ORM, миграции и transaction boundary;
- Redis для Dramatiq/cache/technical locks;
- versioned protobuf и генерация типов;
- environment settings, health/readiness, graceful shutdown;
- Ruff с сортировкой импортов и тестовый pipeline;
- локальный dev setup и документация.

## Не входит

- бизнес-сущности и полноценный JWT flow;
- production deployment/Kubernetes;
- готовые web-экраны и WinUI;
- выделение модулей в отдельные процессы.

## Решения, которые нужно зафиксировать

1. Версии runtime и package managers.
2. Async ORM/driver, миграционный инструмент и способ управления транзакциями.
3. Python gRPC runtime, генерация и хранение generated code.
4. Browser gateway/BFF или grpc-web transport.
5. Формат environment, logging и correlation ID.
6. Обязательный type checking и CI-порог.

## Задачи

1. [x] Создать `backend/` package layout: `presentation`, `application`, `domain`, `repository`, `infrastructure`.
2. [x] Поднять FastAPI/gRPC skeleton и конфигурацию.
3. [x] Поднять PostgreSQL/Redis для dev/test и проверить их health.
4. [x] Настроить Alembic migrations и применить foundation baseline к PostgreSQL.
5. [x] Довести test database lifecycle и graceful shutdown до отдельной проверки.
6. [x] Настроить Ruff, тесты и проверку импортов.
7. [x] Создать первый versioned protobuf package и генерацию Python-кода.
8. [x] Проверить source-of-truth/generation layout для web gateway и C#; WinUI compile остаётся platform-specific проверкой.
9. [x] Описать общий error/status convention, timeout, cancellation и request/correlation ID.
10. [x] Добавить README, `.gitignore` и безопасный example environment.
11. [x] Подключить async Dramatiq broker boundary и первый worker use case для reservations.

Первый рабочий срез выполнен для Python backend: зависимости установлены через `uv`, FastAPI health endpoints и gRPC `GetHealth` работают. PostgreSQL/Redis прошли локальную проверку, protobuf source-of-truth проверен для Python/C# consumers, Windows/C# runtime-сборка ещё не проверялась. Dramatiq worker проверен на stub broker и в полном Docker Compose dev-стеке с PostgreSQL/Redis; scheduler и Alembic migration также проверены в compose-запуске.

Общий transport-контракт зафиксирован в [`backend/docs/ERRORS.md`](../../docs/ERRORS.md):
application codes, HTTP/gRPC statuses, request ID, deadline и cancellation policy.

## Критерии готовности

- чистое окружение запускает backend skeleton;
- PostgreSQL и Redis подключаются только через settings;
- миграции выполняются на пустой базе;
- Ruff и тесты запускаются документированными командами;
- protobuf генерируется без ручного расхождения типов;
- health/readiness различают состояние приложения и зависимостей;
- реальные credentials отсутствуют в репозитории.

## Риски

- native gRPC browser transport может потребовать отдельный gateway;
- Windows build нельзя полноценно проверить на Linux;
- Dramatiq требует явного решения для фоновых задач и async boundary.

## Проверки

- Ruff, format check и pytest;
- чистый запуск инфраструктуры;
- миграция на пустую PostgreSQL;
- protobuf generation/compatibility;
- проверка README на чистом окружении.

## Открытые вопросы

- хранить generated code в Git или генерировать на CI;
- нужен ли единый Python namespace или отдельные packages;
- какой deployment и secret storage будет использоваться в production.
