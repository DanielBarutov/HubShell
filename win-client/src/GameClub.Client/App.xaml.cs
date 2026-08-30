using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace GameClub.Client;

public partial class App : Application
{
    public static MainWindow? MainWindow { get; private set; }

    public App()
    {
        InitializeComponent();
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
        MainWindow = new MainWindow();
        MainWindow.Activate();
    }
}
