using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using WinRT.Interop;
using XamlApplication = Microsoft.UI.Xaml.Application;

namespace GameClub.Client;

public sealed partial class MainWindow : Window
{
    private readonly MainViewModel _viewModel;
    private readonly AppWindow _appWindow;
    private readonly IWorkstationPowerController _powerController;
    private readonly DeviceEnrollmentTokenProvider _enrollmentTokenProvider;

    public MainWindow()
    {
        InitializeComponent();
        var windowHandle = WindowNative.GetWindowHandle(this);
        var windowId = Win32Interop.GetWindowIdFromWindow(windowHandle);
        _appWindow = AppWindow.GetFromWindowId(windowId);
        if (_appWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.SetBorderAndTitleBar(false, false);
            presenter.IsResizable = false;
            presenter.IsMaximizable = false;
            presenter.IsMinimizable = false;
        }
        _appWindow.SetPresenter(AppWindowPresenterKind.FullScreen);
        Closed += MainWindowClosed;
        Activated += MainWindowActivated;
        // GAMECLUB_ENVIRONMENT remains a development-only runtime override;
        // portable production builds use the baked deployment metadata.
        // EndpointPolicy.GetEnvironmentEndpoint remains available for legacy diagnostics.
        var environment = DeploymentSettings.EnvironmentName;
        var authAddress = DeploymentSettings.AuthAddress;
        var grpcAddress = DeploymentSettings.GrpcAddress;
        _enrollmentTokenProvider = new DeviceEnrollmentTokenProvider(authAddress, environment);
        var accessCredentials = new EnvironmentAccessCredentialVerifier(environment);
        _powerController = new WindowsWorkstationPowerController();
        _viewModel = new MainViewModel(
            new ClientSessionCoordinator(
                new GrpcBackendClient(
                    grpcAddress,
                    _enrollmentTokenProvider)),
            accessCredentials,
            null,
            "0.1.0",
            new[] { "commands.v1", "display-lock.v1", "theme.v1", "sessions.v1", "widget.v1" },
            _powerController);
        ContentRoot.DataContext = _viewModel;
        _ = StartClientAsync();
    }

    private async Task StartClientAsync()
    {
        await _viewModel.RefreshConnectionAsync();
        _viewModel.TrackBackgroundTask(_viewModel.RunHeartbeatLoopAsync());
        _viewModel.TrackBackgroundTask(_viewModel.RunAccessLockLoopAsync());
        _viewModel.TrackBackgroundTask(ActivateEnrolledDeviceAsync());
    }

    private async Task ActivateEnrolledDeviceAsync()
    {
        while (string.IsNullOrWhiteSpace(_enrollmentTokenProvider.DeviceId)
            && !_viewModel.LifetimeToken.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(10), _viewModel.LifetimeToken);
            await _viewModel.RefreshConnectionAsync(_viewModel.LifetimeToken);
        }

        var enrolledDeviceId = _enrollmentTokenProvider.DeviceId;
        if (string.IsNullOrWhiteSpace(enrolledDeviceId))
        {
            return;
        }

        _viewModel.SetDeviceIdentity(enrolledDeviceId);
        var deviceId = _viewModel.DeviceId;
        if (string.IsNullOrWhiteSpace(deviceId))
        {
            return;
        }

