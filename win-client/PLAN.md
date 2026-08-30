# Windows client — виджет игрового ПК

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `win-client/`  
Зависимости: `backend/PLAN.md`, Workstations и Auth

Детальный план lockdown и Windows provisioning: [`plans/22-windows-lockdown/PLAN.md`](../plans/22-windows-lockdown/PLAN.md).

## Цель

Создать Windows-клиент в виде компактного рабочего виджета на C#/.NET и WinUI 3, который безопасно связывается с backend по gRPC, получает настройки группы ПК и может развернуться во всё окно.

## Входит в план

- WinUI 3 shell и окно-виджет;
- compact/full-window modes;
- gRPC connection и generated client;
- device identity и bootstrap auth flow;
- heartbeat, reconnect, cancellation и network status;
- получение темы/конфигурации группы ПК;
- обработка команд и acknowledgement;
- version/capabilities reporting;
- безопасное локальное хранение минимума конфигурации;
- логирование без PII и секретов.

## Не входит

- C++ без доказанной необходимости;
- основная бизнес-логика и расчёт цены в клиенте;
- произвольное управление процессами и файлами Windows;
- полноценный auto-updater;
- offline-финансовые операции без reconciliation-плана.

## UX и технические правила

- обычный режим — компактный виджет, не fullscreen;
- full-window режим сохраняет контекст и основные действия;
- тема выбирается серверной конфигурацией группы, например VIP/обычный зал;
- смена темы не требует новой версии клиента;
- при потере сети клиент показывает offline/reconnecting и не создаёт ложный success;
- heartbeat и acknowledgement имеют timeout и retry policy;
- локально не кэшируются лишние данные клиента, баланс или секреты;
- C++ добавляется только после документированной системной потребности и измерения.

## Задачи

1. [x] Зафиксировать Windows support matrix, .NET/WinUI versions и способ сборки.
2. [x] Создать solution с UI, application logic, domain models и infrastructure adapters.
3. [x] Реализовать generated gRPC client и auth metadata boundary.
4. [x] Реализовать widget/full-window window state.
5. [x] Реализовать heartbeat, reconnect, timeout и graceful shutdown boundary.
6. [x] Реализовать локальный theme shell с safe defaults; versioned server configuration остаётся.
7. [x] Реализовать gRPC command receiver/ack boundary, capabilities reporting, reconnect-backoff и ограниченный журнал результатов для защиты от повторного side effect; безопасный executor поддерживает `display.lock`/`theme.apply`.
8. [x] Добавить отображение ближайшей брони и ограничение тарифа prototype.
9. [x] Добавить диагностический статус без секретов.
10. [ ] Проверить запуск под обычным пользователем и восстановление после
    перезапуска на Windows; в текущей Linux-среде не проверено. Добавлен
    воспроизводимый Windows-чек в `scripts/verify-windows.ps1`, но native run
    требует Windows.
11. [x] Зафиксировать отсутствие C++ до появления доказанной системной потребности.
12. [x] Реализовать device-authenticated SessionService gateway, capability `sessions.v1` и структурированный `session.start/stop` executor; локальные игровые процессы остаются вне этого среза.
13. [x] Получать theme key группы в ответе heartbeat, применять безопасную палитру
    WinUI и сохранять safe default для неизвестной темы.
14. [x] Синхронизировать состояние `IsExpanded` с resize-переключателем и добавить
    доступную подпись действия для compact/full-window кнопки.
15. [x] Зафиксировать endpoint transport policy: loopback HTTP только в dev,
    production требует HTTPS для auth и gRPC.
16. [x] Реализовать access-gate: клиент стартует заблокированным, пользователь
    проходит вход до доступа к действиям, а после бездействия экран снова
    блокируется; основной content скрыт до снятия блокировки. Статический
    менеджерский пароль не хранить в клиенте: для dev
    допускается PBKDF2-хеш из защищённой конфигурации, production использует
    Windows Credential Manager/серверную проверку supervisor. Добавлены
    throttling неудачных попыток, relock при device-auth 401/403/Unauthenticated,
    relock при деактивации окна и unit-тесты coordinator.
17. [ ] Зафиксировать kiosk deployment: app-level lock не заменяет Windows
    logon. Для запрета Alt+Tab, запуска оболочки и ухода в другой desktop нужен
    Assigned Access/Shell Launcher, отдельная учётная запись ПК и ручная Windows
    проверка под ограниченным пользователем.
18. [x] Добавить воспроизводимый self-contained publish-скрипт для `win-x64`,
    `win-x86` и `win-arm64` с опциональным single-file режимом; native publish
    остаётся требующим Windows-проверки.
