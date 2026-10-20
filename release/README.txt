HubShell — Windows 10/11 x64

Поставка содержит GUI HubShell.exe и отдельную службу HubShell.Watchdog.exe.
HubShell.zip содержит только GUI. HubShell.Setup.zip — начальный комплект
двух EXE, установщиков и server.ini.example.

1. Завершите игровые сеансы и закройте GUI перед первой установкой службы.
   Скопируйте содержимое этой папки в C:\GameClub.
2. Заполните server.ini реальными адресами сервера клуба:
   GrpcAddress=http://IP:51051
   V2EventsHttpAddress=http://IP:8100
   V2SnapshotPublicKeys=key_id=base64 (публичный ключ сервера).
3. start-service.cmd -> правая кнопка -> Запуск от имени администратора.
   Установка службы защищает папку от записи обычными пользователями.
4. Назначьте MAC каждого ПК в админке клуба.

Для подключения управляемых обновлений каждому ПК нужен собственный enrollment
JSON от backend, HTTP-адрес backend и отдельно закреплённый публичный ключ выпуска.
От администратора:
  .\install-windows.ps1 -PublishPath C:\GameClub -InstallPath C:\GameClub -RegisterWatchdogService -UpdaterEnrollmentFile C:\Admin\pc-enrollment.json -UpdateBackendAddress http://SERVER:8100 -UpdatePublicKeyPath C:\Admin\release-public-key.pem
Секрет хранится через machine DPAPI и закрытый ACL; входной enrollment JSON
после установки удалите из места передачи. Без этих параметров служба только
восстанавливает GUI. Не переносите identity, токены и ledger между ПК.

Автодоставка требует серверного CD: опрос всех ПК, общий блок входа, проверка
сервера, pilot и подтверждения каждого клиента. Откат не открывает парк.
Клиентский и серверный manifest из успешного CI подписаны одним ключом и относятся
к одному commit. GitHub Release пока не опубликован, автодоставка выключена.

Сборка проверена на Linux: Windows x64 PE, подписи и ZIP/hash.
Windows SCM/WTS/DPAPI/ACL/file-lock и native запуск ещё не проверены.

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
