using Avalonia;
using System.Runtime.Versioning;
using GameClub.Client.Application;
using GameClub.Client.Avalonia;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Windows;

[SupportedOSPlatform("windows")]
internal static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        if (args.Contains("--watchdog-service", StringComparer.Ordinal))
        {
            System.ServiceProcess.ServiceBase.Run(new ClientWatchdogService());
            return;
        }
        using var instance = new Mutex(true, @"Local\HubShell.Client", out var firstInstance);
        if (!firstInstance)
        {
            return;
        }
        ClientLog.Initialize("windows");
        ClientLog.Info("startup", $"arguments={args.Length} log={ClientLog.FilePath}");
        StartupDiagnostics.Info($"Avalonia Windows startup: PID={Environment.ProcessId}");
        AppDomain.CurrentDomain.UnhandledException += (_, eventArgs) =>
        {
            if (eventArgs.ExceptionObject is Exception error)
            {
                ClientLog.Exception("unhandled", error, "appdomain exception");
                StartupDiagnostics.Error("Unhandled AppDomain exception", error);
            }
        };
        TaskScheduler.UnobservedTaskException += (_, eventArgs) =>
        {
            ClientLog.Exception("unhandled", eventArgs.Exception, "unobserved task exception");
            StartupDiagnostics.Error("Unobserved task exception", eventArgs.Exception);
            eventArgs.SetObserved();
        };

        try
        {
            AvaloniaClientHostFactory.Configure(static () => new WindowsClientHost());
            AppBuilder.Configure<App>()
                .UsePlatformDetect()
                .LogToTrace()
                .StartWithClassicDesktopLifetime(args);
        }
        catch (Exception error)
        {
            ClientLog.Exception("startup", error, "avalonia lifetime failed");
            StartupDiagnostics.Error("Avalonia Windows startup failed", error);
            throw;
        }
    }
}