19. [x] Добавить явную горячую клавишу `Ctrl+Alt+P` для manager maintenance
    login, lock действий до входа, обработку завершения/исчерпания баланса и
    контролируемый restart после подтверждённой сервером остановки сессии.
    Команда `session.start` также передаёт `tariff_id`/`tariff_quantity`, а
    виджет показывает активную сессию и позволяет завершить её самостоятельно.
20. [x] Подготовить Windows deployment script/installer bootstrap, который
    регистрирует автозапуск клиента и опциональные recovery policy; настоящий
    Assigned Access/Shell Launcher и native installer smoke требуют Windows.
21. [x] Подключить смену manager credential из operator dashboard для группы ПК:
    backend сохраняет только PBKDF2-verifier, отдаёт его конкретному device через
    аутентифицированный heartbeat, а клиент держит verifier только в памяти.
    Для production остаются отдельные enrollment/rotation и Windows Credential
    Manager hardening; dev fallback — PBKDF2-verifier базового `password`.
22. [ ] Выполнить план [`plans/22-windows-lockdown/PLAN.md`](../plans/22-windows-lockdown/PLAN.md):
    разделить app-level shell lock и Windows security boundary, добавить
    декларативную policy группы, безопасный session lock и обратимый provisioning
    Assigned Access/Shell Launcher.

Текущий срез: gRPC-клиент получает device JWT через dev bootstrap, передаёт bearer
metadata, heartbeat и server-streaming команды с acknowledgement. Клиент проверяет
`expires_at` перед исполнением и отрицательно подтверждает просроченную команду.
После потери stream клиент переподключается с backoff до 30 секунд, а результат
исполненной команды сохраняется в ограниченном in-memory журнале до ACK, поэтому
повторная доставка после потери ответа не повторяет side effect в том же процессе.
Protobuf source-of-truth содержит актуальные catalog/reservation/session/billing contracts,
включая единый CatalogSnapshot для чтения тарифов и discount rules, а
Python compatibility test подтверждает наличие generated Python и C# consumers.
Session-команды принимают только JSON-поля `client_id`/`guest_name`/`reservation_id`
или `session_id`, вызывают SessionService с device identity и получают ACK после
серверного результата; billing в клиент не переносится.
Heartbeat возвращает тему настроенной группы; клиент принимает только allowlist
`standard`, `vip`, `neon`, `minimal`, преобразует её в безопасную палитру WinUI и
использует стандартную тему при неизвестном значении.
Сборка WinUI 3 и ручная проверка окна требуют Windows; ограничения и команды
вынесены в [`docs/SUPPORT-MATRIX.md`](docs/SUPPORT-MATRIX.md). В Linux локально
восстановлен .NET 8 SDK и NuGet-граф, но WindowsAppSDK `XamlCompiler.exe` не
запускается как native Windows tool, поэтому native build остаётся непроверенным.
App-level access-gate и тестируемая проверка PBKDF2-хешей добавлены, но итоговая
защита рабочего стола зависит от Windows Assigned Access/Shell Launcher и ещё
требует native проверки на целевом ПК.

## Критерии готовности

- клиент запускается как виджет и разворачивается во всё окно;
- устанавливает защищённое соединение и сообщает heartbeat;
- переживает временное отключение сети без ложного success;
- получает тему группы ПК без новой сборки;
- показывает ближайшую бронь и не предлагает несовместимый по времени тариф;
- команды имеют acknowledgement, timeout и безопасное поведение при дубле;
- клиент не расходится с backend по бизнес-правилам;
- секреты и лишние персональные данные не сохраняются.
- до входа пользователя в клиенте нет рабочих действий и персональных данных;
- maintenance mode требует отдельной проверки менеджера и явно закрывается;
- kiosk-граница Windows настроена политикой ОС, если клубу нужен запрет выхода
  из клиентской оболочки.

## Риски

- нестабильная сеть приведёт к повторным командам без корректного acknowledgement;
- неподходящее локальное хранилище токена создаст риск компрометации;
- platform-specific C++ увеличит стоимость сопровождения без доказанной пользы;
- рассинхронизация времени Windows и backend может нарушить показ брони.

## Проверки

- .NET build и unit tests на Windows; в Linux выполнены статические contract/
  source checks, native build остаётся непроверенным;
- gRPC contract/integration tests с test backend;
- window mode and theme manual tests on Windows;
- reconnect/timeout/duplicate command tests;
- reservation display and time-boundary tests;
- запуск под ограниченной учётной записью;
- проверка локальных файлов и логов на отсутствие секретов.

## Открытые вопросы

- нужен ли отдельный Windows Service;
- должен ли виджет быть always-on-top;
- нужен ли запуск при старте Windows;
- какие команды входят в первую версию;
- как доставлять и откатывать обновления;
- какие Windows API действительно требуют C++.
