# GameClub Windows client

Пошаговая проверка на реальном Windows-ПК находится в
[docs/REAL-PC-VERIFICATION.md](docs/REAL-PC-VERIFICATION.md).

Целевая платформа и границы проверок описаны в
[`docs/SUPPORT-MATRIX.md`](docs/SUPPORT-MATRIX.md).

Компактный WinUI 3 виджет для рабочего места игрового ПК. По кнопке в заголовке
окно переключается между компактным режимом и широким режимом рабочего окна;
подпись кнопки и её accessibility name показывают следующее действие.

## Слои

- `Domain` — состояния соединения и модели, не зависящие от WinUI или gRPC;
- `Application` — coordinator и порты для backend/token provider;
- `Infrastructure` — gRPC adapter с deadline, bearer metadata и health check;
- `Presentation` — WinUI окно и view model.

## Локальный запуск на Windows

Требуются Visual Studio 2022 с workload **.NET desktop development** и Windows App
SDK. После запуска backend gRPC на `127.0.0.1:51051`:

```text
dotnet restore GameClub.Client.sln
dotnet build GameClub.Client.sln --configuration Debug -p:Platform=x64
dotnet test GameClub.Client.sln --configuration Debug -p:Platform=x64
```

Для воспроизводимой проверки из PowerShell используйте скрипт:

```powershell
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Скрипт проверяет Windows/.NET 8, выполняет restore и native build, после чего
выводит ручной checklist для обычного пользователя, reconnect, тем и перезапуска.
Он намеренно завершается с ошибкой вне Windows: Linux-проверка не заменяет сборку
WinUI 3.

## Получение переносимого EXE

Основной способ для проверки на клиентском ПК — один self-contained single-file
EXE. На админском Windows-ПК выполните из каталога `win-client`:

```powershell
.\scripts\build-portable-exe.ps1 -Architecture x64 -Configuration Release
```

Единственный файл появится в
`artifacts\portable\win-x64\Release\GameClub.Client.exe`. Его можно
скопировать на клиентский ПК и запустить без Visual Studio, .NET SDK и отдельно
установленного Windows App SDK. При первом запуске зависимости распаковываются
во временный каталог Windows — это ожидаемое поведение single-file WinUI-клиента.

Для обычной folder-публикации и диагностики также доступен скрипт:

```powershell
.\scripts\publish-windows.ps1 -Architecture x64 -Configuration Release
```

Результат появится в каталоге
`artifacts\publish\win-x64\Release`. Это folder-публикация: WinUI 3
и runtime поставляются рядом с EXE.

Секреты и настройки подключения в EXE не вшиваются — они задаются переменными
окружения конкретного клиентского ПК или deployment policy.

Одноразовая настройка окружения для запуска скопированного EXE:

```powershell
$env:GAMECLUB_ENVIRONMENT = "dev"
$env:GAMECLUB_DEVICE_ID = "pc-001"
$env:GAMECLUB_AUTH_ADDRESS = "http://127.0.0.1:8100"
$env:GAMECLUB_GRPC_ADDRESS = "http://127.0.0.1:51051"
$env:GAMECLUB_DEVICE_BOOTSTRAP_TOKEN = Read-Host "Device bootstrap token"
& "C:\GameClub\GameClub.Client.exe"
```

Эти переменные действуют только в текущем PowerShell-сеансе. Для запуска двойным
кликом их нужно задать в deployment policy или установить для учётной записи
Windows; сам EXE не содержит device token и пароль.

Для локального подключения device-токена задайте переменные окружения процесса:

```text
GAMECLUB_DEVICE_ID=pc-001
GAMECLUB_DEVICE_BOOTSTRAP_TOKEN=значение-из-backend/.env
GAMECLUB_AUTH_ADDRESS=http://127.0.0.1:8100
GAMECLUB_GRPC_ADDRESS=http://127.0.0.1:51051
```

До входа пользователя окно закрыто app-level access-gate. Для dev задайте
PBKDF2-хеши, а не plaintext-секреты:

```text
GAMECLUB_CLIENT_ACCESS_PIN_HASH=pbkdf2-sha256$210000$<salt-base64>$<hash-base64>
GAMECLUB_MANAGER_PASSWORD_HASH=pbkdf2-sha256$210000$<salt-base64>$<hash-base64>
```

Сгенерировать строку без вывода plaintext-пароля можно в PowerShell:

```powershell
.\scripts\new-access-hash.ps1 -Kind manager
.\scripts\new-access-hash.ps1 -Kind user
```

Формат проверяется в `PasswordHashVerifier`; plaintext-значения не выводятся в
логи и не попадают в protobuf. Пароль конкретной зоны можно задать в dashboard:
сервер сохраняет PBKDF2-verifier и отдаёт его только этому device через
аутентифицированный heartbeat; клиент держит verifier в памяти процесса.
Настоящее ограничение Windows-оболочки настраивается
отдельно через Assigned Access/Shell Launcher — см. [`docs/ACCESS-GATE.md`](docs/ACCESS-GATE.md).
В dev-окружении, если `GAMECLUB_MANAGER_PASSWORD_HASH` не задан, доступ менеджера
включается через PBKDF2-хеш встроенного dev-значения `password`. В staging и
production хеш нужно задать явно через deployment policy. Горячая клавиша
`Ctrl+Alt+P` блокирует виджет и открывает форму режима обслуживания.
При ответе backend `401/403` или gRPC `Unauthenticated/PermissionDenied` клиент
очищает access-gate и требует повторную авторизацию устройства; обычный временный
обрыв сети только показывает offline/reconnect.

В dev loopback `http://127.0.0.1` разрешён. Для production задайте
`GAMECLUB_ENVIRONMENT=production` и указывайте только `https://` адреса auth и
gRPC backend; клиент завершит запуск с явной ошибкой при небезопасной схеме или
невалидном URI. Используйте выданный
клубом сертификат; dev `http://127.0.0.1` оставлен только для локального запуска.

