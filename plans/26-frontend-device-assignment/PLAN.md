# План 26 — назначение игровых мест в админке

Статус: `in_progress`  
Владелец: `frontend/`  
Связи: [`23-device-enrollment/PLAN.md`](../23-device-enrollment/PLAN.md), `01-workstations`

## Результат

В настройках и карточке места администратор указывает MAC, видит понятные
состояния «ожидает привязки», «подключено», «не в сети», «отключено» и может
без console commands перепривязать устройство.

## Этапы

- [x] Добавить MAC в typed API и формы workstation.
- [x] Убрать обязательный ручной `device_id` для нового места.
- [x] Показать installation bound без отображения самого installation secret.
- [ ] Добавить confirmation для rebind и audit result.
- [x] Source-level сохранить карту, фильтры зон, polling 20 секунд и Redis cache.
- [x] Не показывать токены, PIN и внутренние claims.
