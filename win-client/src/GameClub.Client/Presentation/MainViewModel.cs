using System.ComponentModel;
using System.Globalization;
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
    private readonly IClientPortalGateway _clientPortal;
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
    private ClientPortalSnapshot? _portalSnapshot;
    private bool _isPortalRegistrationRequested;
    private string _portalIdentifier = string.Empty;
    private string _portalPhone = string.Empty;
    private string _portalNickname = string.Empty;
    private string _portalPin = string.Empty;
    private string _portalRegistrationPin = string.Empty;
    private string _portalMessage = string.Empty;

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
        _clientPortal = session.ClientPortal;
        _powerController = powerController;
        DeviceId = deviceId;
        ClientVersion = clientVersion;
        Capabilities = capabilities ?? Array.Empty<string>();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public CancellationToken LifetimeToken => _lifetime.Token;

    public string ConnectionMessage => _connection.Message;
    public string BackendVersion => _connection.BackendVersion;
    public bool IsOnline => _connection.State == ClientConnectionState.Online;
    public bool IsWaitingForAssignment =>
        _connection.State == ClientConnectionState.WaitingForAssignment;
    public string ConnectionColor => IsOnline ? "#A8ED62" : "#E3A14E";
    public string? DeviceId { get; private set; }
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
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && !_isPortalRegistrationRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility PortalRegistrationVisibility => IsAccessLocked
        && _lockdownPolicy.UserSelfLoginEnabled
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && _isPortalRegistrationRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility ManagerLoginVisibility => IsAccessLocked && _isManagerLoginRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility MaintenanceVisibility => IsMaintenanceMode
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility ManagerEntryVisibility => IsAccessLocked
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && !_isPortalRegistrationRequested
        ? Visibility.Visible
        : Visibility.Collapsed;
    public Visibility PortalContentVisibility => _portalSnapshot is null || IsAccessLocked || IsMaintenanceMode
        ? Visibility.Collapsed
        : Visibility.Visible;
    public string AccessMessage => string.IsNullOrWhiteSpace(_portalMessage)
        ? _accessGate.Snapshot.Message
        : _portalMessage;
    public string AccessTitle => IsMaintenanceMode
        ? "Режим обслуживания"
        : IsWaitingForAssignment
            ? "Ожидание привязки ПК"
        : IsSessionLocked
            ? "Сессия завершена"
            : _lockdownPolicy.UserSelfLoginEnabled ? "Вход на игровое место" : "Клиент заблокирован";
    public string AccessSubtitle => IsMaintenanceMode
        ? "Системные действия доступны только менеджеру"
        : IsWaitingForAssignment
            ? "Администратор должен указать MAC-адрес этого ПК в админке"
        : IsSessionLocked
            ? "Баланс или время сессии закончились. Войдите снова для продолжения."
            : _lockdownPolicy.UserSelfLoginEnabled
                ? _isPortalRegistrationRequested
                    ? "Создайте аккаунт клуба — он будет привязан к этому месту"
                    : "Войдите по нику или телефону, чтобы открыть аккаунт клуба"
                : "Вход пользователя отключён политикой зоны. Для обслуживания используйте Ctrl+Alt+P.";
    public bool CanUnlockUser => _userAccessCode.Trim().Length >= 4;
    public bool CanEnterMaintenance => _managerPassword.Length >= 8;
    public bool CanLoginPortal => _portalIdentifier.Trim().Length >= 3 && _portalPin.Length >= 4;
    public bool CanRegisterPortal => _portalNickname.Trim().Length >= 3
        && _portalPhone.Trim().Length >= 4
        && _portalRegistrationPin.Length >= 4;
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
    public string PortalIdentifier
    {
        get => _portalIdentifier;
        set
        {
            if (_portalIdentifier == value)
            {
                return;
            }
            _portalIdentifier = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanLoginPortal));
        }
    }
    public string PortalPhone
    {
        get => _portalPhone;
        set
        {
            if (_portalPhone == value)
            {
                return;
            }
            _portalPhone = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanRegisterPortal));
        }
    }
    public string PortalNickname
    {
        get => _portalNickname;
        set
        {
            if (_portalNickname == value)
            {
                return;
            }
            _portalNickname = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanRegisterPortal));
        }
    }
    public string PortalPin
    {
        get => _portalPin;
        set
        {
            if (_portalPin == value)
            {
                return;
            }
            _portalPin = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanLoginPortal));
        }
    }
    public string PortalRegistrationPin
    {
        get => _portalRegistrationPin;
        set
        {
            if (_portalRegistrationPin == value)
            {
                return;
            }
            _portalRegistrationPin = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanRegisterPortal));
        }
    }
    public bool IsPortalRegistrationRequested => _isPortalRegistrationRequested;
    public string PortalAccountSummary => _portalSnapshot is null
        ? string.Empty
        : $"{_portalSnapshot.Nickname} · {_portalSnapshot.Phone}";
    public string PortalBalanceSummary => _portalSnapshot is null
        ? string.Empty
        : $"Баланс: {FormatMoney(_portalSnapshot.BalanceCents)} · Бонусы: {_portalSnapshot.BalanceBonus}";
    public string PortalAvailableTimeSummary => _portalSnapshot is null
        ? string.Empty
        : $"Доступное время: {FormatDuration(_portalSnapshot.AvailableTimeMinutes)}";
    public IReadOnlyList<string> PortalBalanceHistory => _portalSnapshot?.BalanceOperations
        .Select(operation =>
            $"{operation.CreatedAt} · {operation.OperationType} · {FormatMoney(operation.AmountCents)} · {operation.Reason}")
        .ToArray() ?? Array.Empty<string>();
    public IReadOnlyList<string> PortalPurchaseHistory => _portalSnapshot?.Purchases
        .Select(purchase =>
            $"{purchase.CreatedAt} · {purchase.ProductName} × {purchase.Quantity} · {FormatMoney(purchase.TotalPriceCents)}")
        .ToArray() ?? Array.Empty<string>();
    public IReadOnlyList<string> PortalChargeHistory => _portalSnapshot?.Charges
        .Select(charge =>
            $"{charge.CreatedAt} · {charge.TariffName ?? "тариф"} · списание времени · {FormatMoney(charge.AmountCents)} · {charge.DurationMinutes} мин")
        .ToArray() ?? Array.Empty<string>();
    public IReadOnlyList<string> PortalSessionHistory => _portalSnapshot?.Sessions
        .Select(session =>
            $"{session.StartedAt} · место {session.WorkstationId} · тариф {session.TariffName ?? session.TariffId ?? "—"} × {session.TariffQuantity} · {session.Status}")
        .ToArray() ?? Array.Empty<string>();
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
        OnPropertyChanged(nameof(IsWaitingForAssignment));
        OnPropertyChanged(nameof(UserLoginVisibility));
        OnPropertyChanged(nameof(PortalRegistrationVisibility));
        OnPropertyChanged(nameof(ManagerEntryVisibility));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    public void SetDeviceIdentity(string deviceId)
    {
        var normalized = deviceId.Trim();
        if (!string.IsNullOrWhiteSpace(DeviceId) || string.IsNullOrWhiteSpace(normalized))
        {
            return;
        }

        DeviceId = normalized;
        OnPropertyChanged(nameof(DeviceId));
        OnPropertyChanged(nameof(DeviceStatus));
    }

    public async Task RunHeartbeatLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(15));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            await RefreshConnectionAsync(_lifetime.Token);
            await RefreshPortalAsync();
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
        _isPortalRegistrationRequested = false;
        _portalMessage = string.Empty;
        ManagerPassword = string.Empty;
        PublishAccessState();
    }

    public void ShowPortalRegistration()
    {
        _isPortalRegistrationRequested = true;
        _portalMessage = string.Empty;
        PublishAccessState();
    }

    public void CancelPortalRegistration()
    {
        _isPortalRegistrationRequested = false;
        _portalMessage = string.Empty;
        PublishAccessState();
    }

    public async Task<bool> LoginPortalAsync()
    {
        if (string.IsNullOrWhiteSpace(DeviceId))
        {
            _portalMessage = "ПК ещё не привязан администратором";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }

        try
        {
            var authentication = await _clientPortal.LoginAsync(
                PortalIdentifier,
                PortalPin,
                DeviceId,
                _lifetime.Token);
            SetPortalSnapshot(authentication.Snapshot);
            _accessGate.OpenUserSession();
            _portalMessage = string.Empty;
            PortalPin = string.Empty;
            PublishAccessState();
            return true;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception)
        {
            _portalMessage = "Не удалось войти. Проверьте ник/телефон и PIN";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    public async Task<bool> RegisterPortalAsync()
    {
        if (string.IsNullOrWhiteSpace(DeviceId))
        {
            _portalMessage = "ПК ещё не привязан администратором";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }

        try
        {
            var authentication = await _clientPortal.RegisterAsync(
                PortalNickname,
                PortalPhone,
                PortalRegistrationPin,
                DeviceId,
                _lifetime.Token);
            SetPortalSnapshot(authentication.Snapshot);
            _accessGate.OpenUserSession();
            _isPortalRegistrationRequested = false;
            _portalMessage = string.Empty;
            PortalRegistrationPin = string.Empty;
            PublishAccessState();
            return true;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception)
        {
            _portalMessage = "Не удалось зарегистрироваться. Проверьте данные";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    public async Task RefreshPortalAsync()
    {
        if (_portalSnapshot is null || string.IsNullOrWhiteSpace(DeviceId) || IsAccessLocked)
        {
            return;
        }

        try
        {
            SetPortalSnapshot(await _clientPortal.RefreshAsync(DeviceId, cancellationToken: _lifetime.Token));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception)
        {
            _portalMessage = "История временно недоступна";
            OnPropertyChanged(nameof(AccessMessage));
        }
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
        _clientPortal.Logout();
        _portalSnapshot = null;
        _accessGate.Lock(message);
        _isManagerLoginRequested = false;
        UserAccessCode = string.Empty;
        ManagerPassword = string.Empty;
        PublishAccessState();
        PublishPortalState();
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
        OnPropertyChanged(nameof(PortalRegistrationVisibility));
        OnPropertyChanged(nameof(PortalContentVisibility));
        OnPropertyChanged(nameof(ManagerLoginVisibility));
        OnPropertyChanged(nameof(MaintenanceVisibility));
        OnPropertyChanged(nameof(ManagerEntryVisibility));
        OnPropertyChanged(nameof(AccessMessage));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    private void SetPortalSnapshot(ClientPortalSnapshot snapshot)
    {
        _portalSnapshot = snapshot;
        PublishPortalState();
    }

    private void PublishPortalState()
    {
        OnPropertyChanged(nameof(PortalContentVisibility));
        OnPropertyChanged(nameof(PortalAccountSummary));
        OnPropertyChanged(nameof(PortalBalanceSummary));
        OnPropertyChanged(nameof(PortalAvailableTimeSummary));
        OnPropertyChanged(nameof(PortalBalanceHistory));
        OnPropertyChanged(nameof(PortalPurchaseHistory));
        OnPropertyChanged(nameof(PortalChargeHistory));
        OnPropertyChanged(nameof(PortalSessionHistory));
    }

    private static string FormatMoney(long cents) =>
        (cents / 100m).ToString("N2", CultureInfo.GetCultureInfo("ru-RU")) + " ₽";

    private static string FormatDuration(long minutes)
    {
        var hours = minutes / 60;
        var remainder = minutes % 60;
        return hours > 0 ? $"{hours} ч {remainder} мин" : $"{remainder} мин";
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
