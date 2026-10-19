# Отдельная копия на TrueNAS

Текущий запуск 2026-10-19: Git stack 1 hubshell-test, env 1, ветка
ci/client-updates, compose.truenas.yaml. CI 39296815640 success; deploy 59 success.
22 running, два init exit 0, HTTP/auth/frontend proxy/gRPC проверены.
Порты на loopback NAS; ожидается локальный IP для LAN. Auto-update/webhook off.
Подробности и оставшиеся критерии: [STATUS.md](STATUS.md).

Ниже первоначальный план и процедуры, исторические сведения об отсутствии
стека относятся к инвентаризации до первого запуска.

Согласовано 2026-10-19: рабочий backend находится на другом ПК. На TrueNAS
создаётся отдельная копия; перенос рабочих volumes пользователь выполнит позже.
GitHub Actions + GHCR и публичные образы согласованы. Автоматическая доставка на игровые ПК пока
отсутствует и не включается этим workflow.

## Что уже подготовлено

- `.github/workflows/release.yml`: запуск по тегу v* или вручную; тесты клиента,
  self-contained win-x64 GUI и службы без single-file compression, три образа
  в GHCR (backend, frontend, steam-guest), GitHub Actions artifact с ZIP,
  SHA256SUMS, commit.txt и images.env с digest-ссылками. Для тегов создаёт
  draft GitHub Release; публикация draft и автодоставка ещё не настроены.
  Отдельный backend job до сборки применяет миграции и запускает scoped тесты
  deployment/admission на PostgreSQL. После push образов подписывается
  server-release.json с digest каждого образа и тем же commit/release_id.
- scripts/build-client-release.py создаёт release.json и RSA/SHA-256 подпись
  release.json.sig. Нужен GitHub secret CLIENT_UPDATE_SIGNING_KEY_PEM с RSA-ключом
  не менее 2048 бит. Без него CI прекращает выпуск. Закрытый ключ в артефакты
  не попадает. release-public-key.pem — экспорт для первоначального закрепления
  доверия; агент не должен брать доверенный ключ из скачанного выпуска.
  ZIP детерминированный, EXE-only, проверяется вложенный хеш и предел 100 MB.
  Runtime updater подключён в исходниках службы: подписанный пакет не равен
  разрешению установки. Полная CD-интеграция ещё не завершена.
  HubShell.Setup.zip — отдельный bootstrap-комплект двух EXE, установщиков и
  server.ini.example. HubShell.zip по-прежнему содержит только HubShell.exe.
- `compose.truenas.yaml`: все сервисы исходного Compose через extends,
  без source build; отдельный project `hubshell-test` и отдельные именованные тома.
  Относительные observability mounts требуют полного checkout репозитория.
  Backend HTTP получает gameclub-client-releases volume read-only;
  GAMECLUB_CLIENT_RELEASE_ROOT указывает внутрь этого тома.
- Installer нового исходного комплекта регистрирует отдельный
  HubShell.Watchdog.exe; текущая папка release с прежними бинарниками не меняется.

## Реально обнаружено через Dockhand MCP

Dockhand 1.0.53, environment 1 `Production`, локальный Docker socket.
Есть repository 1 HubShell с main, но его composePath `compose.yaml` не существует
в текущем checkout. Git stacks пока нет. Registry только Docker Hub без credentials.
Работающий стек — ix-dockhand. При первом list_environments был fetch failed,
повтор успешно вернул окружение; validate_config подтвердил credentialsValid.
Никакие стеки, образы и тома на сервере в этом срезе не изменялись.

## Следующие действия для первого запуска

1. Опубликовать изменения Git и запустить workflow. Это отдельное действие:
   локальная реализация не означает уже опубликованные файлы/образы.
2. После первой сборки переключить три GHCR packages в public (согласовано
   пользователем). GITHUB_TOKEN workflow не делает их public автоматически.
   До этого анонимная загрузка на TrueNAS может не работать; проверить pull.