        _viewModel.TrackBackgroundTask(
            _viewModel.RunWorkstationHeartbeatLoopAsync(
                ApplyThemeFromHeartbeat,
                ApplyManagerPasswordVerifierFromHeartbeat,
                ApplyLockdownPolicyFromHeartbeat));
        _viewModel.TrackBackgroundTask(
            _viewModel.RunCommandLoopAsync(
                new WindowsCommandExecutor(
                    deviceId,
                    _viewModel.BackendClient,
                    ApplyThemeFromCommand,
                    _powerController,
                    RegisterSessionStartedFromCommand,
                    RegisterSessionStoppedFromCommand,
                    LockClientFromCommand)));
    }

    private async void RefreshConnection(object sender, RoutedEventArgs args)
    {
        await _viewModel.RefreshConnectionAsync();
    }

    private async void StopCurrentSession(object sender, RoutedEventArgs args)
    {
        await _viewModel.StopActiveSessionAsync();
    }

    private async void MainWindowClosed(object sender, WindowEventArgs args)
    {
        await _viewModel.DisposeAsync();
    }

    private void MainWindowActivated(object sender, WindowActivatedEventArgs args)
    {
        if (args.WindowActivationState != WindowActivationState.Deactivated)
        {
            return;
        }

        ManagerPasswordBox.Password = string.Empty;
        _viewModel.LockClient();
    }

    private void PortalIdentifierChanged(object sender, TextChangedEventArgs args)
    {
        if (sender is TextBox textBox)
        {
            _viewModel.PortalIdentifier = textBox.Text;
        }
    }

    private void PortalPhoneChanged(object sender, TextChangedEventArgs args)
    {
        if (sender is TextBox textBox)
        {
            _viewModel.PortalPhone = textBox.Text;
        }
    }

    private void PortalNicknameChanged(object sender, TextChangedEventArgs args)
    {
        if (sender is TextBox textBox)
        {
            _viewModel.PortalNickname = textBox.Text;
        }
    }

    private void PortalPinChanged(object sender, RoutedEventArgs args)
    {
        if (sender is PasswordBox passwordBox)
        {
            _viewModel.PortalPin = passwordBox.Password;
        }
    }

    private void PortalRegistrationPinChanged(object sender, RoutedEventArgs args)
    {
        if (sender is PasswordBox passwordBox)
        {
            _viewModel.PortalRegistrationPin = passwordBox.Password;
        }
    }

    private void RecordKeyActivity(object sender, KeyRoutedEventArgs args) =>
        _viewModel.TouchAccessActivity();

    private void RecordPointerActivity(object sender, PointerRoutedEventArgs args) =>
        _viewModel.TouchAccessActivity();

    private void ManagerPasswordChanged(object sender, RoutedEventArgs args)
    {
        if (sender is PasswordBox passwordBox)
        {
            _viewModel.ManagerPassword = passwordBox.Password;
        }
    }

    private async void LoginPortal(object sender, RoutedEventArgs args)
    {
        await _viewModel.LoginPortalAsync();
        PortalPinBox.Password = string.Empty;
    }

    private async void RegisterPortal(object sender, RoutedEventArgs args)
    {
        await _viewModel.RegisterPortalAsync();
        PortalRegistrationPinBox.Password = string.Empty;
    }

    private void OpenPortalRegistration(object sender, RoutedEventArgs args) =>
        _viewModel.ShowPortalRegistration();

    private void CancelPortalRegistration(object sender, RoutedEventArgs args)
    {
        PortalRegistrationPinBox.Password = string.Empty;
        _viewModel.CancelPortalRegistration();
    }

    private void OpenManagerLogin(object sender, RoutedEventArgs args) =>
        _viewModel.ShowManagerLogin();

    private void OpenManagerLoginHotkey(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        _viewModel.ShowManagerLogin();
        args.Handled = true;
    }

    private void CancelManagerLogin(object sender, RoutedEventArgs args)
    {
        ManagerPasswordBox.Password = string.Empty;
        _viewModel.CancelManagerLogin();
    }

    private void EnterMaintenance(object sender, RoutedEventArgs args)
    {
        var entered = _viewModel.TryEnterMaintenance();
        ManagerPasswordBox.Password = string.Empty;
        if (!entered)
        {
            ManagerPasswordBox.Focus(FocusState.Programmatic);
        }
    }

    private void LockClient(object sender, RoutedEventArgs args)
    {
        ManagerPasswordBox.Password = string.Empty;
        _viewModel.LockClient();
    }

    private void ApplyThemeFromCommand(string theme)
    {
        DispatcherQueue.TryEnqueue(() => ApplyTheme(theme));
    }

    private void ApplyThemeFromHeartbeat(string theme)
    {
        DispatcherQueue.TryEnqueue(() => ApplyTheme(theme));
    }

    private void ApplyManagerPasswordVerifierFromHeartbeat(string verifier)
    {
        _viewModel.ApplyManagerPasswordVerifier(verifier);
    }

    private void ApplyLockdownPolicyFromHeartbeat(WorkstationLockdownPolicySnapshot policy)
    {
        DispatcherQueue.TryEnqueue(() => _viewModel.ApplyLockdownPolicy(policy));
    }

    private void RegisterSessionStartedFromCommand(SessionSnapshot session)
    {
        DispatcherQueue.TryEnqueue(() => _viewModel.RegisterSessionStarted(session));
    }

    private void RegisterSessionStoppedFromCommand(SessionSnapshot session)
    {
        DispatcherQueue.TryEnqueue(() => _viewModel.RegisterSessionStopped(session));
    }

    private void LockClientFromCommand()
    {
        DispatcherQueue.TryEnqueue(() => _viewModel.LockClient());
    }

    private void ApplyTheme(string theme)
    {
        _viewModel.ApplyTheme(theme);
        ((App)XamlApplication.Current).ApplyWorkstationTheme(theme);
    }

    private void ApplyLegacyWindowModeMarker(bool isCompact)
    {
        // The client is fullscreen in production; this remains only for older
        // diagnostic automation that inspects the previous mode contract.
        _viewModel.IsExpanded = isCompact;
    }

}
