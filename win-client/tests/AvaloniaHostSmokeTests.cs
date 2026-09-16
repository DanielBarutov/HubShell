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
        Assert.Equal(390, window.MinWidth);
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
        var login = window.FindControl<Button>("PortalLoginButton");
        var registration = window.FindControl<Button>("OpenPortalRegistrationButton");
        var feedback = window.FindControl<Border>("AccessFeedbackPanel");
        Assert.NotNull(login);
        Assert.NotNull(registration);
        Assert.NotNull(feedback);
        Assert.Contains("access-primary", login.Classes);
        Assert.Contains("access-secondary", registration.Classes);
        Assert.False(feedback.IsVisible);
        Assert.NotNull(window.FindControl<Border>("UpcomingBookingPanel"));
        Assert.NotNull(window.FindControl<ItemsControl>("PortalTariffList"));
        Assert.NotNull(window.FindControl<ItemsControl>("PortalEntitlementQueueList"));
        Assert.NotNull(window.FindControl<Border>("TransferPanel"));
        Assert.NotNull(window.FindControl<Button>("OpenAccountHistoryButton"));
        Assert.Null(window.FindControl<Expander>("PortalHistory"));
        Assert.NotNull(window.FindControl<Border>("WindowContentSurface"));
        Assert.False(window.FindControl<Button>("HideToTrayButton")!.IsVisible);
    }

    [Fact]
    public void AccountHistoryIsASeparateBorderlessClientWindowWithCloseControl()
    {
        EnsureAvaloniaInitialized();

        var app = new App();
        app.Initialize();
        var window = new MainWindow();
        var history = new AccountHistoryWindow((MainViewModel)window.DataContext!, useTransparentWindow: false);

        Assert.Equal(SystemDecorations.None, history.SystemDecorations);
        Assert.False(history.CanResize);
        var closeButton = history.FindControl<Button>("CloseAccountHistoryButton");
        Assert.NotNull(closeButton);
        Assert.Equal(HorizontalAlignment.Center, closeButton.HorizontalContentAlignment);
        Assert.Equal(VerticalAlignment.Center, closeButton.VerticalContentAlignment);
        Assert.NotNull(history.FindControl<ItemsControl>("AccountBalanceHistory"));
        Assert.NotNull(history.FindControl<ItemsControl>("AccountPurchaseHistory"));
        Assert.Null(history.FindControl<ItemsControl>("AccountChargeHistory"));
        Assert.NotNull(history.FindControl<ItemsControl>("AccountSessionHistory"));
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