3. Создать Git stack `hubshell-test`, environment 1, путь
   `compose.truenas.yaml`. Отключить auto-update/webhook до реализации барьера.
4. Указать три HUBSHELL_*_IMAGE из images.env одного выпуска, отдельные
   случайные секреты копии через Dockhand secret storage. Не копировать ключи
   и идентичности рабочих ПК. GAMECLUB_ENVIRONMENT=dev допустим только для
   изолированной пустой копии с её dev operator; перед переносом — отдельный
   production-check текущего config и секретов, не простая смена флага.
5. По умолчанию порты копии привязаны к loopback TrueNAS. Для доступа из LAN
   явно задать HUBSHELL_TEST_BIND_HOST приватным адресом TrueNAS. Порты:
   HUBSHELL_TEST_FRONTEND_PORT=3100, HTTP_PORT=8100, GRPC_PORT=51051,
   STEAM_GUEST_PORT=8200. Не перенастраивать игровые ПК на копию.
6. Запустить пустой стенд; проверить миграции, health, API, вход оператора,
   Kafka workers и frontend. Readiness и реальные запросы проверять отдельно:
   socket health gRPC из исходного Compose не доказывает работоспособность API.
7. Перед переносом пользовательских volumes остановить копию и рабочие
   писатели, зафиксировать версии схемы/образов и проверить backup/restore.
   Простой запуск новой миграции на перенесённых данных не является проверкой
   совместимости. Никогда не применять down -v.

Локальная проверка структуры без запуска: `python3 scripts/check-truenas-compose.py`.
Нужен Compose 2.24.4+ для reset/override. CI не заменяет Windows pilot службы.

## Подключение службы на одном PC (проверка Windows ещё требуется)

На каждом PC нужен собственный ответ выдачи credential API (device_id,
installation_id, credential_secret) в защищённом enrollment JSON. Секрет
нельзя помещать в release, Git, server.ini или общий для парка файл.
Установщик сохраняет только DPAPI-зашифрованный секрет с отдельным ACL.
Входной JSON остаётся у администратора; после настройки его следует удалить
из места передачи. Публичный RSA-ключ передаётся доверенным способом отдельно
от скачанного выпуска и закрепляется при установке.

После завершения сессий и закрытия GUI, из повышенного PowerShell:

```powershell
.\install-windows.ps1 -PublishPath C:\GameClub -InstallPath C:\GameClub `
  -RegisterWatchdogService -UpdaterEnrollmentFile C:\Admin\pc-enrollment.json `
  -UpdateBackendAddress http://SERVER:8100 -UpdatePublicKeyPath C:\Admin\release-public-key.pem
```

Относительные пути входных файлов разрешаются от каталога install-windows.ps1.
Существующий watchdog переносится только из этой же папки и только с LocalSystem.
Без enrollment установка остаётся службой восстановления без HTTP updater.
Повторная установка проверяет существующий защищённый конфиг до старта службы.

Обратный переход на legacy host — только вручную при закрытом парке: остановить
единственную HubShell.Watchdog и вернуть её binPath на
`"C:\GameClub\HubShell.exe" --watchdog-service`, сохранив LocalSystem и каталог.
Не создавать вторую службу, не удалять journal/ledger и не снимать серверный барьер.
Legacy host не выполняет HTTP updates; такой переход не подтверждает завершение CD.

## Зеркало и серверный CD stage — исходники, ещё не полный runner

`python3 scripts/mirror-client-release.py --release-id vVERSION --mirror-root /mirror
--public-key /trusted/release-public-key.pem` скачивает только фиксированный
репозиторий DanielBarutov/HubShell, проверяет клиентскую и серверную подписи,
совпадение release/commit, ZIP/hash и допустимые GHCR digest. Выход — проверенный
JSON с публичными metadata. Незавершённая загрузка не видна backend; существующий
выпуск не переписывается. Путь /mirror должен быть смонтирован в тот же volume,
который backend видит read-only; полный runner пока не связывает эти mounts.

