using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Media;
using GameClub.Client.Avalonia;
using GameClub.Client.Presentation;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class AvaloniaHostSmokeTests
{
    private static readonly object AvaloniaSetupLock = new();
    private static bool _isAvaloniaInitialized;

    [Fact]
    public void MainWindowCanBeCreatedOnTheHeadlessPlatform()
    {
        EnsureAvaloniaInitialized();

        var app = new App();
        app.Initialize();

        var window = new MainWindow();

        Assert.Equal("HubShell client — Linux developer host", window.Title);
        Assert.IsType<MainViewModel>(window.DataContext);
        Assert.True(((MainViewModel)window.DataContext!).IsAccessGateVisible);
    }

    [Fact]
    public void MainWindowContainsAllServerBackedPortalAndMaintenanceSurfaces()
    {
        EnsureAvaloniaInitialized();

        var app = new App();
        app.Initialize();
        var window = new MainWindow();

        Assert.NotNull(window.FindControl<TextBox>("PortalIdentifierBox"));
        Assert.NotNull(window.FindControl<TextBox>("PortalPasswordBox"));
        Assert.NotNull(window.FindControl<TextBox>("PortalPhoneBox"));
        Assert.NotNull(window.FindControl<TextBox>("ManagerPasswordBox"));
        Assert.NotNull(window.FindControl<StackPanel>("MaintenancePanel"));
        Assert.NotNull(window.FindControl<Border>("UpcomingBookingPanel"));
        Assert.NotNull(window.FindControl<ItemsControl>("PortalTariffList"));
        Assert.NotNull(window.FindControl<ItemsControl>("PortalEntitlementQueueList"));
        Assert.NotNull(window.FindControl<Border>("TransferPanel"));
        Assert.NotNull(window.FindControl<Expander>("PortalHistory"));
        Assert.False(window.FindControl<Button>("HideToTrayButton")!.IsVisible);
    }

    [Fact]
    public void WorkstationThemeChangesTheSharedAvaloniaAccentResource()
    {
        EnsureAvaloniaInitialized();

        var app = new App();
        app.Initialize();
        app.ApplyWorkstationTheme("vip");

        var accent = Assert.IsType<SolidColorBrush>(app.Resources["AccentBrush"]);
        Assert.Equal(Color.Parse("#C49BFF"), accent.Color);
    }

    private static void EnsureAvaloniaInitialized()
    {
        lock (AvaloniaSetupLock)
        {
            if (_isAvaloniaInitialized)
            {
                return;
            }

            AppBuilder.Configure<App>()
                .UseHeadless(new AvaloniaHeadlessPlatformOptions())
                .SetupWithoutStarting();
            _isAvaloniaInitialized = true;
        }
    }
}
