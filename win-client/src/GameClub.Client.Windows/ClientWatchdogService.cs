using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.ServiceProcess;
using System.Text;

namespace GameClub.Client.Windows;

[SupportedOSPlatform("windows")]
internal sealed class ClientWatchdogService : ServiceBase
{
    private CancellationTokenSource? _stop;
    private Task? _loop;

    public ClientWatchdogService()
    {
        ServiceName = "HubShell.Watchdog";
        CanShutdown = true;
        AutoLog = true;
    }

    protected override void OnStart(string[] args)
    {
        _stop = new CancellationTokenSource();
        _loop = Task.Run(() => WatchAsync(_stop.Token));
    }

    protected override void OnStop()
    {
        _stop?.Cancel();
        _loop?.GetAwaiter().GetResult();
        _stop?.Dispose();
        _stop = null;
        _loop = null;
    }

    protected override void OnShutdown() => OnStop();

    private async Task WatchAsync(CancellationToken cancellationToken)
    {
        var executable = Environment.ProcessPath
            ?? throw new InvalidOperationException("Cannot locate watchdog executable");
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(2));
        try
        {
            do
            {
                try
                {
                    var sessionId = WTSGetActiveConsoleSessionId();
                    if (ClientProcessRecovery.RestoreIfMissing(sessionId == uint.MaxValue ? null : sessionId,
                            session => ClientIsRunning(executable, session),
                            session => LaunchInUserSession(executable, session)))
                    {
                        // shortcut: one local console user, add WTS session enumeration for RDP deployments.
                        WriteRecoveryLog("Клиент восстановлен в пользовательской сессии.", EventLogEntryType.Information);
                        await Task.Delay(TimeSpan.FromSeconds(10), cancellationToken);
                    }
                }
                catch (Win32Exception error) when (error.NativeErrorCode == 1008)
                {
                    // Console session exists before its user token is available at logon.
                }
                catch (Exception error) when (error is not OperationCanceledException)
                {
                    WriteRecoveryLog($"Не удалось восстановить клиент: {error.Message}", EventLogEntryType.Error);
                    await Task.Delay(TimeSpan.FromSeconds(10), cancellationToken);
                }
            } while (await timer.WaitForNextTickAsync(cancellationToken));
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    private void WriteRecoveryLog(string message, EventLogEntryType type)
    {
        try
        {
            EventLog.WriteEntry(message, type);
        }
        catch (Exception error)
        {
            Trace.TraceError($"Watchdog Event Log unavailable: {error.Message}");
        }
    }

    private static bool ClientIsRunning(string executable, uint sessionId)
    {
        foreach (var process in Process.GetProcessesByName("HubShell"))
        {
            using (process)
            {
                try
                {
                    if (process.SessionId == sessionId
                        && string.Equals(process.MainModule?.FileName, executable, StringComparison.OrdinalIgnoreCase))
                    {
                        return true;
                    }
                }
                catch (InvalidOperationException)
                {
                    // Process exited between enumeration and inspection.
                }
            }
        }
        return false;
    }

    private static void LaunchInUserSession(string executable, uint sessionId)
    {
        if (!WTSQueryUserToken(sessionId, out var token))
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        var environment = IntPtr.Zero;
        try
        {
            if (!CreateEnvironmentBlock(out environment, token, false))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            var startup = new StartupInfo
            {
                Size = Marshal.SizeOf<StartupInfo>(),
                Desktop = @"winsta0\default",
            };
            if (!CreateProcessAsUser(token, executable, new StringBuilder($"\"{executable}\""),
                    IntPtr.Zero, IntPtr.Zero, false, 0x00000400, environment,
                    Path.GetDirectoryName(executable) ?? throw new InvalidOperationException("Cannot locate client directory"),
                    ref startup, out var process))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error());
            }
            CloseHandle(process.Thread);
            CloseHandle(process.Process);
        }
        finally
        {
            if (environment != IntPtr.Zero)
            {
                DestroyEnvironmentBlock(environment);
            }
            CloseHandle(token);
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo
    {
        public int Size;
        public string? Reserved;
        public string? Desktop;
        public string? Title;
        public uint X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
        public ushort ShowWindow, ReservedSize;
        public IntPtr ReservedData, StandardInput, StandardOutput, StandardError;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInformation
    {
        public IntPtr Process, Thread;
        public uint ProcessId, ThreadId;
    }

    [DllImport("kernel32.dll")]
    private static extern uint WTSGetActiveConsoleSessionId();
    [DllImport("wtsapi32.dll", SetLastError = true)]
    private static extern bool WTSQueryUserToken(uint sessionId, out IntPtr token);
    [DllImport("userenv.dll", SetLastError = true)]
    private static extern bool CreateEnvironmentBlock(out IntPtr environment, IntPtr token, bool inherit);
    [DllImport("userenv.dll")]
    private static extern bool DestroyEnvironmentBlock(IntPtr environment);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcessAsUser(IntPtr token, string application, StringBuilder commandLine,
        IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment,
        string currentDirectory, ref StartupInfo startup, out ProcessInformation process);
}
