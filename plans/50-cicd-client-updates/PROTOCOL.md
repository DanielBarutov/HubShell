# Протокол обновления v1

2026-11-06: обычные обновления переходят на независимые задания ПК;
общий протокол ниже сохраняется для совместимости до завершения перехода.
Новая политика: [INDEPENDENT-UPDATES.md](INDEPENDENT-UPDATES.md).

Базовый путь: `/api/v1/client-updates`. JSON — snake_case; идентификаторы — UUID.
Меняющие operator-действия требуют JWT operator с `workstations.manage`;
проверка есть в application service. PostgreSQL обязателен, in-memory fallback нет.
Барьер допуска проверяет активные сеансы также архивных PC; они не обновляются,
но архивирование не является способом обойти условие отсутствия игры.
Ошибки: 400 invalid_argument, 401 unauthenticated, 403 permission_denied,
404 not_found, 409 conflict, 503 dependency_unavailable. Изменения проходят аудит.

## Удостоверение службы

`POST /credentials/{device_id}` выдаёт один случайный credential_secret для
уже enrolled PC/installation_id; повтор означает ротацию. БД хранит только SHA-256.
`DELETE /credentials/{device_id}` отзывает credential. Секрет не сохранять в Git,
обычном server.ini или пользовательском AppData.

`POST /agent-token`: device_id, credential_secret. Возвращает короткий access_token,
expires_in и token_type. JWT имеет отдельный subject_type=updater и только
client_updates.poll/report. Он не является GUI device JWT и не допускается
к V2 financial ingress. Каждый агентский запрос проверяет актуальный credential_id
и enrollment; ротация/отзыв/смена установки отзывает уже выданные JWT. Ответы
с секретом/токеном имеют no-store; validation errors не повторяют secret в ответе.

## Управление доставкой

- `GET /current`: operator/workstations.manage, no-store; deployment=null либо
  последняя доставка с confirmed/total и полным devices[]. Статусы назначает
  backend: confirmed, unreachable, failed, rolled_back, active_session,
  pending_facts, not_ready, waiting_gui, ready, installing, verifying.
  Старые раунды не засчитываются; ready=false отличается от готовности.
- `POST /`: operation_id, release_id, executable_sha256. Цели — все неархивные PC,
  включая недоступные/выключенные; Xbox не включается. Ключ операции проверяет
  совпадение содержимого. Незавершённая доставка не вытесняется следующей.
  Повтор operation_id сравнивает release/hash/автора и возвращает исходный
  snapshot целей; изменение парка между потерянным ответом и повтором не
  создаёт другую доставку. Новые PC добавляются через refresh-targets.
- `GET /{id}`: полный сохранённый отчёт, фаза, round_id, цели, отчёты службы и GUI.
- `POST /{id}/refresh-targets`: только polling; включает новые PC, создаёт новый
  раунд и требует повторного опроса. Не исключает прежние цели и не заменяет identity.
- `POST /{id}/prepare`: свежие ответы всех, точная финансовая сверка, постоянный
  Sessions barrier и Workstations membership freeze в одной транзакции. Новый
  round_id и пустые отчёты требуют финального опроса уже под барьером.
- `POST /{id}/server-ready`: CD сообщает о выполненных проверках сервера.
- `POST /{id}/authorize`: все PC готовы в новом раунде, сервер готов; создаёт общий
  допуск. Подтверждение Kafka ingress не заменяет подтверждение финансового chain.
- `POST /{id}/retry`: после failed, новый раунд/повторная проверка сервера, барьер
  не снимается. Переделывать EXE, который уже соответствует выпуску, не требуется.
- `POST /{id}/finish`: только после всех двойных подтверждений; снимает Sessions
  barrier и Workstations freeze атомарно. Ошибка/откат одного PC удерживает весь парк.

## Агент

`GET /agent/current?instance_id=UUID` возвращает только собственное задание:
backend_protocol=1, deployment=null либо id, round_id, release_id, executable_sha256,
phase, block_gui, may_install, last_sequence, report_stage, gui_confirmed. Ответ no-store.
Завершённая последняя доставка также видна агенту для снятия локальной блокировки.
may_install привязан к instance_id последнего принятого ответа. Сам poll не
заменяет конечное разрешение начала установки.

