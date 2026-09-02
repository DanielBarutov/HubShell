# План 23 — автоматическое подключение Windows-клиента и личный кабинет

Статус: `in_progress`  
Приоритет: `P0`  
Владельцы: `backend/`, `win-client/`, `frontend/`  
Зависимости: `01-workstations`, `02-clients-guests`, `04-auth-security`, `06-sessions`, `07-billing`, `10-product-sales`, `22-windows-lockdown`

## Цель

Убрать dev-сценарий с ручными переменными окружения, локальными PIN-хэшами и
bootstrap token из обычной установки игрового ПК.

Целевой пользовательский путь:

1. Администратор один раз собирает self-contained EXE и передаёт его на игровой ПК.
2. EXE запускается без консоли и без ручного ввода конфигурации.
3. Клиент определяет доступные MAC-адреса и показывает состояние «Ожидает
   привязки администратора».
4. Администратор в web-панели создаёт/редактирует место и указывает MAC.
5. Клиент находит назначенное место, получает настройки группы и device access
   token, после чего начинает heartbeat.
6. Клиент стартует в полноэкранной заблокированной оболочке. Пользователь может
   зарегистрироваться или войти; `Ctrl+Alt+P` открывает менеджерский вход.
7. После входа пользователь видит профиль, баланс, историю пополнений и
   списаний, покупки товаров/тарифов и доступное время.

MAC используется для назначения в клубной сети, но не считается самостоятельным
долгосрочным секретом. После привязки backend связывает MAC с установочной
идентичностью клиента; production hardening с подтверждением/rotation остаётся
обязательной проверкой перед внешней эксплуатацией.

## Контракты и границы

- Device enrollment выполняется отдельным bootstrap-запросом только для поиска
  назначения по MAC. Он не открывает бизнес-операции и не выдаёт операторские
  права.
- Все последующие device-команды работают через JWT Bearer и существующий
  gRPC `WorkstationService`.
- Личный кабинет получает отдельный короткоживущий client JWT, привязанный к
  `device_id`; клиентский токен не даёт operator permissions.
- Баланс, сессии, списания, продажи и доступное время рассчитываются backend.
  Windows-клиент только отображает DTO и вызывает разрешённые команды.
- Адрес backend не вводится на игровом ПК. Для production EXE собирается с
  заранее известным HTTPS/DNS endpoint клуба; dev loopback остаётся только для
  разработки и тестов.
- Полноэкранное окно WinUI и app-level lock не заменяют Windows Assigned
  Access/Shell Launcher. Запрет выхода из Windows desktop проверяется отдельным
  native smoke-чеком по плану 22.

## Задачи

Детализация вынесена в планы [`23-device-enrollment`](../23-device-enrollment/PLAN.md),
[`24-windows-shell`](../24-windows-shell/PLAN.md),
[`25-client-portal`](../25-client-portal/PLAN.md),
[`26-frontend-device-assignment`](../26-frontend-device-assignment/PLAN.md),
[`27-portable-deployment`](../27-portable-deployment/PLAN.md) и
[`28-integration-checks`](../28-integration-checks/PLAN.md).

### Backend

- [x] Добавить нормализованный `mac_address` и установочную идентичность к
  Workstation, миграцию и CRUD-поле в operator API.
- [x] Добавить enrollment use case: `pending`, `approved`, `disabled`, binding
  installation identity и выдача только device-scoped JWT.
- [x] Добавить server-side client registration/login с хэшем PIN и блокировкой
  заблокированного профиля.
- [x] Добавить gRPC portal DTO для профиля, баланса, ledger, session charges,
  product sales, тарифов и доступного времени.
- [x] Добавить проверки device/client scope и audit boundary без PIN, токенов и
  полного payload.
- [x] Покрыть memory/API сценарии; [ ] закрыть live gRPC и PostgreSQL concurrency.

### Windows client

- [x] Определять MAC и сохранять только случайный installation id в AppData.
- [x] Poll enrollment без консоли и показывать понятные состояния ожидания,
  отключённого места, offline и успешной привязки.
- [x] Перейти с local access-code gate на server-backed user register/login;
  локальный env verifier оставить только явно включаемым dev fallback.
- [x] Запускать клиент в borderless fullscreen locked shell; компактный режим
  оставить только как менеджерский/диагностический режим.
- [x] Реализовать `Ctrl+Alt+P`, профиль пользователя, историю операций,
  сессий, списаний, товаров/тарифов и доступного времени.
- [ ] Добавить хранение/ротацию device и client tokens без plaintext в логах.
- [ ] Проверить single-file EXE на обычном пользователе Windows и на чистом ПК.

### Frontend

- [x] Добавить поле MAC в создание/редактирование места и явный статус
  `ожидает привязки` / `подключено`.
- [ ] Показывать последнее обнаружение, установочную идентичность без секрета и
  действие «отвязать/перепривязать» с audit.
- [x] Убрать из operator UX необходимость вручную создавать `device_id` для
  нового места; старые записи поддержать обратно совместимо.

## Проверки и чекапы

- Backend: migration upgrade/downgrade, enrollment pending/approved/disabled,
  MAC normalization, installation mismatch, JWT scope, client login и history.
- Frontend: создание места только по MAC, повторное подключение, отключение и
  отображение online/offline.
- Windows: запуск EXE без env и консоли, fullscreen lock, восстановление сети,
  привязка после действия администратора, регистрация/вход пользователя,
  `Ctrl+Alt+P`, отсутствие выхода в desktop.
- Security: MAC spoof/rebind, token expiry/rotation, отсутствие PIN/token в
  EXE, AppData, логах и audit payload.

## Не считать выполненным

- Наличие protobuf-файла без generated Python и native Windows build.
- Запуск полноэкранного WinUI окна как доказательство kiosk security.
- Выдачу device token только по MAC без installation binding.
- Отображение demo-истории или локального баланса вместо server DTO.
