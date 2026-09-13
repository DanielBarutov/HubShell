using Avalonia;
using System.Runtime.Versioning;
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
        StartupDiagnostics.Info($"Avalonia Windows startup: PID={Environment.ProcessId}");
        AppDomain.CurrentDomain.UnhandledException += (_, eventArgs) =>
        {
            if (eventArgs.ExceptionObject is Exception error)
            {
                StartupDiagnostics.Error("Unhandled AppDomain exception", error);
            }
        };
        TaskScheduler.UnobservedTaskException += (_, eventArgs) =>
        {
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
            StartupDiagnostics.Error("Avalonia Windows startup failed", error);
            throw;
        }
    }
}
