using System.Diagnostics;
using System.IO.Pipes;
using HubShell.SteamGuest.Core;

namespace HubShell.SteamGuest.Agent;

public sealed class SteamProcessLauncher : ISteamLauncher
{
    private readonly string _steamPath;

    public SteamProcessLauncher(string steamPath)
    {
        if (string.IsNullOrWhiteSpace(steamPath))
        {
            throw new ArgumentException("Не задан путь к steam.exe.", nameof(steamPath));
        }
        _steamPath = steamPath;
    }

    public Task<ISteamProcess> StartAsync(SteamCredentials credentials, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var startInfo = new ProcessStartInfo(_steamPath)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        // Пароль не попадает в shell-строку, файл конфигурации или журнал агента.
        // Windows-администратор всё равно может увидеть параметры процесса, поэтому
        // на игровых ПК требуется ограниченный пользовательский профиль.
        startInfo.ArgumentList.Add("-login");
        startInfo.ArgumentList.Add(credentials.Login);
        startInfo.ArgumentList.Add(credentials.Password);
        startInfo.ArgumentList.Add("-rememberpassword");
        startInfo.ArgumentList.Add("-silent");
        var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Windows не запустила Steam.");
        return Task.FromResult<ISteamProcess>(new ManagedSteamProcess(process));
    }

    private sealed class ManagedSteamProcess : ISteamProcess
    {
        private readonly Process _process;

        public ManagedSteamProcess(Process process) => _process = process;

        public async Task StopAsync(CancellationToken cancellationToken = default)
        {
            if (_process.HasExited)
            {
                return;
            }
            _process.Kill(entireProcessTree: true);
            await _process.WaitForExitAsync(cancellationToken);
        }

        public Task WaitForExitAsync(CancellationToken cancellationToken = default) =>
            _process.WaitForExitAsync(cancellationToken);
    }
}

public sealed class NamedPipeSessionStopSignal : ISessionStopSignal
{
    public const string PipeName = "HubShell.SteamGuest.SessionStopped";

    public async Task WaitAsync(CancellationToken cancellationToken = default)
    {
        await using var pipe = new NamedPipeServerStream(
            PipeName,
            PipeDirection.In,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous);
        await pipe.WaitForConnectionAsync(cancellationToken);
        using var reader = new StreamReader(pipe, leaveOpen: true);
        var message = await reader.ReadLineAsync(cancellationToken);
        if (!string.Equals(message, "session-stopped", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Получен недопустимый локальный сигнал завершения сессии.");
        }
    }
}
