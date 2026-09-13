# План 38 — platform inventory

Дата: `2026-09-13`  
Статус: первая Linux-сборка выполнена; полный UI migration ещё не начат.

| Текущий компонент | Текущая зависимость | Целевая граница | Linux developer-host сейчас |
| --- | --- | --- | --- |
| `App.xaml`, `MainWindow.xaml`, code-behind | WinUI / Windows App SDK | `GameClub.Client.Avalonia` App/MainWindow | Avalonia diagnostic window запущен; product UI не перенесён |
| `Presentation/MainViewModel.cs` | `Microsoft.UI.Xaml.Visibility` | Core state + Avalonia bindings/converters | остаётся legacy; перенос — следующий этап |
| `NativeTrayIcon.cs` | `shell32.dll`, `user32.dll`, HWND WndProc | future `ITrayController` Windows adapter | отсутствует намеренно |
| `JsonlOfflineJournal.cs` | DPAPI `ProtectedData` | existing `IOfflineJournal` port + Windows adapter | отсутствует намеренно; replay не имитируется |
| `WindowsWorkstationPowerController.cs` | `shutdown.exe` | existing `IWorkstationPowerController` port + Windows adapter | отсутствует намеренно |
| `WindowsCommandExecutor.cs` | Windows default power adapter | portable executor после отдельного extraction | остаётся legacy до переноса power composition |
| `GrpcBackendClient.cs`, enrollment/token providers | gRPC, MAC, AppData identity | portable infrastructure after composition extraction | не запускаются в diagnostic host |
| `Domain/`, `Application/`, `Application/Ports/` | platform-neutral C# | `GameClub.Client.Core` (`net8.0`) | compiled from linked legacy source files |

`GameClub.Client.Core` deliberately links portable source from the legacy tree in
this first step. No files were deleted or moved, so the legacy WinUI host remains
available for later Windows comparison. Core has no references to
`Microsoft.UI.*`, Windows App SDK, DPAPI, `user32.dll`, or `shell32.dll`.