`POST /{id}/reports`: round_id, sequence (>=1), instance_id, active_session,
pending_facts, ready, stage, installed_sha256, error_code; дополнительно session_id,
last_sequence, last_payload_hash последнего сохранённого V2 ledger. При отсутствии
ledger — null/0/null. Время получения назначает сервер. Повтор sequence не меняет
содержимое и не продлевает свежесть. Устаревший раунд отклоняется.
Необязательный running_release_id передаёт версию GUI для отчёта, не заменяя
GUI confirmation. Первый известный release сохраняется в old_releases устройства
и переживает сброс раунда; служба не может этим полем подтвердить успешную замену.

До закрытия GUI и замены EXE агент вызывает `POST /{id}/begin-install` с теми же
полями готовности, новым sequence и stage=installing. Сервер атомарно проверяет
общее разрешение, пробный PC, instance/round, отсутствие локальных блокеров и
подтверждённый финансовый checkpoint, сохраняет начало и отвечает authorized=true.
Только после этого можно менять файлы. Повтор того же запроса идемпотентен;
новый старт после failed запрещён. Reports не заменяет begin-install.

Пробный PC — первый device_id по сортировке. Остальные не получают begin-install,
пока служба пробного PC не подтвердила хеш и GUI не подтвердил release_id.
Этапы: ready, installing, verifying, installed, failed, rolled_back. installed
принимается только после начала установки и с точным executable_sha256.

## GUI и локальное состояние

Обычный device JWT с workstations.connect использует `GET /gui/current` и
`POST /{id}/gui-confirm` (release_id). Updater JWT не может подтвердить GUI.
GUI подтверждает только собственную встроенную HubShellReleaseId после recovery
и проверки отсутствия активного ledger/неотправленных фактов.

Локальный канал Windows — Named Pipe, ACL только текущему пользователю и SYSTEM.
GUI проверяет identity клиента SYSTEM; service-side клиент проверяет PID,
путь и Windows-сессию сервера pipe перед отправкой команд. Формат IPC=1; поля
готовности и финансового checkpoint обязательны даже при null/0. Команды — status,
prepare, close, release; shell-команд нет. Закрытие допускается только при наличии
соответствующей постоянной локальной блокировки и отсутствии активного ledger
и pending facts. Сам блок не удаляет ledger и не останавливает игру.

Machine-owned `.client-update.json` в каталоге установки сохраняется атомарно
с FlushToDisk. GUI читает блок до входа; повреждение означает fail closed. Снятие
блока — после completed, не по таймауту. Токены и server.ini файл замены не затрагивает.

## Пакет

Mirror: `/releases/{release_id}/{release.json|release.json.sig|HubShell.zip}`;
GAMECLUB_CLIENT_RELEASE_ROOT — корень локального зеркала. Произвольные файлы и
выход из корня не обслуживаются. Артефакты публичные, служебные секреты в них не входят.

release.json schemaVersion=1: releaseId, commit (40 hex), runtime=win-x64,
executableName=HubShell.exe, executableSha256/Bytes, archiveSha256/Bytes,
min/maxUpdaterProtocol и min/maxBackendProtocol. JSON camelCase — контракт пакета,
не HTTP API. Подпись точных JSON bytes: RSA >=2048, SHA-256, PKCS#1 v1.5,
отдельный бинарный release.json.sig. Доверенный public key закрепляется отдельно;
экспортированный release-public-key.pem из загрузки не является корнем доверия.
ZIP содержит только HubShell.exe, без ссылок/каталогов/дополнительных файлов.

