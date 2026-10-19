# Проверка готовности плана 50

Полная цель не достигнута. Локальная реализация и поставка готовы;
CI и первый запуск NAS выполнены; полный server-stage/cron и native-проверки ещё требуются.
Актуальные свидетельства: [STATUS.md](STATUS.md), раздел первого запуска NAS.

| Требование | Проверенное свидетельство | Итог |
| --- | --- | --- |
| Договорённости: все PC, offline блокирует парк, ошибка держит парк закрытым | PRODUCT-CONTRACT трёх компонентов; domain/HTTP/E2E сценарии | Реализовано локально |
| Durable deployment, identity/JWT, два раунда, независимые подтверждения | Реальная PostgreSQL/HTTP, отдельные updater и GUI JWT; rotation/revoke; 69 scoped backend tests | Проверено в указанном объёме |
| Вход клиента/гостя/перенос не обходят barrier | 11 admission PG checks: оба порядка client/guest race, оба порядка transfer race, recovery grants, reactivation/move | Проверено на owner repository/application boundaries |
| Подписанный ZIP, staging, install/rollback/recovery | 238 .NET tests и реальные RSA/ZIP/files; Linux UpdateAgentHost | Windows adapter runtime не доказан |
| Pilot, отказ второго PC, explicit retry, 2/2, restart | Два .NET agents через TCP HTTP; остановка/новый PID backend; PostgreSQL; JSON/text report | GUI/process/IPC simulated, не production fleet proof |
| Настройки оператора | 18 scoped frontend tests и production build; server-owned numerator/denominator | Browser layout не проверен: CUA browsers=[] / iab unavailable |
| Локальная поставка | release/BUILD-INFO.json, PE x64, RSA, SHA256SUMS, ZIP entry/hash, сохранённый server.ini | Выполнено; native запуск не проверен |
| CI и согласованный server/client release | Workflow/actionlint и packager tests; source в локальной ci/client-updates | CI 39296815640 success, три публичных digest проверены |
| TrueNAS Git stack, host executor/cron, mirror, backups/migration/readiness | Compose config validator, server ordering tests; реальный pg_dump/restore отдельной PostgreSQL | Полный Compose stage и live Dockhand merge не выполнялись |
| Windows bootstrap, SCM/WTS/ACL/DPAPI/pipe/file locks | Компиляция GUI/watchdog, source installer, инструкция обратного перехода | Требуется Windows pilot, Linux этого не доказывает |

## Артефакты

GUI/source build: 0c9d514a9d18c0cd7b36bf07e2ea8b55b3c0452a.
Последующие дополнительные проверки меняют только tests/docs, не C# runtime.

- HubShell.exe: 108204802 bytes; HubShell.zip: 46524393, только HubShell.exe.
- HubShell.Watchdog.exe: 68688118 bytes; HubShell.Setup.zip: 76279360.
- Self-contained win-x64 single-file, внутреннее сжатие выключено.
- Текущие размеры/хеши сверены с BUILD-INFO; INI сравнен с backup byte-for-byte.
- Private signing key находится вне Git; server release manifest/images не подменены
  фиктивными digest. Локальные артефакты не означают включённую CD доставку.

## История блокировки до разрешения публикации

Вопрос о публикации отдельной ветки ci/client-updates и запуске CI отправлен,
ответ не получен. Ожидание этого ответа повторилось в трёх последовательных
goal turns; его отсутствие не считается разрешением. `git ls-remote` подтвердил,
что удалённой ветки пока нет. Remote push и Actions не выполнялись.

После разрешения: опубликовать source/tests, настроить signing secret вне Git,
выполнить CI и проверить фактические digest/доступ к образам; затем создать
отдельную пустую копию на TrueNAS и проверить весь server stage/runner/mirror.
Для закрытия Windows критериев нужен доступный тестовый PC и административный
bootstrap. Текущая рабочая среда — Linux, Windows-поведение не подтверждено.

Не включать общую доставку до native pilot. Не отмечать план выполненным по
одной сборке, unit tests или двум simulated GUI в developer host.
