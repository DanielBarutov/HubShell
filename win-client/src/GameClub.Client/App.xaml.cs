using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using GameClub.Client.Infrastructure;
using XamlApplication = Microsoft.UI.Xaml.Application;

namespace GameClub.Client;

public partial class App : XamlApplication
{
    public static MainWindow? MainWindow { get; private set; }

    public App()
    {
        StartupDiagnostics.Info("App constructor: begin");
        UnhandledException += AppUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += CurrentDomainUnhandledException;
        TaskScheduler.UnobservedTaskException += TaskSchedulerUnobservedTaskException;
        InitializeComponent();
        StartupDiagnostics.Info("App constructor: completed");
    }

    public void ApplyWorkstationTheme(string themeKey)
    {
        var palette = themeKey.Trim().ToLowerInvariant() switch
        {
            "vip" => (accent: ColorHelper.FromArgb(255, 196, 155, 255), lightAccent: ColorHelper.FromArgb(255, 143, 102, 207)),
            "neon" => (accent: ColorHelper.FromArgb(255, 91, 231, 255), lightAccent: ColorHelper.FromArgb(255, 20, 158, 188)),
            "minimal" => (accent: ColorHelper.FromArgb(255, 173, 181, 189), lightAccent: ColorHelper.FromArgb(255, 108, 117, 125)),
            _ => (accent: ColorHelper.FromArgb(255, 168, 237, 98), lightAccent: ColorHelper.FromArgb(255, 143, 216, 84)),
        };

        if (Resources.ThemeDictionaries["Dark"] is ResourceDictionary dark)
        {
            dark["AccentBrush"] = new SolidColorBrush(palette.accent);
        }
        if (Resources.ThemeDictionaries["Light"] is ResourceDictionary light)
        {
            light["AccentBrush"] = new SolidColorBrush(palette.lightAccent);
        }
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _ = args;
        StartupDiagnostics.Info($"OnLaunched: begin, PID={Environment.ProcessId}");
        try
        {
            MainWindow = new MainWindow();
            StartupDiagnostics.Info("OnLaunched: MainWindow constructed");
            MainWindow.Activate();
            StartupDiagnostics.Info("OnLaunched: MainWindow activated");
        }
        catch (Exception error)
        {
            StartupDiagnostics.Error("OnLaunched: fatal startup error", error);
            throw;
        }
    }

    private void AppUnhandledException(
        object sender,
        Microsoft.UI.Xaml.UnhandledExceptionEventArgs args)
    {
        _ = sender;
        StartupDiagnostics.Error("WinUI unhandled exception", args.Exception);
    }

    private static void CurrentDomainUnhandledException(
        object? sender,
        System.UnhandledExceptionEventArgs args)
    {
        _ = sender;
        if (args.ExceptionObject is Exception error)
        {
            StartupDiagnostics.Error("AppDomain unhandled exception", error);
        }
        else
        {
            StartupDiagnostics.Info($"AppDomain unhandled non-Exception: {args.ExceptionObject}");
        }
    }

    private static void TaskSchedulerUnobservedTaskException(
        object? sender,
        UnobservedTaskExceptionEventArgs args)
    {
        _ = sender;
        StartupDiagnostics.Error("Unobserved background task exception", args.Exception);
        args.SetObserved();
    }
}
