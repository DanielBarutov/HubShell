using Avalonia;
using System.Runtime.Versioning;
using GameClub.Client.Avalonia;
using GameClub.Client.Avalonia.Hosting;

namespace GameClub.Client.Windows;

[SupportedOSPlatform("windows")]
internal static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        AvaloniaClientHostFactory.Configure(static () => new WindowsClientHost());
        AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .LogToTrace()
            .StartWithClassicDesktopLifetime(args);
    }
}
