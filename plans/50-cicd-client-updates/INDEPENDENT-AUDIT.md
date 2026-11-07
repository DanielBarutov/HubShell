# Аудит независимых обновлений — 2026-11-07

Статус: локальные implementation gates закрыты; полный live acceptance не выполнен.
Остаются отложенные пользователем NAS/Windows и ещё не запущенный GitHub CI.
Рабочая папка содержит несвязанные изменения пользователя, они сохранены.
На NAS/Windows подключения не выполнялись по прямому ограничению пользователя.

| Требование | Проверенное свидетельство | Граница / остаток |
| --- | --- | --- |
| Пакет раздаётся сервером по LAN | HTTP file route, signed mirror tests, .NET TCP E2E | Реальный mount NAS и сетевой доступ ещё не проверены |
| ПК получает target при включении | Автоматическое задание в agent poll, independent E2E | SCM/WTS старт на Windows отложен |
| Выключенный/занятый ПК не удерживает другие | PostgreSQL admission и независимый E2E | Нет реальной пары Windows-ПК |
| Новый несовместимый вход блокируется | GUI observation + installation JWT; tests входа/реактивации/переноса и гонки policy | Полный native GUI login не проверен |
| Начатая игра сохраняется | Gate tests и активный guest extension под блоком | Native таймер/окна не проверены |
| Подписанный пакет и восстановление EXE | RSA/ZIP/hash, installer/state tests, bad GUI rollback E2E | Windows locks/DPAPI/ACL/pipe/SCM не проверены |
| Серверный выпуск — источник назначения | Sync image labels/digests tests; настоящий JsonApi publisher → backend → agents | Docker inspect boundary моделируется; GitHub CI и cron ещё не запускались |
| Повторы не дублируют действия | PostgreSQL concurrency, operation IDs, lost-response publisher/agent tests | Native network outage во время установки ещё не проверен |
| Ошибка только своего ПК | Independent rollback/retry E2E, /current read model | retry-current на исправленный target прошёл через TCP/backend/.NET; native остаётся отложенным |
| Карточка всего парка | 5 PostgreSQL projection scenarios, 21 frontend tests, production build, desktop/mobile browser fixture | Браузер использовал fixture данных, не живой NAS API |
| Установочный комплект | Два win-x64 self-contained publish; PE/ZIP/parity/RSA/hash; новая инструкция первого provisioning | Полный установщик не выполнялся на Windows; PowerShell здесь отсутствует |

## Результаты текущего прогона

- 105 backend tests из актуальной release workflow прошли, включая PostgreSQL,
  authenticated HTTP, admission races и два настоящих .NET TCP сценария.
- 241 .NET test прошёл после исправления active guest polling. Есть прежний
  xUnit1031 warning в AvaloniaHostSmokeTests.cs:289; этот тест не менялся.
- 47 standalone packaging/mirror/CD/sync tests: прежний прогон 46 плюс новый
  regression о старых backend-migrate/oneoff контейнерах (10 sync tests).
- Compose validator/actionlint прошли. Scoped Ruff/format/diff-check прошли.
- Ранее проверены production frontend build и карточка при 1100/390 px. Общий
  frontend lint по-прежнему останавливается на двух прежних unused imports
  ChevronDown (AppShell.tsx) и MoreHorizontal (MapScreen.tsx).

## Исправления, найденные при аудите

1. Блок версии прерывал polling активного гостя, включая продления/серверный stop.
   Guard теперь запрещает только новое гостевое право; regression сначала
   воспроизвела потерю продления, после исправления полный .NET набор зелёный.
2. Sync проверял digest исторического backend-migrate до исключения oneoff.
   Старый завершённый контейнер после server stage мог блокировать раздачу.
   Миграционные/oneoff контейнеры исключаются до проверки действующих приложений;
   несоответствие активного приложения по-прежнему запрещает публикацию.

## Локальный кандидат

Папка: `output/independent-updates-local-20261107-2302d734f484/`.
В `package/`: EXE-only HubShell.zip 46 547 440 bytes,
HubShell.Setup.zip 76 325 733 bytes, watchdog ZIP 29 769 448 bytes,
release.json/signature/public key/SHA256SUMS и BUILD-INFO.json.
GUI и watchdog опубликованы self-contained win-x64 без внутреннего сжатия.
Setup содержит оба EXE, скрипты, README и server.ini.example, без machine secrets.

Это локальная сборка незакоммиченного дерева, не опубликованный server/CI release.
SOURCE-INFO.json хранит base commit и hashes исходного snapshot; BUILD-INFO явно
отмечает dirty=true и windows_runtime_verified=false. Более ранний кандидат
5dac547b476a помечен superseded после найденного guest polling дефекта.
Рабочие release/server.ini и release/HubShell.zip проверены по исходным hash и
не заменялись. Приватный ключ подписи остаётся вне Git и вне пакета.

## Закрытие восстановления на исправленный выпуск

POST retry-current и кнопка в карточке ошибок переводят только failed независимый
ПК на проверенную текущую policy. Предыдущие отчёты/GUI confirmations/round/target
архивируются с автором и временем; initial create key остаётся идемпотентным.
ID задания/барьер сохраняются; новый round заново проходит readiness/финансовую
сверку/установку/двойное подтверждение. Повтор operation_id не сбрасывает отчёты.

Сквозной тест использует два подписанных пакета с разными EXE hash: v1 → rollback
второго ПК → backend restart с исправленным server release → JsonApi policy sync →
operator retry-current (и повтор того же запроса) → v2 confirmed. Первый ПК
затем независимо обновляется до v2; возврат старого EXE подтверждённого ПК
запускает repair. HTTP/backend/PostgreSQL/.NET/files настоящие; исполнение GUI,
процессы и IPC в Linux-host моделируются. Это не доказательство автоматического
восстановления произвольно повреждённого Windows EXE, который не может запуститься.

UI: 21 tests проверяют read/poll/timeout, retry key при потере ответа, новый ключ
для следующего failed round и отмену при закрытии. Browser fixture проверила
нажатие кнопки для выбранного ПК, новый статус и сохранение пяти строк без
переполнения страницы. Production build и actionlint прошли; общий frontend lint
имеет две ранее перечисленные несвязанные ошибки.

## Остаток до полного live acceptance

- Публикация исходников/запуск нового GitHub workflow не выполнялись. Без
  выпущенных signed manifests/images этот локальный кандидат не является
  развернутым server release; production deploy не объявляется завершённым.
- NAS, Dockhand runtime, настоящий volume mount, cron и Windows SCM/WTS/DPAPI/ACL/
  pipe/file-locks проверить по CLIENT-UPDATE-RUNBOOK.md после возвращения доступа.
  Пользователь прямо сообщил недоступность сервера и Windows на неделю.
- Код/локальные regression gates и кандидат готовы для этого пилота; новых
  незакрытых implementation-частей аудит не выявил. Нативные/внешние пункты
  нельзя честно закрыть доступными Linux-тестами или повторным запуском mock suite.
