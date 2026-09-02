# GameClub Windows client

`GameClub.Client` — клиент игрового ПК. Целевой пользовательский сценарий:

1. администратор один раз собирает EXE на админском Windows-ПК;
2. EXE копируется на игровой ПК и запускается без консоли, SDK и ручной
   настройки;
3. клиент сам определяет MAC и ждёт назначения места в web-админке;
4. после назначения получает настройки группы и открывает fullscreen Locked
   shell;
5. пользователь регистрируется или входит на этом экране и видит только свой
   аккаунт, баланс, операции депозита, историю сессий/тарифов/товаров и
   доступное время;
6. менеджер открывает отдельный режим обслуживания через `Ctrl+Alt+P`.

Пошаговая проверка физического Windows-ПК находится в
[docs/REAL-PC-VERIFICATION.md](docs/REAL-PC-VERIFICATION.md), а границы
поддержки — в [docs/SUPPORT-MATRIX.md](docs/SUPPORT-MATRIX.md).

## Архитектура

- `Domain` — модели состояния, heartbeat и пользовательского портала без WinUI
  и gRPC;
- `Application` — coordinator и порты backend/token provider;
- `Infrastructure` — gRPC/HTTP enrollment, device identity, endpoint policy,
  Windows adapters;
- `Presentation` — WinUI fullscreen shell и `MainViewModel`.

Backend остаётся источником истины для сессий, тарифов, цены, баланса, списаний
и истории. Клиент не считает деньги и не принимает произвольные shell-команды.
Команды устройства ограничены allowlist, имеют срок действия и подтверждение.

## Сборка одного EXE на админском ПК

Для production передайте скрипту реальные адреса защищённых endpoint'ов. Адреса
не являются секретами и вшиваются в метаданные сборки:

```powershell
cd win-client
.\scripts\build-portable-exe.ps1 `
  -Architecture x64 `
  -Configuration Release `
  -EnvironmentName production `
  -AuthAddress "https://api.example.club:8100" `
  -GrpcAddress "https://api.example.club:51051"
```

Готовый файл:
`artifacts\portable\win-x64\Release\GameClub.Client.exe`.
Скрипт печатает SHA-256. На игровом ПК не нужны Visual Studio, .NET SDK,
Windows App SDK, PowerShell-команды, `device_id`, bootstrap-токен,
переменные окружения или локальные PIN-хэши.

Важно: один EXE можно передавать между ПК только при одинаковой архитектуре и
совместимой Windows. Если backend меняет адрес, EXE нужно пересобрать на
админском ПК; секреты в EXE не вшиваются.

## Установка на игровой ПК

Минимальный сценарий — скопировать `GameClub.Client.exe` в постоянную папку и
запустить двойным кликом. Клиент создаёт только технический `installation_id`
в `%LocalAppData%\GameClub\Client`, отправляет MAC на endpoint enrollment и
показывает одно из состояний:

- `Ожидает назначения` — администратор ещё не создал/не назначил место;
- `Подключение` — место найдено и проверяется heartbeat;
- `Заблокировано` — устройство отключено администратором;
- `Locked` — устройство подключено, ожидается регистрация или вход пользователя.

В админке оператор открывает настройки игровых мест, создаёт workstation,
выбирает группу/зону и указывает MAC из сведений физического ПК. До назначения
клиент не получает operator-доступ. После первого одобрения backend привязывает
установку к MAC; другой installation identity не может молча заменить её.

Для автозапуска и копирования folder-publish существует optional
`scripts/install-windows.ps1`, но для первого пользовательского smoke он не
нужен. Полное ограничение выхода в Windows настраивается отдельно через
Assigned Access или Shell Launcher — fullscreen WinUI сам по себе не является
границей безопасности ОС.

## Пользовательский и менеджерский flow

На Locked-экране пользователь может:

- зарегистрироваться по nickname, телефону и PIN;
- войти по nickname или canonical phone и PIN;
- увидеть текущий баланс и бонусы;
- увидеть пополнения и списания, включая поминутные списания;
- увидеть купленные товары, тарифы и историю игровых сессий;
- увидеть рассчитанное сервером доступное время.

JWT пользователя хранится только в памяти процесса, привязан к текущему device,
а snapshot обновляется с backend. При logout, expiry, relock или `401/403`
пользовательское состояние очищается. `Ctrl+Alt+P` открывает manager
maintenance; рабочий экран пользователя не должен получать manager credentials.

## Локальная разработка

Исходный Debug-запуск на Windows нужен только разработчику. Для него endpoint'ы
можно переопределить параметрами publish или runtime diagnostics, но эти
переменные не нужны при обычной передаче EXE на игровой ПК:

```powershell
dotnet restore .\GameClub.Client.sln
dotnet build .\GameClub.Client.sln --configuration Debug -p:Platform=x64
dotnet test .\GameClub.Client.sln --configuration Debug -p:Platform=x64
```

Проверочный скрипт выполняет native Windows restore/build/test и после этого
печатает ручной checklist:

```powershell
.\scripts\verify-windows.ps1 -Architecture x64 -Configuration Debug
```

Он намеренно завершается с ошибкой вне Windows: Linux не заменяет WinUI 3
XAML-компилятор и реальный kiosk smoke.

## Безопасность и kiosk

- MAC используется только как ключ назначения, не как единственная production
  аутентификация;
- в EXE нет паролей, JWT, bootstrap-токенов и PIN;
- production должен использовать HTTPS/gRPC TLS, rate limit, rotation/revocation
  device credentials и защищённое локальное хранилище;
- Assigned Access/Shell Launcher должны отдельно запрещать Explorer, desktop,
  Alt+Tab и произвольные приложения;
- действия `session.start/stop`, темы и lock проходят только через typed
  allowlist и backend permissions.

Нативные ограничения и ручные проверки описаны в
[docs/REAL-PC-VERIFICATION.md](docs/REAL-PC-VERIFICATION.md) и
[docs/ACCESS-GATE.md](docs/ACCESS-GATE.md).
