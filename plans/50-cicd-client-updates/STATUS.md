# Текущее состояние плана 50

Статус: in_progress. Полная цель и финальная сборка EXE/ZIP ещё не выполнены.
Согласовано: ждём все PC; при ошибке одного весь парк закрыт до исправления;
TrueNAS — отдельная пустая копия, volumes пользователь перенесёт позднее;
GitHub Actions + публичные GHCR images.

Реализовано:
- Миграции 0083–0086: Sessions barrier, deployment, Workstations freeze,
  хешированные индивидуальные updater credentials.
- HTTP/bootstrap, отдельный JWT subject updater, отзыв JWT при ротации,
  idempotent begin-install, финальный раунд всех PC, пробный PC и двойное подтверждение.
- Точная сверка номера/хеша фактов последнего локального ledger с confirmed V2 chain.
- Separate watchdog host, signed manifest/ZIP validation и CI packager.
- GUI guard, durable blocked journal, Windows pipe server (SYSTEM peer), безопасное
  закрытие только idle GUI; service-side pipe клиент проверяет PID/path/session.
  IPC=1 требует все поля готовности/checkpoint; сборки Windows host на Linux проходят.
- Portable executable install/rollback/recovery с резервным хешем; server.ini/ledger не меняются.
- Watchdog HTTP loop, signed staging, begin-install до закрытия, пауза восстановления,
  запуск/проверка GUI, откат и восстановление при рестарте. Потеря installed-report
  не откатывает здоровый EXE; непроверенный EXE не запускается после сбоя восстановления.
- Machine updater config: DPAPI LocalMachine, ACL только SYSTEM/Administrators;
  installer принимает enrollment JSON/адрес backend/закреплённый публичный ключ.
  HubShell.Setup.zip содержит оба EXE, scripts и server.ini.example, без machine secrets.
- Подписанный server-release.json привязывает digest трёх образов к тому же
  release_id/commit, что клиентский manifest. CI проверяет backend на PostgreSQL
  до сборки/публикации и подписывает server manifest после push образов.
- Проверяемое атомарное зеркало GitHub Release; backend-http получает mirror volume
  только для чтения. CLI mirror-client-release.py не доверяет ключу из загрузки.
- Ядро координации CD и JSON/text отчёт сохраняют весь знаменатель парка;
  старый/запущенный release_id службы сохраняются в backend JSONB без новой миграции.
- Серверный Compose stage: pull application images, stop writers, два PostgreSQL
  backup с пробным восстановлением, migration, app-only up, gRPC/frontend smoke.
- CLI deploy-release.py связывает mirror/coordinator/server stage, protected auth
  с refresh, job/lock/resume/timeout, полный отчёт и merge digest в Dockhand.
  Без --release-id возобновляет active job, затем выбирает GitHub latest; fetch/checkout
  только подписанного commit из approved origin. Dirty checkout не заменяется.
  Mirror path определяется через named volume на Docker host. Пока проверены
  отдельные HTTP/файловые/оркестрационные границы, не live NAS pipeline.
- Статус в существующих настройках: operator-only GET /current, server-owned
  confirmed/total и статусы всех целей; версии/время ответов/ошибка. Poll/refresh,
  abort timeout, закрытие страницы прекращает опрос; stale данные не показываются
  после ошибки. Браузерная проверка недоступна: CUA browsers=[] / iab unavailable.
- Linux UpdateAgentHost и real TCP/HTTP/PostgreSQL E2E: два настоящих .NET
  ClientUpdateAgent, подписи/ZIP/файлы, updater JWT и независимый GUI JWT.
  Missing/active PC блокируют prepare; финальный раунд, pilot, bad GUI → rollback
  и общий failed, explicit retry → 2/2 → снятие локальных блоков. Отдельный backend
  process останавливается и запускается с другим PID, сохраняя barrier/reports;
  обрыв HTTP не снимает local block.
  GUI/process/IPC в этом host симулируются, Windows SCM/WTS/ACL этим не доказаны.

Следующие обязательные части (не уменьшать объём цели):
1. Windows SCM/DPAPI/ACL/WTS/pipe/file-lock pilot. Linux E2E уже использует
   настоящий HTTP/backend/PostgreSQL; GUI/process/IPC boundary остаётся simulated.
2. Проверка bootstrap install/reverse migration на Windows; GUI release metadata
   должна совпадать с manifest (CI уже передаёт HubShellReleaseId).
3. Настроить реальный host CLI/cron и credentials вне Git, Git stack с auto-update off,
   проверить mirror mount и сохранение digest на установленном Dockhand.
   Проверить весь server stage на отдельном Compose-стенде
   (пока реальным был только PostgreSQL dump/restore).
   Браузерная проверка карточки статуса; публикация/настройка pipeline и стенда.
4. Сквозные Linux/dev-host проверки, затем доступный Windows pilot; не выдавать source/build
   за SCM/WTS/file-lock proof. В самом конце пересобрать EXE, >100 MB упаковать;
   HubShell.zip оставлять EXE-only. Текущий release пока не заменён.

Тестовая PostgreSQL: отдельный контейнер hubshell-cicd-postgres, 127.0.0.1:55439,
DSN postgresql+asyncpg://postgres@127.0.0.1:55439/postgres. Рабочие базы/TrueNAS не менялись.
Последняя проверка: 238 .NET tests; 65 scoped backend tests, включая .NET HTTP E2E,
с реальной PostgreSQL; 18 scoped frontend tests и production build;
5 packager, 6 signed mirror, 7 CD coordinator/report,
4 server-order, 4 real loopback HTTP/auth/merge и 8 CD runner tests.
Real PostgreSQL dump/restore проверил контрольную строку,
удаление временной БД и повторное использование проверенного backup.
Server-order тесты подменяют Compose subprocess; это не доказательство реального
рестарта/миграций через Compose. 13 admission/snapshot checks — предыдущий срез.
Ruff/format/actionlint и Compose config validator проходили локально; GitHub CI ещё не запускался.
Миграции 0085/0086: downgrade до 0084 и повторный upgrade прошли в тестовой БД.
Windows GUI host и standalone watchdog компилируются на Linux, native не проверен.
Повторная инвентаризация Dockhand: environment 1/socket, repository HubShell/main
по-прежнему compose.yaml, Git stacks=[]; mutations NAS не выполнялись.
Запрошено разрешение на отдельную ветку ci/client-updates и запуск CI; ответа пока нет.
Подробности API и локального протокола: [PROTOCOL.md](PROTOCOL.md).

Финальный локальный аудит: failed park polls сохраняют принятые installed/rolled_back
отчёты до explicit retry; прежняя ветка агента могла затереть их общим failed.
Добавлены два unit cases и проверка повторного опроса обоих hosts в E2E.
238 .NET и обновлённый TCP/HTTP E2E прошли. Готовится локальная поставка из
зафиксированного source commit; Windows/TrueNAS/публикация по-прежнему не завершены.
