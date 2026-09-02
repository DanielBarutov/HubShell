# План 27 — portable EXE без ручной настройки на игровом ПК

Статус: `in_progress`  
Владелец: `win-client/`  
Связи: `15-win-client`, [`24-windows-shell/PLAN.md`](../24-windows-shell/PLAN.md)

## Результат

Администратор собирает один self-contained EXE на своей Windows-машине и
передаёт его на игровой ПК. На игровом ПК не нужны PowerShell, Visual Studio,
.NET SDK, ручные env-переменные, генерация PIN-хэшей или bootstrap token.

## Этапы

- [x] Зафиксировать backend endpoint в production EXE через стабильный HTTPS/DNS
  deployment parameter; не встраивать секреты.
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
