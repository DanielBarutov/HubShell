# План 23 — автоматическое назначение Windows-клиента по MAC

Статус: `in_progress`  
Владелец: `backend/` + `frontend/`  
Связи: [`23-windows-enrollment-member-portal/PLAN.md`](../23-windows-enrollment-member-portal/PLAN.md), `01-workstations`, `04-auth-security`

## Результат

Игровой ПК запускает один EXE, сам отправляет список MAC-адресов и ждёт
действия администратора. Администратор создаёт место в web-панели, вводя MAC,
после чего backend связывает его с workstation и выдаёт только device-scoped
JWT. `device_id` не требуется вводить на клиентском ПК.

## Этапы

- [x] Добавить нормализацию MAC в домен workstation.
- [x] Добавить `mac_address` и `installation_id` в модель и миграцию.
- [x] Добавить поиск workstation по MAC в memory/PostgreSQL repositories.
- [x] Добавить `pending/approved/disabled` enrollment endpoint.
- [x] Добавить frontend-поле MAC и статус привязки.
- [ ] Добавить явную операцию отвязки/перепривязки с audit.
- [ ] Добавить rate limit и production pairing/rotation policy.
- [x] Покрыть MAC normalization и mismatch installation memory-сценарием.
- [x] Добавить API checks для pending/approved/disabled и device-token scope.
- [x] Ограничить список MAC на Linux-клиенте 16 адресами — пределом
  enrollment API — чтобы Docker и другие виртуальные интерфейсы не превращали
  регистрацию устройства в ошибку валидации `422`.

## Security boundary

MAC — только lookup/assignment key. После первого одобрения сохраняется случайный
installation id клиента; другой installation id получает отказ и не заменяет
действующую привязку. MAC spoofing, TLS и ротация device token проверяются на
целевом deployment и не считаются закрытыми source-level реализацией.

## Чекап

`POST /api/v1/auth/device-enrollment` без совпадения возвращает `202 pending`,
после назначения — `200 approved`, для disabled — `409`. Ни один ответ не
содержит operator permissions.

Linux developer-host также проверен после перезапуска Compose: при большом
числе Docker-интерфейсов клиент отправил допустимые 16 MAC, получил `200` и
снова начал heartbeat назначенного места. Для production Windows всё ещё нужна
отдельная проверка на реальном игровом ПК: Linux-проверка не доказывает работу
EXE, Windows-сетевых адаптеров и kiosk-политик.
