using System.ComponentModel;
using System.Runtime.CompilerServices;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Microsoft.UI.Xaml;

namespace GameClub.Client.Presentation;

public sealed class MainViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private readonly ClientSessionCoordinator _session;
    private readonly AccessGateCoordinator _accessGate;
    private readonly IAccessCredentialVerifier _accessCredentials;
    private readonly IWorkstationPowerController? _powerController;
    private readonly List<Task> _backgroundTasks = [];
    private CancellationTokenSource _lifetime = new();
    private ClientConnectionSnapshot _connection = new(
        ClientConnectionState.Connecting,
        "Подключаемся...",
        null,
        "—");
    private bool _isExpanded;
    private bool _isManagerLoginRequested;
    private string _userAccessCode = string.Empty;
    private string _managerPassword = string.Empty;
    private string _themeName = "Обычный зал";
    private WorkstationLockdownPolicySnapshot _lockdownPolicy =
        WorkstationLockdownPolicySnapshot.SafeDefault;
    private SessionSnapshot? _activeSession;

    public MainViewModel(
        ClientSessionCoordinator session,
        IAccessCredentialVerifier accessCredentials,
        string? deviceId = null,
        string clientVersion = "0.1.0",
        IReadOnlyCollection<string>? capabilities = null,
        IWorkstationPowerController? powerController = null)
    {
        _session = session;
        _accessCredentials = accessCredentials;
        _accessGate = new AccessGateCoordinator(_accessCredentials);
        _powerController = powerController;
        DeviceId = deviceId;
        ClientVersion = clientVersion;
        Capabilities = capabilities ?? Array.Empty<string>();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public string ConnectionMessage => _connection.Message;
    public string BackendVersion => _connection.BackendVersion;
    public bool IsOnline => _connection.State == ClientConnectionState.Online;
    public string ConnectionColor => IsOnline ? "#A8ED62" : "#E3A14E";
    public string DeviceId { get; }
    public string ClientVersion { get; }
    public IReadOnlyCollection<string> Capabilities { get; }
    public AccessMode AccessMode => _accessGate.Snapshot.Mode;
    public bool IsAccessLocked => _accessGate.IsLocked;
    public bool IsSessionLocked => _accessGate.IsSessionLocked;
    public bool IsMaintenanceMode => _accessGate.IsMaintenance;
    public Visibility AccessGateVisibility => IsAccessLocked || IsMaintenanceMode
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility SecuredContentVisibility => IsAccessLocked || IsMaintenanceMode
        ? Visibility.Collapsed
        : Visibility.Visible;
    public Visibility UserLoginVisibility => IsAccessLocked
        && _lockdownPolicy.UserSelfLoginEnabled
        && !_isManagerLoginRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility ManagerLoginVisibility => IsAccessLocked && _isManagerLoginRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility MaintenanceVisibility => IsMaintenanceMode
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility ManagerEntryVisibility => IsAccessLocked && !_isManagerLoginRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public string AccessMessage => _accessGate.Snapshot.Message;
    public string AccessTitle => IsMaintenanceMode
        ? "Режим обслуживания"
        : IsSessionLocked
            ? "Сессия завершена"
            : _lockdownPolicy.UserSelfLoginEnabled ? "Вход на игровое место" : "Клиент заблокирован";
    public string AccessSubtitle => IsMaintenanceMode
        ? "Системные действия доступны только менеджеру"
        : IsSessionLocked
            ? "Баланс или время сессии закончились. Введите код для нового входа."
            : _lockdownPolicy.UserSelfLoginEnabled
                ? "Введите персональный код, чтобы начать игру"
                : "Вход пользователя отключён политикой зоны. Для обслуживания используйте Ctrl+Alt+P.";
    public bool CanUnlockUser => _userAccessCode.Trim().Length >= 4;
    public bool CanEnterMaintenance => _managerPassword.Length >= 8;
    public bool IsUserAccessConfigured => _accessCredentials.IsUserAccessConfigured;
    public bool IsManagerAccessConfigured => _accessCredentials.IsManagerAccessConfigured;
    public WorkstationLockdownPolicySnapshot LockdownPolicy => _lockdownPolicy;
    public string UserAccessCode
    {
        get => _userAccessCode;
        set
        {
            if (_userAccessCode == value)
            {
                return;
            }
            _userAccessCode = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanUnlockUser));
        }
    }
    public string ManagerPassword
    {
        get => _managerPassword;
        set
        {
            if (_managerPassword == value)
            {
                return;
            }
            _managerPassword = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanEnterMaintenance));
        }
    }
    public string DeviceStatus => string.IsNullOrWhiteSpace(DeviceId)
        ? "Device identity не настроена"
        : $"Device: {DeviceId}";
    public Visibility ActiveSessionVisibility => _activeSession is null
        ? Visibility.Collapsed
        : Visibility.Visible;
    public bool CanStopActiveSession => _activeSession is not null && !IsAccessLocked && !IsMaintenanceMode;
    public string ActiveSessionDescription => _activeSession is null
        ? string.Empty
        : $"{_activeSession.GuestName ?? _activeSession.ClientId ?? "Гость"} · с {_activeSession.StartedAt}";
    public IWorkstationSessionGateway BackendClient => _session.BackendClient;
    public string ThemeName
    {
        get => _themeName;
        set
        {
            if (_themeName == value)
            {
                return;
            }
            _themeName = value;
            OnPropertyChanged();
        }
    }

    public void ApplyTheme(string themeKey)
    {
        ThemeName = themeKey switch
        {
            "vip" => "VIP-зона",
            "standard" => "Обычный зал",
            "neon" => "Неон",
            "minimal" => "Минимал",
            "VIP-зона" => "VIP-зона",
            "Обычный зал" => "Обычный зал",
            "Неон" => "Неон",
            "Минимал" => "Минимал",
            _ => "Обычный зал",
        };
    }

    public void ApplyManagerPasswordVerifier(string verifier) =>
        _accessCredentials.UpdateManagerPasswordVerifier(verifier);

    public void ApplyLockdownPolicy(WorkstationLockdownPolicySnapshot policy)
    {
        _lockdownPolicy = policy;
        if (!policy.ShellEnabled || !policy.UserSelfLoginEnabled)
        {
            LockClient("Доступ к клиенту отключён политикой зоны");
        }
        OnPropertyChanged(nameof(LockdownPolicy));
        OnPropertyChanged(nameof(UserLoginVisibility));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    public string NextBooking { get; } = "Сегодня, 18:00 · VIP-01";

    public bool IsExpanded
    {
        get => _isExpanded;
        set
        {
            if (_isExpanded == value)
            {
                return;
            }
            _isExpanded = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(WindowModeActionLabel));
        }
    }

    public string WindowModeActionLabel => IsExpanded
        ? "Компактный виджет"
        : "Во всё окно";

    public async Task RefreshConnectionAsync(CancellationToken cancellationToken = default)
    {
        _connection = await _session.CheckConnectionAsync(cancellationToken);
        if (_connection.State == ClientConnectionState.AuthenticationRequired)
        {
            _accessGate.Lock("Требуется повторная авторизация устройства");
            _isManagerLoginRequested = false;
            UserAccessCode = string.Empty;
            ManagerPassword = string.Empty;
            PublishAccessState();
        }
        OnPropertyChanged(nameof(ConnectionMessage));
        OnPropertyChanged(nameof(BackendVersion));
        OnPropertyChanged(nameof(IsOnline));
        OnPropertyChanged(nameof(ConnectionColor));
    }

    public async Task RunHeartbeatLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(15));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            await RefreshConnectionAsync(_lifetime.Token);
        }
    }

    public async Task RunAccessLockLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(30));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            if (_accessGate.LockIfIdle())
            {
                PublishAccessState();
            }
        }
    }

    public void ShowManagerLogin()
    {
        _accessGate.Lock("Введите пароль менеджера");
        _isManagerLoginRequested = true;
        ManagerPassword = string.Empty;
        PublishAccessState();
    }

    public void CancelManagerLogin()
    {
        _isManagerLoginRequested = false;
        ManagerPassword = string.Empty;
        PublishAccessState();
    }

    public bool TryUnlockUser()
    {
        var unlocked = _accessGate.TryUnlockUser(UserAccessCode);
        if (unlocked)
        {
            UserAccessCode = string.Empty;
        }
        PublishAccessState();
        return unlocked;
    }

    public bool TryEnterMaintenance()
    {
        var entered = _accessGate.TryEnterMaintenance(ManagerPassword);
        if (entered)
        {
            ManagerPassword = string.Empty;
            _isManagerLoginRequested = false;
        }
        PublishAccessState();
        return entered;
    }

    public void LockClient(string message = "Экран заблокирован")
    {
        _accessGate.Lock(message);
        _isManagerLoginRequested = false;
        UserAccessCode = string.Empty;
        ManagerPassword = string.Empty;
        PublishAccessState();
    }

    public void TouchAccessActivity() => _accessGate.Touch();

    public void RegisterSessionStarted(SessionSnapshot session)
    {
        _activeSession = session;
        PublishSessionState();
    }

    public void RegisterSessionStopped(SessionSnapshot session)
    {
        if (_activeSession?.Id == session.Id)
        {
            _activeSession = null;
            PublishSessionState();
            ApplySessionStopPolicy();
        }
    }

    public async Task<bool> StopActiveSessionAsync(CancellationToken cancellationToken = default)
    {
        var activeSession = _activeSession;
        if (activeSession is null || string.IsNullOrWhiteSpace(DeviceId) || !CanStopActiveSession)
        {
            return false;
        }

        await _session.BackendClient.StopSessionAsync(
            activeSession.Id,
            DeviceId,
            cancellationToken);
        _activeSession = null;
        PublishSessionState();
        ApplySessionStopPolicy();
        return true;
    }

    public Task RunWorkstationHeartbeatLoopAsync(
        Action<string>? onThemeReceived = null,
        Action<string>? onManagerPasswordVerifierReceived = null,
        Action<WorkstationLockdownPolicySnapshot>? onLockdownPolicyReceived = null) =>
        string.IsNullOrWhiteSpace(DeviceId)
            ? Task.CompletedTask
            : _session.RunWorkstationHeartbeatLoopAsync(
                DeviceId,
                ClientVersion,
                Capabilities,
                onThemeReceived,
                onManagerPasswordVerifierReceived,
                onLockdownPolicyReceived,
                _lifetime.Token);

    public Task RunCommandLoopAsync(IWorkstationCommandExecutor executor) =>
        string.IsNullOrWhiteSpace(DeviceId)
            ? Task.CompletedTask
            : _session.RunCommandLoopAsync(DeviceId, executor, _lifetime.Token);

    public void TrackBackgroundTask(Task task) => _backgroundTasks.Add(task);

    public async ValueTask DisposeAsync()
    {
        await _lifetime.CancelAsync();
        try
        {
            await Task.WhenAll(_backgroundTasks);
        }
        catch (OperationCanceledException)
        {
            // Отмена фоновых циклов является штатным завершением окна.
        }
        _lifetime.Dispose();
        await _session.DisposeAsync();
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    private void PublishAccessState()
    {
        OnPropertyChanged(nameof(AccessMode));
        OnPropertyChanged(nameof(IsAccessLocked));
        OnPropertyChanged(nameof(IsSessionLocked));
        OnPropertyChanged(nameof(IsMaintenanceMode));
        OnPropertyChanged(nameof(AccessGateVisibility));
        OnPropertyChanged(nameof(SecuredContentVisibility));
        OnPropertyChanged(nameof(UserLoginVisibility));
        OnPropertyChanged(nameof(ManagerLoginVisibility));
        OnPropertyChanged(nameof(MaintenanceVisibility));
        OnPropertyChanged(nameof(ManagerEntryVisibility));
        OnPropertyChanged(nameof(AccessMessage));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    private void PublishSessionState()
    {
        OnPropertyChanged(nameof(ActiveSessionVisibility));
        OnPropertyChanged(nameof(CanStopActiveSession));
        OnPropertyChanged(nameof(ActiveSessionDescription));
    }

    private void ApplySessionStopPolicy()
    {
        if (_lockdownPolicy.LockAfterSession)
        {
            _accessGate.LockSession("Сессия завершена. Введите код для нового входа");
            PublishAccessState();
        }

        if (_lockdownPolicy.RestartAfterSession)
        {
            _powerController?.ScheduleRestart();
        }
    }
}
