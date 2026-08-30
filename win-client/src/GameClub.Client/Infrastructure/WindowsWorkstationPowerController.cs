using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Infrastructure;

public sealed class WindowsWorkstationPowerController : IWorkstationPowerController
{
    public CommandExecutionResult ScheduleRestart()
    {
        if (!OperatingSystem.IsWindows())
        {
            return new CommandExecutionResult(false, "Перезапуск доступен только в Windows");
        }

        try
        {
            using var process = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = "shutdown.exe",
                Arguments = "/r /t 5 /d p:0:0",
                UseShellExecute = false,
                CreateNoWindow = true,
            });
            return process is null
                ? new CommandExecutionResult(false, "Windows не запустила перезапуск")
                : new CommandExecutionResult(true, "Перезапуск Windows запланирован через 5 секунд");
        }
        catch (Exception error) when (error is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return new CommandExecutionResult(false, "Не удалось запланировать перезапуск Windows");
        }
    }
}
