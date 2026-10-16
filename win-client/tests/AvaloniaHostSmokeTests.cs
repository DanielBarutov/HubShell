using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Styling;
using GameClub.Client.Avalonia;
using GameClub.Client.Presentation;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class AvaloniaHostSmokeTests
{
    [Fact]
    public void FreeMinuteRateShowsUnlimitedTimeInWidget()
    {
        EnsureAvaloniaInitialized();
        var vm = (MainViewModel)new MainWindow().DataContext!;
        var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
        var ledger = GameClub.Client.Domain.V2LocalSessionLedger.Create(1, Guid.NewGuid(), Guid.NewGuid(),
            "device-01", null, 0, 0, 0, [],
            [new("rate", "Admin", null, 0, 0, 0, false, IsPerMinute: true)]);
        typeof(MainViewModel).GetMethod("OpenV2Session", flags)!.Invoke(vm, [ledger, "Тест"]);
        Assert.Equal("∞", vm.WidgetTimerSummary);
        Assert.Equal("Бесплатно", vm.ActiveTimeSummary);
    }

    private static readonly object AvaloniaSetupLock = new();
    private static bool _isAvaloniaInitialized;

    [Fact]
    public void MainWindowCanBeCreatedOnTheHeadlessPlatform()
    {
        EnsureAvaloniaInitialized();

        var app = new App();
        app.Initialize();

        var window = new MainWindow();

        Assert.Equal(ThemeVariant.Dark, app.RequestedThemeVariant);
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
        Assert.True(window.FindControl<Button>("HideToTrayButton")!.IsVisible);
        Assert.False(window.FindControl<Button>("CompactWidgetButton")!.IsVisible);
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

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void WidgetCollapsesAndRestoresWithoutEndingSessionAndLockRestoresGate(bool guest)
    {
        EnsureAvaloniaInitialized();
        var window = new MainWindow();
        var vm = (MainViewModel)window.DataContext!;
        var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
        var ledger = GameClub.Client.Domain.V2LocalSessionLedger.Create(1, Guid.NewGuid(), Guid.NewGuid(),
            "device-01", null, 0, 0, 147, [], [], guestPaymentId: guest ? Guid.NewGuid() : null);
        var profile = new GameClub.Client.Domain.ClientPortalSnapshot(
            "client", "Игрок", "79990000000", 0, 0, 0, [], [], [], [], [], [], []);
        typeof(MainViewModel).GetMethod("SetPortalSnapshot", flags)!.Invoke(vm, [profile]);
        typeof(MainViewModel).GetMethod("OpenV2Session", flags)!.Invoke(vm, [ledger, "Тест"]);
        global::Avalonia.Threading.Dispatcher.UIThread.RunJobs();
        Assert.True(vm.IsWidgetContentVisible);
        Assert.False(window.Topmost);
        Assert.Equal("02:27", vm.WidgetTimerSummary);
        var animate = typeof(MainWindow).GetMethod("AnimateWidget", flags)!;
        animate.Invoke(window, [true]);
        PumpAnimation();
        Assert.Equal(68, window.Width);
        Assert.Equal(280, window.Height);
        Assert.True(window.FindControl<Button>("CompactWidgetButton")!.IsVisible);
        Assert.False(window.FindControl<Grid>("ExpandedWidgetContainer")!.IsVisible);
        Assert.True(vm.IsActiveSessionVisible);
        animate.Invoke(window, [false]);
        PumpAnimation();
        Assert.Equal(390, window.Width);
        Assert.True(window.FindControl<Grid>("ExpandedWidgetContainer")!.IsVisible);
        Assert.False(window.FindControl<Button>("CompactWidgetButton")!.IsVisible);
        animate.Invoke(window, [true]);
        vm.ShowManagerLogin();
        global::Avalonia.Threading.Dispatcher.UIThread.RunJobs();
        Assert.True(vm.IsAccessLocked);
        Assert.True(window.Topmost);
        Assert.False(window.FindControl<Button>("CompactWidgetButton")!.IsVisible);
        Assert.Equal(1120, window.Width);
    }

    private static void PumpAnimation()
    {
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(350));
        global::Avalonia.Threading.Dispatcher.UIThread.MainLoop(cancellation.Token);
    }

    [Fact]
    public void ShowingTheSameWindowAgainDoesNotRestartItsHostOrResetItsGeometry()
    {
        EnsureAvaloniaInitialized();
        var vm = (MainViewModel)new MainWindow().DataContext!;
        var host = new CountingHost(vm);
        var window = new MainWindow(host);
        var opened = typeof(MainWindow).GetMethod("MainWindowOpened",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        opened.Invoke(window, [null, EventArgs.Empty]);
        window.MinWidth = 68;
        window.MinHeight = 0;
        window.Width = 68;
        window.Height = 280;
        opened.Invoke(window, [null, EventArgs.Empty]);
        Assert.Equal(1, host.Starts);
        Assert.Equal(68, window.Width);
        Assert.Equal(280, window.Height);
    }

    [Fact]
    public void HidingTheClientCancelsPendingConfirmationAndReleasesItsWindow()
    {
        EnsureAvaloniaInitialized();
        var host = new CountingHost((MainViewModel)new MainWindow().DataContext!);
        var window = new MainWindow(host);
        window.Show();
        var flags = System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic;
        var pending = (Task<bool>)typeof(MainWindow).GetMethod("ShowConfirmationAsync", flags)!
            .Invoke(window, ["Подтвердите покупку", "Сумма будет списана с баланса.", "Купить"])!;
        Assert.False(pending.IsCompleted);
        var dialog = Assert.Single(window.OwnedWindows);
        var closed = false;
        dialog.Closed += (_, _) => closed = true;
        window.Hide();
        global::Avalonia.Threading.Dispatcher.UIThread.RunJobs();
        Assert.False(pending.GetAwaiter().GetResult());
        Assert.True(closed);
        typeof(Window).GetMethod("CloseCore", flags)!.Invoke(window, [WindowCloseReason.OSShutdown, true, true]);
    }

    private sealed class CountingHost(MainViewModel viewModel) : GameClub.Client.Avalonia.Hosting.IClientHost
    {
        public int Starts { get; private set; }
        public MainViewModel ViewModel => viewModel;
        public string WindowTitle => "Test";
        public string HostDisclaimer => "";
        public GameClub.Client.Avalonia.Hosting.IClientWindowAdapter? WindowAdapter => null;
        public Task StartAsync() { Starts++; return Task.CompletedTask; }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    [Theory]
    [InlineData(WindowCloseReason.WindowClosing, true)]
    [InlineData(WindowCloseReason.ApplicationShutdown, true)]
    [InlineData(WindowCloseReason.OSShutdown, false)]
    public void OrdinaryClosingIsCancelledButWindowsShutdownIsAllowed(WindowCloseReason reason, bool cancelled)
    {
        EnsureAvaloniaInitialized();
        var window = new MainWindow();
        var args = (WindowClosingEventArgs)Activator.CreateInstance(typeof(WindowClosingEventArgs),
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic,
            binder: null, args: [reason, false], culture: null)!;
        typeof(MainWindow).GetMethod("OnClosing", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
            .Invoke(window, [args]);
        Assert.Equal(cancelled, args.Cancel);
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
