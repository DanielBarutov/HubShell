using Avalonia;
using GameClub.Client.Application;
using GameClub.Client.Avalonia.Hosting;

namespace GameClub.Client.Avalonia;

internal static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        ClientLog.Initialize("avalonia");
        ClientLog.Info("startup", $"arguments={args.Length} log={ClientLog.FilePath}");
        AppDomain.CurrentDomain.UnhandledException += (_, eventArgs) =>
        {
            if (eventArgs.ExceptionObject is Exception error)
            {
                ClientLog.Exception("unhandled", error, "appdomain exception");
            }
            else
            {
                ClientLog.Error("unhandled", "appdomain exception object is not an Exception");
            }
        };
        TaskScheduler.UnobservedTaskException += (_, eventArgs) =>
        {
            ClientLog.Exception("unhandled", eventArgs.Exception, "unobserved task exception");
        };

#if GAMECLUB_LINUX_V2
        AvaloniaClientHostFactory.Configure(() => new Development.V2LinuxClientHost());
#endif
        try
        {
            BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        }
        catch (Exception error)
        {
            ClientLog.Exception("startup", error, "avalonia lifetime failed");
            throw;
        }
    }

    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .LogToTrace();
}
