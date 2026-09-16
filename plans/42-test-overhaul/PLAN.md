# План 42 — переделка тестирования проекта

Статус: `in_progress`  
Приоритет: `P0`  
Владельцы: `backend/`, `frontend/`, `win-client/`

## Цель

Сделать тестирование единым, воспроизводимым и ориентированным на наблюдаемое
поведение во всех трёх частях HubShell. Тесты должны защищать бизнес-инварианты,
транспортные контракты и критические пользовательские потоки, а не текущую
структуру классов или наличие отдельных строк в исходниках.

## Baseline на 2026-09-16

- Backend: `146 passed, 18 skipped, 6 failed` командой `cd backend && uv run pytest -q`.
  Шесть падений относятся к устаревшим source-level ожиданиям после миграции
  frontend API и Windows UI на Avalonia.
- Frontend: `typecheck`, `lint` и `build` проходят; test runner отсутствует.
- Windows client: после `dotnet restore` тесты обнаружили три ошибки компиляции
  в изменённых тестах (`await` в синхронном тесте и два отсутствующих Avalonia
  namespace imports). Native Windows runtime и kiosk boundary остаются отдельным
  доказательством и не могут быть заменены Linux-тестом.
- Checkout содержит незакоммиченные изменения пользователя; работа ведётся
  поверх них без отката или перезаписи несвязанных файлов.

## Принципы и границы

1. Domain/application logic остаётся настоящей в unit-тестах; mock допускается
   только на внешней границе или нестабильном источнике.
2. Repository, ORM, protobuf serialization, HTTP/gRPC adapters и transaction
   boundaries проверяются интеграционно на реальной реализации и контролируемой
   инфраструктуре.
3. Source-level checks остаются только для packaging/platform declarations,
   generated-artifact presence и документов; бизнес-поведение проверяется через
   публичные entry points.
4. Реальное время, UUID, сеть, внешний API и Windows API контролируются через
   dependency seams; arbitrary sleeps и публичный интернет в suite запрещены.
5. Для Python-тестов обязательна короткая русская behavior-docstring сразу под
   объявлением теста. Новые TypeScript/C# тесты используют поведенческие имена и
   русские описания в test case metadata/XML summary по мере принятого стиля.

## Целевая раскладка

| Слой | Backend | Frontend | Windows client |
| --- | --- | --- | --- |
| Unit/domain | application/domain rules, deterministic clocks | normalizers, reducers, pure view rules | Core state, coordinators, policy |
| Adapter/API | FastAPI/gRPC public responses | real API facade + stubbed fetch boundary | gRPC adapter + controlled server/fakes |
| Persistence/integration | PostgreSQL/Redis, migrations, locking | — | filesystem journal where applicable |
| Critical flow | small gateway smoke | selected React/operator flows | Avalonia Linux smoke; native Windows separately |

## Порядок работ

1. [x] Снять baseline и записать границы доказательства.
2. [x] Актуализировать устаревшие contract-layout checks под текущие API/Avalonia
   boundaries; не возвращать compatibility-строки только ради теста.
3. [x] Восстановить компиляцию Linux-runnable C# test solution после текущей
   миграции на Avalonia.
4. [x] Добавить минимальный Vitest foundation и первые API-boundary tests для
   нормализации телефона, авторизации, refresh/retry, ошибок и idempotency
   headers.
5. [x] Разделить крупные backend test modules по bounded context и добавить
   русские docstrings без изменения проверяемого поведения. `test_modules.py`
   разделён на 4 bounded-context файла, `test_api_modules.py` — на 4 API-файла;
   convention guard проверяет наличие русских behavior-docstring.
6. [x] Ввести pytest markers/commands для unit, API, contract, PostgreSQL/Redis
   integration и slow/concurrency suites; убрать неявные пропуски из release
   gate, сохранив отдельный offline режим.
7. [ ] Добавить frontend component/accessibility tests для login, map, sale,
   booking, offline и confirmation flows. Покрыты login/map/sale/booking,
   offline-routing, settlement confirmation и modal/accessibility semantics;
   headed mock smoke подтвердил dashboard/map/offline panel/booking panel;
   полный browser visual/realtime matrix остаётся отдельным подпунктом.
8. [x] Добавить контрактные fixtures для HTTP/gRPC DTO и небольшой критический
   end-to-end набор; добавлены авторизованный ASGI context, стабильные HTTP DTO
   factories, общий snapshot contract и smoke рабочего места с гостевой бронью.
9. [x] Снять первый coverage baseline и установить guardrail без снижения
   измеренного уровня: backend `70.10%` lines с порогом `70%`, frontend `17.18%`
   lines с порогом `17%`; coverage не используется как замена behavior tests.
10. [ ] Отдельно выполнить Windows native smoke: publish, обычный пользователь,
    tray, DPAPI, restart и Assigned Access/Shell Launcher.

## Проверки каждой итерации

```bash
cd backend && uv run pytest -q
cd backend && uv run ruff check .
cd frontend && npm run typecheck && npm run lint && npm run test
cd win-client && dotnet test GameClub.Client.sln --configuration Debug -p:Platform=x64
```

При инфраструктурном ограничении результат фиксируется отдельно для unit/API,
PostgreSQL/Redis integration, browser visual и native Windows; пропуск не
считается успешным доказательством.
