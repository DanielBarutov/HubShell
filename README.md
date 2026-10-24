# HubShell

**Проект находится в активной разработке.** Функциональность, интерфейсы и протоколы меняются; часть интеграционных и платформенных проверок ещё не завершена. Текущее состояние проверок — в [plans/VERIFICATION.md](plans/VERIFICATION.md).

## Основная идея

HubShell — система управления компьютерным клубом, объединяющая сервер, веб-интерфейс оператора и клиент на игровых ПК.

Оператор работает с картой мест: видит состояние ПК и Xbox, управляет игровыми сессиями, бронированиями, клиентами и гостями. Система объединяет тарифы и пакеты времени, баланс и бонусы, продажи товаров, складские остатки, кассовые смены и аналитику.

На игровом ПК клиент показывает экран входа, личный кабинет и компактный виджет сессии. V2-клиент ведёт локальный учёт по подписанному сервером снимку и сохраняет события при кратковременном обрыве связи для последующего подтверждения. Сервер остаётся владельцем баланса и окончательных финансовых решений.

## Стек технологий

| Компонент | Назначение | Технологии |
| --- | --- | --- |
| **Backend** — [`backend/`](backend/) | Бизнес-правила, API, сессии и финансовый учёт; модульный монолит с разделением слоёв | Python 3.12, FastAPI, Uvicorn, Pydantic, SQLAlchemy 2 Async, asyncpg, Alembic, PostgreSQL, Redis, Dramatiq, FastStream, Apache Kafka, gRPC, Protocol Buffers; управление зависимостями через uv |
| **Frontend** — [`frontend/`](frontend/) | Веб-интерфейс оператора, работающий через HTTP API backend | TypeScript, React 19, Vite 7, Redux Toolkit, React Redux, Tailwind CSS 4, daisyUI 5, Lucide |
| **Клиент игровых ПК** — [`win-client/`](win-client/) | Экран доступа, личный кабинет, виджет сессии и локальный журнал V2; целевая ОС — Windows, для разработки есть Linux-host | C#, .NET 8, Avalonia 11, Fluent Theme, gRPC, Protocol Buffers; Windows DPAPI для защищённого журнала, отдельный watchdog для сопровождения клиента и обновлений |
| **Steam Guest** — [`steam-guest/`](steam-guest/) | Отдельный сервис аренды гостевых Steam-аккаунтов и фоновый Windows-агент | C#, .NET 8, ASP.NET Core, PostgreSQL, Npgsql, HTTP API |

Для окружения и доставки используются Docker, Docker Compose и GitHub Actions. Проверки компонентов: pytest и Ruff для backend, Vitest и Testing Library для frontend, .NET-тесты для клиента.

## Документация

- [Backend: настройка и запуск](backend/README.md).
- [Frontend: настройка и запуск](frontend/README.md).
- [Клиент ПК: Linux developer host и Windows-поставка](win-client/README.md).
- [Steam Guest: сервис и агент](steam-guest/README.md).
- [Планы разработки](plans/README.md) и [сводка состояния](plans/SUMMARY.md).
- Продуктовые контракты: [backend](backend/PRODUCT-CONTRACT.md), [frontend](frontend/PRODUCT-CONTRACT.md), [клиент ПК](win-client/PRODUCT-CONTRACT.md).