Bootstrap endpoint доступен только в dev-окружении backend. Токен не записывается
в файлы и логи, а выданный JWT хранится только в памяти процесса. Для production
нужны enrollment/rotation/revocation и защищённое локальное хранилище Windows.

Сейчас gRPC adapter содержит health check, heartbeat с capabilities, server-streaming
получение команд, acknowledgement boundary и dev-bootstrap provider. Безопасный
executor поддерживает app-level `display.lock` через access-gate и `theme.apply` через UI;
`session.start/stop` разбирают только структурированный payload и вызывают
защищённый SessionService с device identity; backend SessionService фиксирует
операторский `active`/`completed` lifecycle, а BillingService списывает средства только после
завершения фактической именованной сессии. Win-клиент не кэширует баланс и не
выполняет финансовые операции. Команды имеют серверный `expires_at`, поэтому устаревшая
команда не должна исполняться после reconnect. Произвольные shell-команды не
поддерживаются.
Настройка группы ПК хранится в backend; ответ heartbeat содержит безопасный theme
key, после чего WinUI применяет соответствующую палитру без новой сборки клиента.

Для системной границы kiosk подготовлен `scripts/configure-windows-kiosk.ps1`.
Он генерирует Shell Launcher XML, сохраняет предыдущую policy и применяет её
только с явным `-Apply`; без этого флага устройство не изменяется. Восстановление:

```powershell
.\scripts\configure-windows-kiosk.ps1 -Apply -Restore
```

## Установка на Windows

На Windows с Visual Studio/.NET 8 выполните публикацию и подготовьте пакет:

```powershell
.\scripts\build-installer.ps1 -Architecture x64 -Configuration Release
```

В каталоге `artifacts\installer\...` будет self-contained payload и скрипты
`install-windows.ps1`/`uninstall-windows.ps1`. Установка копирует клиент,
регистрирует автозапуск текущего пользователя через `HKCU\...\Run`, при
необходимости задаёт окружение устройства и может зарегистрировать recovery-задачу:

```powershell
.\install-windows.ps1 -DeviceId pc-001 -DeviceBootstrapToken <token> -RegisterRecoveryTask
```

Скрипт не прошивает секреты в EXE и не включает Assigned Access автоматически.
После подтверждённой остановки `session.stop` app callback применяет policy зоны и
при включённом флаге планирует перезапуск Windows через `shutdown.exe`; виджет показывает активную сессию и позволяет пользователю
завершить её самостоятельно. При нулевом балансе backend отправляет
`session.stop` и `display.lock`, а сам обработчик подтверждённого `session.stop`
планирует перезапуск.

Клиент дополнительно проверяет `expires_at` перед исполнением команды и отправляет
отрицательный acknowledgement для просроченной команды. Сборка WinUI 3 и ручная
проверка окна требуют Windows и в Linux-окружении не проверяются. При временном
обрыве stream клиент использует экспоненциальную задержку reconnect до 30 секунд,
а результат уже исполненной команды держится в ограниченном in-memory журнале до
успешного acknowledgement: повторная доставка после потери ответа не запускает
локальный side effect второй раз. Журнал не заменяет серверную идемпотентность и
сбрасывается при полном перезапуске процесса; в этой среде
проверены только структура проекта, исходные protobuf-контракты и статические
границы слоёв.
