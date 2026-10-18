HubShell — Windows 10/11 x64

1. Скопируйте содержимое этой папки в C:\GameClub.
2. Заполните server.ini реальными адресами сервера клуба:
   GrpcAddress=http://IP:51051
   V2EventsHttpAddress=http://IP:8100
   V2SnapshotPublicKeys=key_id=base64 (публичный ключ сервера).
3. start-service.cmd -> правая кнопка -> Запуск от имени администратора.
   Установка службы защищает папку от записи обычными пользователями.
4. Назначьте MAC каждого ПК в админке клуба.

.NET/SDK устанавливать не нужно. После перезагрузки служба запускается сама.
Если служба уже настроена для другой папки, сначала удалите старую установку.
Для изменения INI/обновления EXE сначала завершите игровую сессию,
остановите службу и GUI; меняйте файлы от администратора.
PowerShell от администратора:
  Stop-Service HubShell.Watchdog
  (после остановки службы закройте процесс HubShell через диспетчер задач)
  Start-Service HubShell.Watchdog

Удаление (сохраняет runtime-данные):
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\GameClub\uninstall-windows.ps1 -InstallPath C:\GameClub -RemoveWatchdogService -ConfirmRemoval
