# План 12 — Live metered billing и последовательные тарифы

Статус: `in_progress`  
Приоритет: `P0`  
Владелец: `backend/`  
Зависимости: Catalog, Clients, Sessions, Billing, Workstations

## Цель

Добавить единый серверный lifecycle продажи времени с карты ПК: блочные тарифы
могут использоваться последовательными единицами, а поминутные тарифы списывают
баланс после бесплатного grace-периода и автоматически завершают сессию при
исчерпании spendable balance.

## Решения первого среза

- `Tariff.billing_mode` принимает `block` или `per_minute`.
- Цена поминутной игры принадлежит зоне и задаётся в `workstation_groups` через
  `per_minute_price_cents`; backend поддерживает внутренний per-minute snapshot
  для совместимости с текущим meter-контрактом. Цена и списание рассчитываются
  backend, а не frontend.
- `Session.tariff_quantity` фиксирует количество последовательных одинаковых
  блочных единиц, например две единицы по часу.
- `SessionMeter` хранит уже списанные минуты/копейки и защищается
  idempotency key, чтобы worker и оператор не списали одну минуту дважды.
- При нехватке баланса сервер завершает сессию и отправляет устройству только
  allowlisted команды остановки/блокировки; произвольные shell-команды запрещены.
- Если у клиентской сессии нет активного entitlement и явно выбранного тарифа,
  backend фиксирует опубликованный per-minute тариф её зоны; для уже созданной
  legacy-сессии billing worker использует тот же fallback при первом meter tick.
- Гость не получает автоматическое списание: для гостевой сессии остаётся
  операторское завершение и будущий cashier flow.

## Задачи

1. [x] Расширить домен, HTTP и protobuf контракт тарифа и сессии.
2. [x] Добавить миграции и memory/PostgreSQL repositories для meter.
3. [x] Реализовать идемпотентное списание elapsed minutes и recovery worker.
4. [x] Подключить выбор тарифа/количества, продажу товара и пополнение клиента к карте ПК.
5. [x] Добавить unit/API/concurrency tests и Compose smoke.
6. [x] Зарегистрировать все Dramatiq actors на общем broker и вынести live
   metering в отдельную очередь/worker, чтобы reconciliation backlog не
   задерживал списание активных сессий.

Оставшийся production backlog: отдельный cashier flow для автоматического
списания гостевой поминутной сессии. Manager credential уже настраивается для
группы ПК из dashboard: сервер сохраняет только PBKDF2-verifier, а Win-клиент
получает его в device-authenticated heartbeat. Полноценный device enrollment,
rotation и Windows Credential Manager остаются отдельным production hardening.

## Границы

Не входит: заранее купленные разные пакеты с очередью entitlement, списание
бонусного баланса, external payments, reserve/hold средств и нативный Windows
kiosk policy. Эти задачи требуют отдельных контрактов и reconciliation rules.
