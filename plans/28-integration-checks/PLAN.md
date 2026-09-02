# План 28 — сквозные чекапы нового клиентского сценария

Статус: `in_progress`  
Владелец: `backend/`, `frontend/`, `win-client/`  
Связи: планы 23–27 и `VERIFICATION.md`

## Сквозной сценарий

- [x] Поднять Compose и применить Alembic до актуальной головы.
- [x] Прогнать backend lint/tests, HTTP enrollment и in-process gRPC portal scope.
- [x] Прогнать frontend typecheck/build.
- [ ] Создать зону и workstation только с MAC в админке.
- [ ] Запустить EXE на реальном игровом ПК без env и консоли.
- [ ] Подтвердить `pending` до назначения и `approved` после назначения.
- [ ] Проверить heartbeat, theme, lockdown policy и reconnect.
- [ ] Зарегистрировать пользователя на locked screen.
- [ ] Войти вторым запуском и увидеть только собственный профиль/историю.
- [ ] Запустить поминутную сессию, проверить доступное время и debit ledger.
- [ ] Купить товар, проверить purchase history и отсутствие двойного списания.
- [ ] Открыть менеджера через `Ctrl+Alt+P`, закрыть maintenance и снова заблокировать.
- [ ] Проверить Windows desktop boundary через Assigned Access/Shell Launcher.

## Артефакты

- Backend pytest/ruff/format и migration output.
- Frontend typecheck/build и screenshot карты/настроек.
- Windows `dotnet test`, native publish output, event/log evidence и manual matrix.
- Обновлённый `plans/SUMMARY.md` с разделением `проверено`, `source-level`,
  `не проверено`.
