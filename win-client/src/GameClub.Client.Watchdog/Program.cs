using System.Runtime.Versioning;
using System.ServiceProcess;
using GameClub.Client.Windows;

namespace GameClub.Client.Watchdog;

[SupportedOSPlatform("windows")]
internal static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length > 0)
        {
            try
            {
                if (args.Length == 4 && args[0] == "--configure-updater")
                    WindowsUpdaterSettings.Configure(AppContext.BaseDirectory, args[1], args[2], args[3]);
                else if (args.Length == 1 && args[0] == "--validate-updater-config")
                    _ = WindowsUpdaterSettings.Load(AppContext.BaseDirectory)?.DecryptSecret()
                        ?? throw new InvalidDataException("Updater configuration is missing");
                else throw new ArgumentException("Unsupported watchdog arguments");
                return 0;
            }
            catch (Exception error)
            {
                Console.Error.WriteLine("Updater configuration failed: " + error.GetType().Name);
                return 1;
            }
        }
        ServiceBase.Run(new ClientWatchdogService(WindowsClientUpdateRuntime.RunAsync, WindowsClientUpdateRuntime.RequiresRecovery()));
        return 0;
    }
}