`client_update_cd.py` содержит advancement/report: prepare → серверный этап →
server-ready → authorize → finish; 409 ждёт, failed не снимает барьер. Это ядро,
пока не самостоятельный daemon. `server_deployment.py` обновляет только
application services проекта hubshell-test без обновления infra/down -v:
stop writers, backup обеих БД, полное pg_restore во временные БД с их удалением,
миграция, app-only up --wait, GetHealth через настоящий SystemService и frontend
smoke. При ошибке backup/migration разрешения GUI не выдаются; автоматического
отката схемы нет. Требуется свободное место под dump и временные restore DB.
Полный Compose stage на стенде ещё не проверен, только отдельный реальный
PostgreSQL backup/restore и тесты порядка команд.

## Локальный CD CLI

`scripts/deploy-release.py` запускается на самом Docker host: Python 3.11+,
OpenSSL, Git и Docker Compose 2.24.4+. Он получает host mountpoint тома
`hubshell-test_gameclub-client-releases` через docker volume inspect. Удалённый
Docker daemon/Docker Desktop без доступа к этому host path здесь не поддерживается.
Рабочая директория — отдельный checkout HubShell на NAS, не пользовательская
папка разработки. После проверки подписей CLI fetch/checkout делает detached
checkout ровно подписанного commit; существующие tracked изменения запрещены.

Вне Git нужны: закреплённый public key; stack.env с теми же секретами, что Git
stack Dockhand; backend-token.json (ответ operator login, access_token/refresh_token);
dockhand-token.json (`{"access_token":"..."}`). Оба token файла и stack.env —
chmod 600; job-root — chmod 700. Значения токенов не передаются в аргументах CLI,
отчётах или cron log. Backend refresh сохраняет новый refresh token атомарно.
HTTP допускается только на loopback/private IP; для внешнего адреса нужен HTTPS.

Пример кандидата запуска (пути заменить на реальные пути NAS после bootstrap):

```bash
python3 /mnt/POOL/hubshell/checkout/scripts/deploy-release.py \
  --public-key /mnt/POOL/hubshell/secrets/release-public-key.pem \
  --job-root /mnt/POOL/hubshell/cd-jobs \
  --env-file /mnt/POOL/hubshell/secrets/stack.env \
  --token-file /mnt/POOL/hubshell/secrets/backend-token.json \
  --dockhand http://127.0.0.1:9000 \
  --dockhand-token-file /mnt/POOL/hubshell/secrets/dockhand-token.json
```

Без --release-id берёт unfinished active job, а после его завершения — последний
опубликованный GitHub Release. Draft недоступен этому механизму. --release-id vTAG
выбирает конкретный выпуск, но не вытесняет unfinished job. Один host lock на весь
job-root; второй вызов выходит без изменений. Команду можно вызывать Cron Job
TrueNAS с интервалом в минуту после полного pilot; сама задача пока не установлена.

ID операции сохраняется до POST create, поэтому потерянный ответ не создаёт дубль.
При server-stage failure, timeout или прерывании сохраняются job-error.json,
deployment.json, report.json и report.txt; backend barrier остаётся. Повтор продолжает
тот же deployment. При backend phase=failed CLI ничего не разблокирует и не вызывает
retry за оператора. После исправления — явный API retry, затем повтор CLI.
Success exit 0 требует completed и двойных подтверждений всех целей; 0/0 не успех.

После успешного server stage CLI read/merge/write сохраняет три digest в Git stack
Dockhand и перечитывает их; остальные variables, включая masked secrets, сохраняются.
Во время CD не редактировать env stack параллельно. Контракт PUT и masked placeholders
проверен по [исходнику Dockhand v1.0.53](https://github.com/Finsys/dockhand/blob/v1.0.53/src/routes/api/stacks/%5Bname%5D/env/%2Bserver.ts).
Live API merge на NAS ещё не выполнялся. Dockhand auto-update/webhook остаются off:
обновление игровых процессов проходит только через общий CD barrier.
