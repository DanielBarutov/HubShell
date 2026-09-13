# Windows client — access-gate и post-login session widget

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `win-client/`  
Зависимости: `backend/PLAN.md`, Workstations и Auth, а также планы
[`33-session-transfer`](../plans/33-session-transfer/PLAN.md),
[`34-durable-offline`](../plans/34-durable-offline/PLAN.md),
[`36-winui-contract-consumers`](../plans/36-winui-contract-consumers/PLAN.md),
[`37-platform-integration-evidence`](../plans/37-platform-integration-evidence/PLAN.md) и
[`38-avalonia-linux-first`](../plans/38-avalonia-linux-first/PLAN.md)

Детальный план lockdown и Windows provisioning: [`plans/22-windows-lockdown/PLAN.md`](../plans/22-windows-lockdown/PLAN.md).

## Цель

Создать Windows-клиент на C#/.NET с Avalonia UI, который после запуска сам
подключается к backend, назначается администратором по MAC и получает настройки
группы. До server-backed авторизации он работает как полноэкранный borderless
access-gate. После авторизации не заменяет Windows shell, переходит к обычному
Windows Desktop и показывает компактный borderless-виджет сессии, который можно
скрыть в трей. Manager maintenance остаётся отдельным режимом.

Avalonia-host является Linux-first developer host: обычная разработка должна
включать Linux restore/build/test и запуск окна здесь. Это не меняет целевой
Windows-продукт и не делает Linux-версию kiosk-клиентом. Windows остаётся
обязательной финальной проверкой publish, tray, DPAPI, window placement,
autostart и Assigned Access/Shell Launcher. Порядок и первая остановка
миграции зафиксированы в плане 38.

Первый технический срез плана 38 выполнен частично: `GameClub.Client.Core`,
`GameClub.Client.Avalonia` и cross-platform tests собираются в Linux; headless
smoke прошёл, diagnostic окно запускалось в GUI-сеансе, а `win-x64` artifact
собран cross-publish. Это не перенос access-gate/portal и не Windows runtime
proof: `MainViewModel`, full product UI и Windows adapters пока остаются legacy
WinUI source. Точное evidence — в
[`plans/VERIFICATION.md`](../plans/VERIFICATION.md).

Подробный целевой flow и личный кабинет: [`plans/23-windows-enrollment-member-portal/PLAN.md`](../plans/23-windows-enrollment-member-portal/PLAN.md).

## Входит в план

- Avalonia access-gate и post-login session widget;
- Linux restore/build/test и developer UI-smoke до Windows platform-smoke;
- dynamic borderless/fullscreen presentation и tray hide/show;
- gRPC connection и generated client;
- automatic MAC enrollment and device identity;
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

- до авторизации — полноэкранный locked access-gate без стандартного chrome;
- после авторизации — обычный Windows Desktop и компактный borderless widget без
  системных кнопок окна; widget можно скрыть собственной кнопкой в трей;
- клиент не требует ручных env-переменных, PIN-хэшей или bootstrap token при
  обычной установке;
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
4. [x] Реализовать state-dependent window presentation: fullscreen gate до auth,
    post-auth desktop/widget и tray hide/show; native Windows smoke всё ещё
    нужен для подтверждения фактического поведения.
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
    legacy WinUI implementation и сохранять safe default для неизвестной темы.
14. [x] Убрать пользовательский compact/full-window переключатель из Locked-flow;
    старый marker сохранён только как source-compatibility boundary.
15. [x] Зафиксировать endpoint transport policy: HTTP разрешён для loopback и
    приватных LAN IPv4 (`10/8`, `172.16/12`, `192.168/16`) в закрытом deployment,
    включая production; для внешних адресов используется HTTPS.
16. [x] Реализовать access-gate: клиент стартует заблокированным, пользователь
    проходит вход до доступа к действиям, а после бездействия экран снова
    блокируется; основной content скрыт до снятия блокировки. Статический
    менеджерский пароль не хранить в клиенте: для dev
    допускается PBKDF2-хеш из защищённой конфигурации, production использует
    Windows Credential Manager/серверную проверку supervisor. Добавлены
    throttling неудачных попыток и relock при device-auth
    401/403/Unauthenticated; потеря фокуса окна сама по себе не вызывает relock.
    Добавлены unit-тесты coordinator.
17. [ ] Зафиксировать kiosk deployment: app-level lock не заменяет Windows
    logon. Для запрета Alt+Tab, запуска оболочки и ухода в другой desktop нужен
    Assigned Access/Shell Launcher, отдельная учётная запись ПК и ручная Windows
    проверка под ограниченным пользователем.
18. [x] Добавить воспроизводимый self-contained publish-скрипт для `win-x64`,
    `win-x86` и `win-arm64`, а также `build-portable-exe.ps1` с single-file
    режимом по умолчанию для передачи одного EXE; native publish остаётся
    требующим Windows-проверки.
19. [x] Реализовать manager maintenance login через явный пользовательский
    flow, lock действий до входа, обработку завершения/исчерпания баланса и
    контролируемый restart после подтверждённой сервером остановки сессии.
    Скрытая глобальная горячая клавиша `Ctrl+Alt+P` удалена из пользовательского
    клиента. Команда `session.start` также передаёт `tariff_id`/`tariff_quantity`,
    а клиент показывает активную сессию и позволяет завершить её самостоятельно.
