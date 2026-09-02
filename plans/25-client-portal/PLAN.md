# План 25 — регистрация пользователя и личный кабинет на игровом ПК

Статус: `in_progress`  
Владелец: `backend/` + `win-client/`  
Связи: `02-clients-guests`, `06-sessions`, `07-billing`, `10-product-sales`, [`23-device-enrollment/PLAN.md`](../23-device-enrollment/PLAN.md)

## Результат

Пользователь регистрируется или входит непосредственно на игровом ПК. После
входа он видит только собственный профиль и server-backed историю:

- nickname/телефон и текущий баланс;
- пополнения и списания депозита, включая поминутный billing;
- купленные товары и тарифы;
- активную сессию и доступное время по применимому тарифу.

## Контракт

- Регистрация: nickname, телефон и PIN; PIN хранится только как server-side
  scrypt/PBKDF2 verifier.
- Login: nickname или canonical phone + PIN.
- Backend выдаёт короткоживущий `SubjectType.CLIENT` token, scoped к текущему
  workstation/device.
- Windows client не вычисляет цену, доступное время, списание или баланс.
- Гость не получает client balance автоматически.

## Этапы

- [x] Добавить application use case регистрации и проверки PIN.
- [x] Добавить client-scoped JWT и device binding в auth claims.
- [x] Добавить gRPC portal contract и server implementation.
- [x] Добавить истории ledger, session charges и product sales через публичные
  read-порты модулей.
- [x] Добавить расчёт доступного времени по действующему тарифу и балансу.
- [x] Добавить WinUI register/login/profile/history screens.
- [x] Добавить logout, expiry, relock и очистку пользовательского состояния.
- [x] Ограничить portal snapshot client subject + device claim.
- [x] Добавить in-process gRPC ownership check для device/client scope.
- [ ] Добавить production token rotation и revocation check.

## Чекап

В тесте создаются два клиента и две истории; каждый пользователь получает только
свои строки. Повторный login не создаёт новый баланс или ledger operation.
