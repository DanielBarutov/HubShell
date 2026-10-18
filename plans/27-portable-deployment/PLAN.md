# План 27 — portable EXE без ручной настройки на игровом ПК

2026-10-11: переносимая self-contained папка `release/` для Windows x64.
Адреса/публичные ключи — в `server.ini`, запуск watchdog на месте в `C:\GameClub`
через `start-service.cmd` от администратора с защитой ACL. Учётные записи не меняются.
Native Windows запуск/SCM/ACL остаются отдельной проверкой.

Статус: `in_progress`  
Владелец: `win-client/`  
Связи: `15-win-client`, [`24-windows-shell/PLAN.md`](../24-windows-shell/PLAN.md)

## Результат

Администратор получает self-contained папку release с EXE и server.ini,
передаёт её в C:\GameClub и один раз запускает скрипт службы от администратора.
На игровом ПК не нужны Visual Studio, .NET SDK/runtime, ручные env-переменные,
генерация PIN-хэшей или bootstrap token. Сборка возможна на Linux.

## Этапы

- [x] Читать адреса backend из server.ini рядом с production EXE; сохранить
  существующие env/metadata overrides, не включать секреты.
- [x] Хранить случайный installation id в AppData.
- [ ] Хранить device/client tokens в Windows Credential Manager или защищённом
  DPAPI-хранилище; не в EXE и не в логах.
- [x] Обновить `build-portable-exe.ps1` с ясными параметрами endpoint и checksum.
- [x] Убрать env/secret setup из optional install script; запуск EXE не требует
  административных console commands.
- [ ] Добавить автозапуск без административных console commands либо отдельный
  обратимый installer bootstrap.
- [ ] Проверить single-file runtime на чистой x64 Windows под обычным пользователем.
- [x] Подготовить короткую инструкцию: скопировать EXE, запустить, MAC назначить
  в админке.

## Не считать выполненным

Успешный `dotnet publish` на админском ПК не доказывает запуск на клиентском ПК.
Нужен native smoke без SDK и без elevated shell.