20. [x] Подготовить Windows deployment/autostart bootstrap, который
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
23. [x] Выполнить source-level контрактный срез [`plans/29-contract-alignment/PLAN.md`](../plans/29-contract-alignment/PLAN.md):
    session snapshot gateway, package lifecycle notification, transfer и durable
    offline batch. Package queue и explicit activation доступны в client portal
    snapshot/gRPC/UI; entry login integration, native Windows и production
    hardening остаются отдельными checks в планах 32/36/37.
24. [x] Добавить в приложение собственный startup diagnostics boundary:
    безопасный журнал этапов запуска в `%LocalAppData%\GameClub\startup.log`,
    обработчики ранних managed/UI-исключений и наблюдение за background tasks.
    Native Windows проверка журнала остаётся частью реального smoke; внешний
    сборщик `scripts/diagnose-startup.ps1`, Application Event Log и Visual Studio
    используются для ранних/native loader сбоев.
25. [x] Устранить source-level причины пустого первого кадра и невидимой ошибки
    покупки: начальный presenter применяется после загрузки XAML visual tree,
    режим повторно применяется после возврата из трея, а ошибки недостаточного
    баланса показываются отдельным уведомлением авторизованного виджета.
26. [x] Поддержать операторский сброс пароля без генерации временного секрета:
    passwordless-вход только для сброшенного аккаунта, обязательная форма нового
    пароля с повтором в legacy WinUI implementation и блокировка действий портала до подтверждения.
    Native Windows publish/smoke остаётся отдельной проверкой на Windows.

Декомпозиция оставшегося runtime: entitlement/meter и snapshot принадлежат
планам [`30`](../plans/30-entitlements-meter/PLAN.md) и
[`32`](../plans/32-session-snapshot-entry/PLAN.md), transfer — [`33`](../plans/33-session-transfer/PLAN.md),
offline — [`34`](../plans/34-durable-offline/PLAN.md), legacy WinUI consumers —
[`36`](../plans/36-winui-contract-consumers/PLAN.md), а native/kiosk evidence —
[`37`](../plans/37-platform-integration-evidence/PLAN.md). Avalonia migration
до первого Linux build/run — [`38`](../plans/38-avalonia-linux-first/PLAN.md).

Текущий source-level срез: gRPC-клиент получает device JWT через MAC enrollment, передаёт bearer
metadata, heartbeat и server-streaming команды с acknowledgement. Клиент проверяет
`expires_at` перед исполнением и отрицательно подтверждает просроченную команду.
После потери stream клиент переподключается с backoff до 30 секунд, а
offline-операции active session сохраняются в DPAPI-защищённом JSONL journal с
durable sequence state до server ACK; повторная доставка не должна повторять
side effect.
Protobuf source-of-truth содержит актуальные catalog/reservation/session/billing contracts,
включая единый CatalogSnapshot для чтения тарифов и discount rules, а
Python compatibility test подтверждает наличие generated Python и C# consumers.
Session-команды принимают только JSON-поля `client_id`/`guest_name`/`reservation_id`
или `session_id`, вызывают SessionService с device identity и получают ACK после
серверного результата; billing в клиент не переносится.
Heartbeat возвращает тему настроенной группы; клиент принимает только allowlist
`standard`, `vip`, `neon`, `minimal`, преобразует её в безопасную палитру WinUI и
использует стандартную тему при неизвестном значении. До завершения плана 38
это описание относится к legacy WinUI source; продуктовой реализацией станет
Avalonia host с теми же server-backed правилами.
Session snapshot/transfer/replay DTO и gateway подключены на source-level.
Текущий WinUI source не собирается и не запускается как нативное окно в Linux.
Миграция на Avalonia должна закрыть Linux build/run для developer host; Windows
native evidence остаётся отдельной обязательной границей. Ограничения и порядок
зафиксированы в [`docs/SUPPORT-MATRIX.md`](docs/SUPPORT-MATRIX.md) и плане 38.
App-level access-gate и тестируемая проверка PBKDF2-хешей добавлены, но итоговая
защита рабочего стола зависит от Windows Assigned Access/Shell Launcher и ещё
требует native проверки на целевом ПК.

## Критерии готовности

- клиент запускается fullscreen в borderless Locked access-gate, а после входа
  переходит к post-auth desktop/widget flow;
- устанавливает защищённое соединение и сообщает heartbeat;
- переживает временное отключение сети без ложного success;
- получает тему группы ПК без новой сборки;
- показывает только server-backed reservation decision, session snapshot и
  package activation result;
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

- до плана 38: статические contract/source checks в Linux и .NET build/unit
  tests на Windows; после его первого этапа: Linux restore/build/test/run
  Avalonia developer host;
- gRPC contract/integration tests с test backend;
- window mode and theme manual tests on Windows;
- reconnect/timeout/duplicate command tests;
- reservation display and time-boundary tests;
- запуск под ограниченной учётной записью;
- проверка локальных файлов и логов на отсутствие секретов.

Обязательная дополнительная матрица и порядок закрытия разрывов находятся в
[`plans/29-contract-alignment/PLAN.md`](../plans/29-contract-alignment/PLAN.md).

## Открытые вопросы

- нужен ли отдельный Windows Service;
- должен ли виджет быть always-on-top;
- нужен ли запуск при старте Windows;
- какие команды входят в первую версию;
- как доставлять и откатывать обновления;
- какие Windows API действительно требуют C++.
