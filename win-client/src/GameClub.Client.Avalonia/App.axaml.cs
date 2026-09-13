using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using GameClub.Client.Avalonia.Hosting;
using AvaloniaApplication = Avalonia.Application;

namespace GameClub.Client.Avalonia;

public partial class App : AvaloniaApplication
{
    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new MainWindow(AvaloniaClientHostFactory.Create());
        }

        base.OnFrameworkInitializationCompleted();
    }

    public void ApplyWorkstationTheme(string themeKey)
    {
        var accent = themeKey.Trim().ToLowerInvariant() switch
        {
            "vip" or "vip-зона" => "#C49BFF",
            "neon" or "неон" => "#5BE7FF",
            "minimal" or "минимал" => "#ADB5BD",
            _ => "#B6F35A",
        };

        if (Resources["AccentBrush"] is SolidColorBrush accentBrush)
        {
            accentBrush.Color = Color.Parse(accent);
        }
    }
}
