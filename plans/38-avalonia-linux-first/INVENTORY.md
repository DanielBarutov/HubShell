# План 38 — platform inventory

Дата: `2026-09-17`
Статус: Avalonia UI migration completed; native Windows evidence remains open.

| Компонент | Production boundary | Linux developer-host | Windows evidence |
| --- | --- | --- | --- |
| `GameClub.Client.Avalonia` | Avalonia App/MainWindow, access-gate, portal, manager route | build/test/UI-smoke | fullscreen, Topmost, tray и window placement |
| `GameClub.Client.Core` | portable domain/application/ports и shared presentation state | compiled and tested | reused by Windows host |
| `NativeTrayIcon.cs` | Windows tray adapter за `IClientWindowAdapter` | не активируется | native tray smoke |
| `JsonlOfflineJournal.cs` | DPAPI-backed Windows offline journal | portable boundary only | restart/reconnect smoke |
| `WindowsWorkstationPowerController.cs` | Windows restart/power adapter | portable boundary only | server-side stop/restart smoke |
| `WindowsCommandExecutor.cs` | Windows command adapter | portable tests | command/ACK smoke |
| `GrpcBackendClient.cs`, enrollment/token providers | portable gRPC/MAC/AppData infrastructure | compiled and tested | device-auth heartbeat smoke |
| `GameClub.Client.Windows` | Windows production composition | cross-build | publish/runtime on Windows |

Portable source is shared by the Avalonia hosts. A second UI implementation is
not part of the production build graph. Linux checks do not prove DPAPI, tray,
fullscreen window behavior, user policy or kiosk security; those remain native
Windows evidence.
