# HubShell Steam Guest

Отдельный сервис гостевых Steam-аккаунтов и фоновый Windows-агент
`HubShellSteam.exe`. В проекте нет web-интерфейса: предусмотрен только
служебный HTTP API для регистрации станций, аккаунтов и выдачи аренды.

Для запуска нужны переменные окружения сервиса:

- `STEAM_GUEST_POSTGRES_DSN`;
- `STEAM_GUEST_MASTER_KEY` — base64 от 32 случайных байтов;
- `STEAM_GUEST_ADMIN_KEY` — ключ администратора для добавления станций и
  аккаунтов.

Агент получает `HUBSHELL_STEAM_SERVER_URL`, `HUBSHELL_STEAM_STATION_ID`,
`HUBSHELL_STEAM_STATION_KEY` и путь к `steam.exe`. Секреты не добавляются в
репозиторий и не передаются через аргументы командной строки.

