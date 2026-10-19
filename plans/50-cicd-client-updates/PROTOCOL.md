# Протокол обновления v1

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
