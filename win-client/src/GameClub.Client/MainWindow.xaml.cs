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

    public MainWindow()
    {
        InitializeComponent();
        var windowHandle = WindowNative.GetWindowHandle(this);
        var windowId = Win32Interop.GetWindowIdFromWindow(windowHandle);
        _appWindow = AppWindow.GetFromWindowId(windowId);
        _appWindow.Resize(new SizeInt32(430, 670));
        Closed += MainWindowClosed;
        Activated += MainWindowActivated;
        var environment = Environment.GetEnvironmentVariable("GAMECLUB_ENVIRONMENT")?.Trim() ?? "dev";
        var authAddress = EndpointPolicy.GetEnvironmentEndpoint(
            "GAMECLUB_AUTH_ADDRESS",
            "http://127.0.0.1:8100",
            environment);
        var grpcAddress = EndpointPolicy.GetEnvironmentEndpoint(
            "GAMECLUB_GRPC_ADDRESS",
            "http://127.0.0.1:51051",
            environment);
        var tokenProvider = CreateTokenProvider(authAddress, environment);
        var accessCredentials = new EnvironmentAccessCredentialVerifier(environment);
        var powerController = new WindowsWorkstationPowerController();
        var deviceId = Environment.GetEnvironmentVariable("GAMECLUB_DEVICE_ID")?.Trim();
        _viewModel = new MainViewModel(
            new ClientSessionCoordinator(
                new GrpcBackendClient(
                    grpcAddress,
                    tokenProvider)),
            accessCredentials,
            deviceId,
            "0.1.0",
            new[] { "commands.v1", "display-lock.v1", "theme.v1", "sessions.v1", "widget.v1" },
            powerController);
        ContentRoot.DataContext = _viewModel;
        _ = StartClientAsync();
    }

    private async Task StartClientAsync()
    {
        await _viewModel.RefreshConnectionAsync();
        _viewModel.TrackBackgroundTask(_viewModel.RunHeartbeatLoopAsync());
        _viewModel.TrackBackgroundTask(_viewModel.RunAccessLockLoopAsync());
        if (_tokenProviderConfigured && !string.IsNullOrWhiteSpace(_viewModel.DeviceId))
        {
            _viewModel.TrackBackgroundTask(
                _viewModel.RunWorkstationHeartbeatLoopAsync(
                    ApplyThemeFromHeartbeat,
                    ApplyManagerPasswordVerifierFromHeartbeat,
                    ApplyLockdownPolicyFromHeartbeat));
            _viewModel.TrackBackgroundTask(
                _viewModel.RunCommandLoopAsync(
                    new WindowsCommandExecutor(
                        _viewModel.DeviceId,
                        _viewModel.BackendClient,
                        ApplyThemeFromCommand,
                        powerController,
                        RegisterSessionStartedFromCommand,
                        RegisterSessionStoppedFromCommand,
                        LockClientFromCommand)));
        }
    }

    private async void RefreshConnection(object sender, RoutedEventArgs args)
    {
        await _viewModel.RefreshConnectionAsync();
    }

    private async void StopCurrentSession(object sender, RoutedEventArgs args)
    {
        await _viewModel.StopActiveSessionAsync();
    }

    private void ToggleWindowMode(object sender, RoutedEventArgs args)
    {
        var isCompact = _appWindow.Size.Width < 700;
        _viewModel.IsExpanded = isCompact;
        _appWindow.Resize(isCompact ? new SizeInt32(1100, 760) : new SizeInt32(430, 670));
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

        UserAccessCodeBox.Password = string.Empty;
        ManagerPasswordBox.Password = string.Empty;
        _viewModel.LockClient();
    }

    private void UserAccessCodeChanged(object sender, RoutedEventArgs args)
    {
        if (sender is PasswordBox passwordBox)
        {
            _viewModel.UserAccessCode = passwordBox.Password;
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

    private void UnlockUser(object sender, RoutedEventArgs args)
    {
        var unlocked = _viewModel.TryUnlockUser();
        UserAccessCodeBox.Password = string.Empty;
        if (!unlocked)
        {
            UserAccessCodeBox.Focus(FocusState.Programmatic);
        }
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
        UserAccessCodeBox.Password = string.Empty;
        ManagerPasswordBox.Password = string.Empty;
        _viewModel.LockClient();
    }

    private static ITokenProvider? CreateTokenProvider(Uri authAddress, string environment)
    {
        var deviceId = Environment.GetEnvironmentVariable("GAMECLUB_DEVICE_ID");
        var bootstrapToken = Environment.GetEnvironmentVariable("GAMECLUB_DEVICE_BOOTSTRAP_TOKEN");
        if (string.IsNullOrWhiteSpace(deviceId) || string.IsNullOrWhiteSpace(bootstrapToken))
        {
            return null;
        }

        return new DeviceBootstrapTokenProvider(
            authAddress,
            deviceId,
            bootstrapToken,
            environment: environment);
    }

    private bool _tokenProviderConfigured =>
        !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(
            "GAMECLUB_DEVICE_BOOTSTRAP_TOKEN"));

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
        DispatcherQueue.TryEnqueue(_viewModel.LockClient);
    }

    private void ApplyTheme(string theme)
    {
        _viewModel.ApplyTheme(theme);
        ((App)XamlApplication.Current).ApplyWorkstationTheme(theme);
    }

}