server-release.json (отдельная RSA/SHA-256 подпись server-release.json.sig):
schemaVersion=1, releaseId, commit, images. images содержит ровно
HUBSHELL_BACKEND_IMAGE, HUBSHELL_FRONTEND_IMAGE, HUBSHELL_STEAM_GUEST_IMAGE;
разрешён только ghcr.io/danielbarutov/hubshell/{backend,frontend,steam-guest}
с @sha256 digest. releaseId/commit обязаны совпасть с подписанным клиентским
manifest. images.env — удобный экспорт, не источник доверия для CD.
CLI зеркала проверяет обе подписи/ZIP и публикует каталог атомарно; повтор
не перезаписывает уже опубликованный выпуск. Server metadata не раздаётся GUI.

## Граница готовности

HTTP/auth, agent loop/pipe и защищённый bootstrap реализованы в исходниках.
CLI связывает mirror/coordinator/report/server-stage; его запуск на TrueNAS,
полный Compose stage и Windows pilot ещё не проверены. Текущая граница
хранится в STATUS.md; этот документ не является доказательством native готовности.

## Независимое задание ПК — реализованный первый этап, 2026-11-06

`POST /` дополнительно принимает необязательный `device_id`. При его наличии
создаётся `independent=true`, ровно одна цель; без него остаётся старое общее
задание. Несколько независимых заданий разных ПК допустимы одновременно;
пересечение по устройству/рабочей станции и сочетание с незавершённым общим
заданием запрещены. Повтор operation_id не может менять режим и устройство.

При `/agent-command` сервер автоматически продвигает независимое задание:
свежая готовность → финансовая сверка/атомарный барьер одного ПК → новый
раунд → повторная готовность/авторизация → отчёт службы + GUI → completed
и снятие только своего барьера. Нет глобального membership freeze и ожидания
пробного ПК. При ошибке задание остаётся failed до operator retry.

Миграция 0087 разрешает независимые задания, прежние payload читаются как
`independent=false`. Downgrade при нескольких активных заданиях откажет
транзакционно, сохранив данные; сначала нужно завершить задания.
Автоматическое назначение выпуска, его минимальная совместимость и общий
статус всех независимых заданий ещё не подключены.

## Назначение выпуска — 2026-11-06

`POST /policy` (operator/workstations.manage): operation_id, release_id,
accepted_release_ids (до 31 дополнительных идентификаторов). Target всегда
включается в список. Идентификаторы непрозрачны: минимальная совместимость
задаётся явным перечнем разрешённых выпусков, без сравнения строк/semver.
Повтор operation_id должен совпадать по содержимому/автору; повтор старой
операции возвращает старую запись, не делает её текущей заново.
Один release_id не может получить другой executable_sha256.

До сохранения проверяются RSA/SHA-256 подпись release.json закреплённым
ключом, протоколы backend/updater, размеры/хеши ZIP и единственного EXE.
GAMECLUB_CLIENT_RELEASE_PUBLIC_KEY — путь к доверенному PEM в контейнере;
ключ нельзя брать из загруженного выпуска. Без ключа/зеркала — 503,
повреждённый/несовместимый пакет — 409. Проверка файлов не блокирует event loop.
`GET /policy` (тот же operator permission) возвращает {policy: ...} с no-store.

Опрос `/agent/current` атомарно создаёт независимое задание из текущей политики
для enrolled PC; одновременные опросы не создают дубликаты. При незавершённом
задании сохраняются его выпуск и фаза, в том числе failed. Следующее назначение
будет применено после завершения прежнего задания. Если последняя завершённая
доставка уже подтвердила тот же target/hash/workstation, нового задания нет.

Совместимость пока только хранится: запрет нового входа по этому списку
ещё не подключён. Автоматическая публикация policy после CD и конфигурация
ключа в поставке также остаются следующими задачами.

## Допуск по запущенному выпуску — 2026-11-06

`GET /gui/current?release_id=<running>` сохраняет наблюдение GUI и возвращает
`release_allowed` вместе с deployment. Device JWT, полученный через enrollment,
содержит installation_id; наблюдение принимается только при совпадении
с текущей установкой ПК. Старый JWT установки/токен без привязки — 401.
Без release_id наблюдение не обновляется; при активной policy release_allowed=false.
Это сообщение доверенного GUI, а не удалённая аттестация бинарника.

