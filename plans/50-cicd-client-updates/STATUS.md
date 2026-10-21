# Текущее состояние плана 50

Статус: in_progress — ветка опубликована, CI прошёл, копия в Dockhand запущена.
Windows pilot отложен пользователем до 2026-10-20; полная цель не завершена. Аудит: [AUDIT.md](AUDIT.md).
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
   Браузерная проверка карточки статуса. CI и начальный запуск стенда выполнены;
   полный CD server-stage/cron ещё не проверен.
4. Доступный Windows pilot; не выдавать source/build за SCM/WTS/file-lock proof.
   Папка release обновлена из CI commit e300b4b2e03092fdb195ecfd3f7212cd513b82d1;
   при дальнейших runtime изменениях пересобрать его повторно.

Тестовая PostgreSQL: отдельный контейнер hubshell-cicd-postgres, 127.0.0.1:55439,
DSN postgresql+asyncpg://postgres@127.0.0.1:55439/postgres. Рабочие базы не менялись; на TrueNAS создана отдельная пустая копия.
Последняя проверка: 238 .NET tests; 69 scoped backend tests, включая .NET HTTP E2E,
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
238 .NET и обновлённый TCP/HTTP E2E прошли. Локальная поставка обновлена из
source commit 0c9d514a9d18c0cd7b36bf07e2ea8b55b3c0452a (ветка ci/client-updates):
GUI 108204802 bytes → EXE-only HubShell.zip 46524393 bytes; watchdog 68688118;
HubShell.Setup.zip 76279360 bytes. Оба win-x64 self-contained single-file без
внутреннего сжатия. PE, embedded release id, RSA signature, ZIP/checksums,
installer parity проверены; server.ini сохранён. Старый bundle — output/cicd-release-0c9d514/previous-release.
Signing key — вне Git в ~/.config/hubshell-cicd (private 600, dir 700);
в release только public key/signature. Signed server manifest/images отсутствуют
до CI; эта локальная поставка не включает реальную автодоставку.
Windows/TrueNAS/публикация по-прежнему не завершены.

Завершены прямые PG races client/guest/transfer с barrier в обоих порядках;
11 admission checks, общий scoped набор 69 passed. C# runtime/готовые EXE
после этой проверки не менялись. Дальнейшая самостоятельная локальная работа
не закрывает live CI/NAS/Windows evidence; нужны ответ и внешний доступ.

## 2026-10-19 — опубликованный выпуск и первый запуск NAS

Пользователь разрешил публикацию и запуск контейнеров, Windows PC будет завтра.
Ветка ci/client-updates опубликована. CI run 39296815640 — success, commit
 e300b4b2e03092fdb195ecfd3f7212cd513b82d1. Signing secret настроен вне Git.
Ручной dispatch нового workflow без файла в main вернул 404; добавлен push trigger
только для этой ветки. Первый CI выявил наследование PostgreSQL DSN старыми
in-memory API tests; DSN миграций ограничен командой alembic, повтор прошёл полностью.

Dockhand: git stack 1 hubshell-test, environment 1, compose.truenas.yaml,
branch override ci/client-updates. Auto-update/webhook выключены. Отдельные
случайные секреты сохранены в Dockhand secret storage, рабочие volumes не переносились.
Все три GHCR image доступны анонимно; digest совпали с подписанным server manifest.
Deploy run 59 success: 22 running, два init-контейнера exit 0, restart count 0.
Проверены HTTP live/ready, operator login, workstations=[], current deployment=null,
frontend proxy ready и настоящий gRPC SystemService.GetHealth (ok).
Kafka consumers получили partition assignment, Dramatiq выполняет периодические jobs.

Порты пока привязаны к 127.0.0.1 NAS: 3100/8100/51051/8200. Для LAN ожидается
локальный IP от пользователя; 0.0.0.0 автоматически не выставляется.
CI artifacts скачаны в output/ci-e300b4b, подписи обоих manifests/commit/hash/ZIP
проверены закреплённым ключом. release/ обновлён из этого CI без изменения server.ini:
HubShell.exe 108233738 bytes, EXE-only HubShell.zip 46550584 bytes,
HubShell.Setup.zip 76326753 bytes. BUILD-INFO содержит provenance и hashes.
Это первый запуск копии, не сквозная CD-проверка server-stage/cron/Windows update.

## 2026-10-21 — упорядочивание Compose и веток

Согласовано пользователем: серверный Git stack отслеживает main; последующие
изменения идут feature-ветками. Нормальное имя стека/проекта — hubshell.
compose.local.yml — полный прежний Linux build-контур (project gameshell для
сохранения developer volumes). compose.deploy.yml — самостоятельный обычный YAML,
без extends/!reset/!override, с digest images, закрытыми infra ports и обязательными
server secrets. Это устраняет неизвестные теги у графа Dockhand.
CD executor/persist_images используют проект hubshell, зеркало определяется по
реальному mount backend, а не по угаданному имени volume. По уточнению пользователя старые тестовые
volumes не переносятся: hubshell запускается с новыми пустыми volumes. Свои данные
с клиентами и ПК пользователь подключит позднее. Старые контейнеры должны быть
остановлены до запуска нового проекта (общие host ports).
CI: main/tag builds, PR checks без публикации images. Auto-update парка остаётся off.

## 2026-10-21 — результат смены проекта

main 48fb647, CI 39576497937 success. Подписи client/server manifests,
commit/hash/ZIP проверены; digest трёх images сохранены в Dockhand.
Git stack 1 переименован в hubshell, branch main, compose.deploy.yml,
HUBSHELL_BIND_HOST=192.168.0.21. Все 10 secret vars сохранены.
Deploy 151 success: 24 контейнера созданы, 22 работают, migration/topics exit 0.
HTTP страницы и /health/ready через frontend: 200; operator login: 200;
/api/v1/clients и workstations: 200, пустые; current deployment=null.
SystemService.GetHealth: ok/gameclub-backend. Имена контейнеров hubshell-*.
Старые test-контейнеры остановлены и удалены без удаления volumes; старые
checkout-файлы перемещены в backups Dockhand. Тестовые данные не переносились.
Новые hubshell_* volumes пустые; пользователь позже подключит собственную БД/ПК.
Секреты копии сохранены, это не production cutover существующего клуба.
Оставлены только compose.local.yml и compose.deploy.yml; backend infra-only
использует первый файл с сервисами postgres redis. Граф Dockhand принимает YAML
без unknown-tag ошибок (preflight error findings=[]); visual UI не проверен.
Локальная папка release обновлена из того же CI, server.ini сохранён.
Не проверены подключение пользовательских volumes, Windows pilot и full CD cron.

### Инструкция Windows-комплекта

win-client/INSTALL.txt — короткая инструкция двух EXE, остановки службы перед
заменой, сохранения INI/идентичности и start-service.cmd. Packager включает её
как README.txt в Setup ZIP; локальный архив обновлён без пересборки EXE, checksum
и BUILD-INFO актуализированы. 5 packaging tests прошли, native Windows не проверен.
