using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Layout;
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

        Assert.Equal("HubShell, Linux developer host", window.Title);
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
        Assert.NotNull(window.FindControl<Border>("PortalWidgetSurface"));
        Assert.NotNull(window.FindControl<Border>("WidgetNotificationPanel"));
        Assert.NotNull(window.FindControl<Grid>("WidgetFooterActions"));
        Assert.Equal(1, Grid.GetColumn(window.FindControl<Button>("OpenAccountHistoryButton")!));
        Assert.Equal(0, Grid.GetColumn(window.FindControl<Button>("ToggleTransferButton")!));
        Assert.NotNull(window.FindControl<Button>("ToggleTransferButton"));
        Assert.False(window.FindControl<Button>("GuestTransferButton")!.IsEnabled);
        Assert.NotNull(window.FindControl<Button>("ActivatePortalEntitlementButton"));
        Assert.Null(window.FindControl<Expander>("PortalHistory"));
        Assert.NotNull(window.FindControl<Border>("WindowContentSurface"));
        Assert.NotNull(window.FindControl<Button>("PortalLogoutButton"));
        Assert.NotNull(window.FindControl<Button>("StopActiveSessionButton"));
        Assert.NotNull(window.FindControl<Button>("OpenDesktopButton"));
        Assert.False(window.FindControl<Button>("HideToTrayButton")!.IsVisible);
        Assert.False(window.FindControl<Button>("OpenDesktopButton")!.IsVisible);
    }

    [Fact]
    public void NeonAccessGateLoadsItsBundledBackground()
    {
        EnsureAvaloniaInitialized();
        var window = new MainWindow();
        Assert.NotNull(window.FindControl<Image>("AccessGateBackground")!.Source);
        Assert.NotNull(window.FindControl<Border>("AccessLoginCard"));
    }

    [Fact]
    public void RegistrationUsesTheNeonFormAndKeepsTheReturnToLoginRoute()
    {
        EnsureAvaloniaInitialized();
        var window = new MainWindow();
        var viewModel = (MainViewModel)window.DataContext!;
        viewModel.ShowPortalRegistration();
        Assert.True(viewModel.IsPortalRegistrationVisible);
        Assert.False(viewModel.IsUserLoginVisible);
        foreach (var name in new[] { "PortalNicknameBox", "PortalPhoneBox", "PortalRegistrationPasswordBox" })
            Assert.Contains("neon-input", window.FindControl<TextBox>(name)!.Classes);
        Assert.Equal(HorizontalAlignment.Stretch, window.FindControl<Button>("PortalRegisterButton")!.HorizontalAlignment);
        Assert.NotNull(window.FindControl<Button>("BackToPortalLoginButton"));
        viewModel.CancelPortalRegistration();
        Assert.True(viewModel.IsUserLoginVisible);
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
        Assert.Equal(SizeToContent.Height, history.SizeToContent);
        Assert.Equal(650, history.MaxHeight);
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
    public void ConfirmationFitsItsContentAndKeepsBothActionsAndWarning()
    {
        EnsureAvaloniaInitialized();
        var window = new MainWindow();
        var method = typeof(MainWindow).GetMethod("CreateConfirmationDialog",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        var dialog = (Window)method.Invoke(window,
            ["Завершить игровую сессию?", "Неиспользованные минуты текущего пакета сгорят.", "Завершить"])!;
        Assert.Equal(SizeToContent.Height, dialog.SizeToContent);
        Assert.Equal(SystemDecorations.None, dialog.SystemDecorations);
        var content = (StackPanel)((Border)dialog.Content!).Child!;
        Assert.Contains("сгорят", ((TextBlock)content.Children[1]).Text);
        var actions = (StackPanel)content.Children[2];
        Assert.Equal("Отмена", ((Button)actions.Children[0]).Content);
        Assert.Contains("widget-secondary", ((Button)actions.Children[0]).Classes);
        Assert.Equal("Завершить", ((Button)actions.Children[1]).Content);
        Assert.Contains("widget-primary", ((Button)actions.Children[1]).Classes);
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