Sessions получает проверку через публичный application-порт: новый сеанс,
реактивация и целевой ПК переноса требуют наблюдения не старше 30 секунд
с совпадающими device/workstation/installation и разрешённым release_id.
Наблюдение не заменяется heartbeat/updater-report. Обновление policy и
наблюдения сериализуется с выдачей нового доступа тем же admission lock.
Активная сессия, её signed snapshot refresh и подтверждение финансовых фактов
продолжаются по прежним правилам. Xbox от Windows release policy не зависит.

Для выдачи нового snapshot до создания сессии writer получает workstation_id:
барьер другого ПК больше не блокирует неизвестный ещё session_id.
Для неизвестной сессии без workstation_id сохранена прежняя закрытая проверка.
Kafka reconciliation не получает новый compatibility gate: подписанные ранее
финансовые факты нельзя отвергать из-за последующего обновления policy.

GUI блокирует новые входы до успешной проверки при старте и после обрыва
опроса, сохраняя уже начатую игру. IPC release не снимает блок несовместимости.
Вместо ожидания всего парка показывается проверка/обновление этого ПК.
Если GUI сообщил старый EXE после завершённой доставки, следующий опрос
службы создаёт отдельное repair-задание, не переиспользуя старый completed.

## Источник target для периодической доставки

Новые CI-образы содержат io.hubshell.release-id. `sync-client-release.py`
берёт эту метку у фактически запущенного backend, а не GitHub latest;
проверяет подписанный server manifest и фактические RepoDigests приложений.
Перед policy POST он повторно наблюдает стек, чтобы смена сервера во время
загрузки не опубликовала старый target. Backend, собранный новым CI, дополнительно
сверяет target с GAMECLUB_SERVER_RELEASE_ID; прямой API не обходит эту проверку.
Dev/test без идентификатора образа сохраняет явный тестовый сценарий.

Публикация mirror root ключа использует только переданный операторский public key.
Ключ из downloaded release не считается доверенным. Несовпадение уже
закреплённого root ключа требует отдельной ротации, а не автоматической замены.
Exit 0 периодической задачи подтверждает policy, не завершение всех ПК.

## Operator current — весь парк, 2026-11-07

При активной policy GET /current возвращает deployment с mode=independent,
id=policy.operation_id и release_id целевого выпуска. Цели — все неархивные
PC с device identity, даже без задания/ответа; disabled PC остаётся отдельной
строкой. Для каждой строки выдаются assigned_release_id и deployment_id
(последнего задания, либо null), running_release_id, received_at и error_code.
Добавлены статусы awaiting_agent и disabled. Последние задания читаются одним
пакетным SQL-запросом; передавать всю историю доставок в UI не требуется.

Confirmed требует target/hash и двойного подтверждения последнего задания.
Более новое наблюдение другого EXE или смена installation не наследует успех.
Completed при пустом парке не выдаётся. Phase=failed в независимой сводке
означает ошибку отдельных ПК, не общий барьер. Если действует незавершённое
legacy coordinated обслуживание, сохраняется прежняя форма /current и его
предупреждения; policy не маскирует существующий общий барьер.

Поле mode необязательно для совместимости прежнего /current. Frontend
сохраняет loading/empty/error/timeout/poll teardown. Статусы считает сервер;
frontend показывает подписи и имена рабочих мест.

## Явный повтор на исправленный выпуск

POST /{deployment_id}/retry-current, body {operation_id: UUID}, требует
operator/workstations.manage и failed независимое задание. Backend выбирает
текущую policy и повторно проверяет её пакет/хеш. При отсутствии policy/ключа,
при active session или непроверенном пакете исходный failed snapshot сохраняется.
Предыдущая попытка архивируется в payload с автором/временем и retry operation_id;
повтор запроса не меняет round и не очищает новые отчёты. Initial create operation
продолжает ссылаться на исходные release/hash и тот же deployment resource.
Барьер не снимается; GUI принимает новый round того же deployment, скачивает
новый пакет и проходит прежний begin-install/verify/confirm. Legacy /retry остаётся
повтором прежнего выпуска для coordinated CD.
