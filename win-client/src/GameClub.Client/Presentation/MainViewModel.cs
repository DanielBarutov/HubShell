using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;
using Grpc.Core;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Presentation;

public sealed class MainViewModel : INotifyPropertyChanged, IAsyncDisposable
{
    private readonly ClientSessionCoordinator _session;
    private readonly AccessGateCoordinator _accessGate;
    private readonly IAccessCredentialVerifier _accessCredentials;
    private readonly IWorkstationPowerController? _powerController;
    private readonly IClientPortalGateway _clientPortal;
    private readonly SessionTimeProjection _sessionTimeProjection = new();
    private readonly Func<DateTimeOffset> _clock;
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
    private int _portalResumeInFlight;
    private ClientPortalSnapshot? _portalSnapshot;
    private bool _isPortalRegistrationRequested;
    private string _portalIdentifier = string.Empty;
    private string _portalPhone = string.Empty;
    private string _portalNickname = string.Empty;
    private string _portalPassword = string.Empty;
    private string _portalRegistrationPassword = string.Empty;
    private string _portalPasswordSetup = string.Empty;
    private string _portalPasswordSetupConfirmation = string.Empty;
    private bool _portalPasswordResetRequired;
    private string _portalMessage = string.Empty;
    private string _workstationName = string.Empty;
    private string _transferTargetWorkstationId = string.Empty;
    private string _incomingTransferOfferId = string.Empty;
    private string _incomingTransferToken = string.Empty;
    private string _transferOfferId = string.Empty;
    private string _transferOfferToken = string.Empty;
    private string _sessionNotification = string.Empty;
    private bool _isTransferExpanded;
    private bool _isTransferWaiting;
    private string? _portalSessionIdempotencyKey;
    private CancellationTokenSource? _sessionNotificationLifetime;

    public MainViewModel(
        ClientSessionCoordinator session,
        IAccessCredentialVerifier accessCredentials,
        string? deviceId = null,
        string clientVersion = "0.1.0",
        IReadOnlyCollection<string>? capabilities = null,
        IWorkstationPowerController? powerController = null,
        Func<DateTimeOffset>? clock = null)
    {
        _session = session;
        _accessCredentials = accessCredentials;
        _accessGate = new AccessGateCoordinator(_accessCredentials);
        _clientPortal = session.ClientPortal;
        _powerController = powerController;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
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
    public string? WorkstationId { get; private set; }
    public string WorkstationName => _workstationName;
    public string ClientVersion { get; }
    public IReadOnlyCollection<string> Capabilities { get; }
    public AccessMode AccessMode => _accessGate.Snapshot.Mode;
    public bool IsAccessLocked => _accessGate.IsLocked;
    public bool IsSessionLocked => _accessGate.IsSessionLocked;
    public bool IsMaintenanceMode => _accessGate.IsMaintenance;
    public bool IsAccessGateVisible => IsAccessLocked || IsMaintenanceMode;
    public bool IsSecuredContentVisible => !IsAccessLocked && !IsMaintenanceMode && _portalSnapshot is null;
    public bool IsUserLoginVisible => IsAccessLocked
        && _lockdownPolicy.UserSelfLoginEnabled
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && !_isPortalRegistrationRequested;
    public bool IsPortalRegistrationVisible => IsAccessLocked
        && _lockdownPolicy.UserSelfLoginEnabled
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && _isPortalRegistrationRequested;
    public bool IsManagerLoginVisible => IsAccessLocked && _isManagerLoginRequested;
    public bool IsMaintenanceVisible => IsMaintenanceMode;
    public bool IsManagerEntryVisible => IsAccessLocked
        && !IsWaitingForAssignment
        && !_isManagerLoginRequested
        && !_isPortalRegistrationRequested;
    public bool IsPortalContentVisible => _portalSnapshot is not null && !IsAccessLocked && !IsMaintenanceMode;
    public bool IsPortalPasswordSetupVisible => _portalPasswordResetRequired && _portalSnapshot is not null;
    public bool IsPortalReadyVisible => !_portalPasswordResetRequired;
    public string AccessMessage => string.IsNullOrWhiteSpace(_portalMessage)
        ? _accessGate.Snapshot.Message
        : _portalMessage;
    public bool IsAccessFeedbackVisible => !string.IsNullOrWhiteSpace(_portalMessage);
    public string AccessTitle => IsMaintenanceMode
        ? "Режим обслуживания"
        : IsWaitingForAssignment
            ? "Ожидание привязки ПК"
        : IsSessionLocked
            ? "Сессия завершена"
            : _lockdownPolicy.UserSelfLoginEnabled ? "Войдите и начните играть" : "Клиент заблокирован";
    public string AccessSubtitle => IsMaintenanceMode
        ? "Системные действия доступны только менеджеру"
        : IsWaitingForAssignment
            ? "Администратор должен указать MAC-адрес этого ПК в админке"
        : IsSessionLocked
            ? "Баланс или время сессии закончились. Войдите снова для продолжения."
            : _lockdownPolicy.UserSelfLoginEnabled
                ? _isPortalRegistrationRequested
                ? "Создайте аккаунт клуба — он будет привязан к этому месту"
                    : "Войдите по нику или телефону, чтобы начать сессию на этом ПК"
                : "Вход пользователя отключён политикой зоны. Обратитесь к администратору клуба.";
    public bool CanUnlockUser => _userAccessCode.Trim().Length >= 4;
    public bool CanEnterMaintenance => _managerPassword.Length >= 8;
    public bool CanLoginPortal => _portalIdentifier.Trim().Length >= 3
        && (_portalPassword.Length == 0 || _portalPassword.Length >= 4);
    public bool CanSetPortalPassword => _portalPasswordSetup.Length is >= 4 and <= 128
        && string.Equals(_portalPasswordSetup, _portalPasswordSetupConfirmation, StringComparison.Ordinal);
    public bool CanRegisterPortal => _portalNickname.Trim().Length >= 3
        && _portalPhone.Trim().Length >= 4
        && _portalRegistrationPassword.Length >= 4;
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
    public string PortalPassword
    {
        get => _portalPassword;
        set
        {
            if (_portalPassword == value)
            {
                return;
            }
            _portalPassword = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanLoginPortal));
        }
    }
    public string PortalRegistrationPassword
    {
        get => _portalRegistrationPassword;
        set
        {
            if (_portalRegistrationPassword == value)
            {
                return;
            }
            _portalRegistrationPassword = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanRegisterPortal));
        }
    }
    public string PortalPasswordSetup
    {
        get => _portalPasswordSetup;
        set
        {
            if (_portalPasswordSetup == value)
            {
                return;
            }
            _portalPasswordSetup = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanSetPortalPassword));
        }
    }
    public string PortalPasswordSetupConfirmation
    {
        get => _portalPasswordSetupConfirmation;
        set
        {
            if (_portalPasswordSetupConfirmation == value)
            {
                return;
            }
            _portalPasswordSetupConfirmation = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanSetPortalPassword));
        }
    }
    public bool IsPortalPasswordResetRequired => _portalPasswordResetRequired;
    public bool IsPortalRegistrationRequested => _isPortalRegistrationRequested;
    public string PortalAccountSummary => _portalSnapshot is null
        ? string.Empty
        : _portalSnapshot.Nickname;
    public string PortalContactSummary => _portalSnapshot is null
        ? string.Empty
        : _portalSnapshot.Phone;
    public string CurrentWorkstationLabel => string.IsNullOrWhiteSpace(WorkstationName)
        ? "Игровое место"
        : WorkstationName;
    public string PortalBalanceAmountSummary => _portalSnapshot is null
        ? string.Empty
        : FormatMoney(_portalSnapshot.BalanceCents);
    public string PortalBonusSummary => _portalSnapshot is null
        ? string.Empty
        : $"Бонусы: {_portalSnapshot.BalanceBonus}";
    public string PortalAvailableTimeValue => _portalSnapshot is null
        ? string.Empty
        : FormatDuration(_portalSnapshot.AvailableTimeMinutes);
    public string PortalBalanceSummary => _portalSnapshot is null
        ? string.Empty
        : $"Баланс: {FormatMoney(_portalSnapshot.BalanceCents)} · Бонусы: {_portalSnapshot.BalanceBonus}";
    public string PortalAvailableTimeSummary => _portalSnapshot is null
        ? string.Empty
        : $"Осталось примерно {FormatDuration(_portalSnapshot.AvailableTimeMinutes)}";
    public bool IsPortalBalanceTimeVisible => _portalSnapshot is not null
        && _activeSession?.ActivePackage is null
        && !_portalSnapshot.Entitlements.Any(item =>
            item.Status.Equals("active", StringComparison.OrdinalIgnoreCase));
    public IReadOnlyList<string> PortalBalanceHistory => _portalSnapshot is null
        ? Array.Empty<string>()
        : ClientPortalHistoryFormatter.FormatBalanceOperations(_portalSnapshot);
    public IReadOnlyList<string> PortalPurchaseHistory => _portalSnapshot is null
        ? Array.Empty<string>()
        : ClientPortalHistoryFormatter.FormatPurchases(_portalSnapshot);
    public IReadOnlyList<string> PortalChargeHistory => _portalSnapshot is null
        ? Array.Empty<string>()
        : ClientPortalHistoryFormatter.FormatCharges(_portalSnapshot);
    public IReadOnlyList<string> PortalSessionHistory => _portalSnapshot is null
        ? Array.Empty<string>()
        : ClientPortalHistoryFormatter.FormatSessions(_portalSnapshot);
    public IReadOnlyList<string> PortalEntitlementQueue => _portalSnapshot?.Entitlements
        .Where(item => item.Status.Equals("active", StringComparison.OrdinalIgnoreCase)
            || item.Status.Equals("queued", StringComparison.OrdinalIgnoreCase))
        .OrderBy(item => item.QueuePosition)
        .Select(item =>
            $"{item.TariffName ?? "Пакет"} · {FormatEntitlementStatus(item.Status)} · {item.RemainingMinutes} из {item.DurationMinutes} мин")
        .ToArray() ?? Array.Empty<string>();
    public IReadOnlyList<ClientPortalTariff> PortalTariffs => _portalSnapshot?.Tariffs
        ?? Array.Empty<ClientPortalTariff>();
    public bool HasPortalTariffs => PortalTariffs.Count > 0;
    public bool IsTariffsVisible => HasPortalTariffs && !_portalPasswordResetRequired;
    public bool HasPortalBalance => _portalSnapshot?.BalanceCents > 0;
    public ClientPortalTariff? FindPortalTariff(string tariffId) =>
        _portalSnapshot?.Tariffs.FirstOrDefault(item => item.Id == tariffId);
    public bool IsUpcomingBookingVisible => FindUpcomingBooking() is not null;
    public string UpcomingBookingTitle => FormatUpcomingBookingTitle(FindUpcomingBooking());
    public string UpcomingBookingDetails => FormatUpcomingBooking(
        FindUpcomingBooking(),
        CurrentWorkstationLabel);
    public bool IsTransferPanelVisible => _isTransferExpanded && !_portalPasswordResetRequired;
    public string TransferToggleLabel => _isTransferExpanded
        ? _isTransferWaiting ? "Ожидаем вход на новом ПК" : "Свернуть перенос"
        : "Перенести сессию на другой ПК";
    public bool IsTransferWaiting => _isTransferWaiting;
    public bool CanActivatePortalEntitlement => _portalSnapshot?.Entitlements
        .Any(item => item.Status.Equals("queued", StringComparison.OrdinalIgnoreCase)) == true
        && _portalSnapshot?.Entitlements.Any(item => item.Status.Equals("active", StringComparison.OrdinalIgnoreCase)) != true
        && !string.IsNullOrWhiteSpace(DeviceId)
        && !_portalPasswordResetRequired;
    public string DeviceStatus => string.IsNullOrWhiteSpace(DeviceId)
        ? "Device identity не настроена"
        : $"Device: {DeviceId} · Workstation: {WorkstationId ?? "—"}";
    public bool IsActiveSessionVisible => _activeSession is not null && !_portalPasswordResetRequired;
    public bool CanStopActiveSession => _activeSession is not null
        && !_portalPasswordResetRequired
        && !IsAccessLocked
        && !IsMaintenanceMode;
    public string ActiveSessionDescription => _activeSession is null
        ? string.Empty
        : $"{_activeSession.GuestName ?? _activeSession.ClientId ?? "Гость"} · с {_activeSession.StartedAt}";
    public string ActiveTimeSummary => _activeSession is null
        ? "Сессия не запущена"
        : _sessionTimeProjection.GetRemainingMinutes(_clock()) is int projectedMinutes
            ? $"Осталось {FormatDuration(projectedMinutes)}"
        : _activeSession.LoginGrantRemainingMinutes > 0
            ? $"Осталось {FormatDuration(_activeSession.LoginGrantRemainingMinutes)}"
        : _activeSession.ActivePackage is not null
            ? $"Осталось {FormatDuration(_activeSession.ActivePackage.RemainingMinutes)}"
        : _activeSession.ActiveTariff is not null
            && _activeSession.ActiveTariff.BillingMode == "block"
            ? $"Осталось {FormatDuration(_activeSession.ActiveTariff.RemainingMinutes)}"
        : _activeSession.ActiveTariff is not null
            && _activeSession.ActiveTariff.BillingMode == "per_minute"
            && _activeSession.BalanceRemainingMinutes is not null
            ? $"Осталось {FormatDuration(_activeSession.BalanceRemainingMinutes.Value)}"
        : _activeSession.ActiveTariff is not null
            ? $"Использовано {_activeSession.ActiveTariff.ElapsedMinutes} мин"
        : _activeSession.Meter is not null
            && _activeSession.BalanceRemainingMinutes is not null
            ? $"Осталось {FormatDuration(_activeSession.BalanceRemainingMinutes.Value)}"
        : _activeSession.Meter is not null
            ? $"Использовано {_activeSession.Meter.BilledMinutes} мин"
            : "Время обновляется сервером";
    public string CurrentSessionModeSummary => _activeSession is null
        ? string.Empty
        : _activeSession.LoginGrantRemainingMinutes > 0
            ? "Бесплатное время входа"
        : _activeSession.ActivePackage is not null
            ? "Пакет времени"
        : _activeSession.ActiveTariff?.BillingMode == "per_minute"
            ? "Поминутная игра"
        : _activeSession.ActiveTariff?.Name ?? (_activeSession.Meter is not null
            ? "Поминутная игра"
            : "Игровая сессия");
    public string CurrentSessionTariffSummary => _activeSession is null
        ? string.Empty
        : _activeSession.LoginGrantRemainingMinutes > 0
            ? $"Бесплатные минуты · осталось {FormatDuration(_activeSession.LoginGrantRemainingMinutes)}"
        : _activeSession.ActivePackage is not null
            ? FormatActivePackageSummary(_activeSession.ActivePackage)
        : _activeSession.ActiveTariff is not null
            && _activeSession.ActiveTariff.BillingMode == "per_minute"
            ? FormatPerMinuteTariffSummary(_activeSession.ActiveTariff)
        : _activeSession.ActiveTariff is not null
            ? $"{_activeSession.ActiveTariff.Name} · {_activeSession.ActiveTariff.Quantity} × "
                + $"{_activeSession.ActiveTariff.DurationMinutes} мин"
        : _activeSession.Meter is not null
            ? "Поминутный режим"
            : "Тариф не выбран";
    public string TransferTargetWorkstationId
    {
        get => _transferTargetWorkstationId;
        set
        {
            if (_transferTargetWorkstationId == value)
            {
                return;
            }
            _transferTargetWorkstationId = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanCreateTransferOffer));
        }
    }
    public string IncomingTransferOfferId
    {
        get => _incomingTransferOfferId;
        set
        {
            if (_incomingTransferOfferId == value)
            {
                return;
            }
            _incomingTransferOfferId = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanConfirmTransfer));
        }
    }
    public string IncomingTransferToken
    {
        get => _incomingTransferToken;
        set
        {
            if (_incomingTransferToken == value)
            {
                return;
            }
            _incomingTransferToken = value;
            OnPropertyChanged();
            OnPropertyChanged(nameof(CanConfirmTransfer));
        }
    }
    public bool CanCreateTransferOffer => _activeSession is not null
        && !_portalPasswordResetRequired
        && !string.IsNullOrWhiteSpace(DeviceId)
        && !_isTransferWaiting;
    public bool CanConfirmTransfer => !string.IsNullOrWhiteSpace(DeviceId)
        && !string.IsNullOrWhiteSpace(_incomingTransferOfferId)
        && !string.IsNullOrWhiteSpace(_incomingTransferToken);
    public string TransferMessage => _sessionNotification;
    public bool IsTransferMessageVisible => !string.IsNullOrWhiteSpace(_sessionNotification);
    public string PortalNotification => _sessionNotification;
    public bool IsPortalNotificationVisible => !string.IsNullOrWhiteSpace(_sessionNotification);
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
        OnPropertyChanged(nameof(IsUserLoginVisible));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

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
        OnPropertyChanged(nameof(IsUserLoginVisible));
        OnPropertyChanged(nameof(IsPortalRegistrationVisible));
        OnPropertyChanged(nameof(IsManagerEntryVisible));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    public void SetDeviceIdentity(
        string deviceId,
        string? workstationId = null,
        string? workstationName = null)
    {
        var normalized = deviceId.Trim();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return;
        }

        var deviceChanged = string.IsNullOrWhiteSpace(DeviceId);
        if (deviceChanged)
        {
            DeviceId = normalized;
            OnPropertyChanged(nameof(DeviceId));
        }

        var normalizedWorkstationId = workstationId?.Trim();
        var workstationChanged = string.IsNullOrWhiteSpace(WorkstationId)
            && !string.IsNullOrWhiteSpace(normalizedWorkstationId);
        if (workstationChanged)
        {
            WorkstationId = normalizedWorkstationId;
            OnPropertyChanged(nameof(WorkstationId));
        }

        var normalizedWorkstationName = workstationName?.Trim();
        var workstationNameChanged = string.IsNullOrWhiteSpace(WorkstationName)
            && !string.IsNullOrWhiteSpace(normalizedWorkstationName);
        if (workstationNameChanged)
        {
            _workstationName = normalizedWorkstationName!;
            OnPropertyChanged(nameof(WorkstationName));
        }

        if (deviceChanged || workstationChanged || workstationNameChanged)
        {
            OnPropertyChanged(nameof(DeviceStatus));
            OnPropertyChanged(nameof(CurrentWorkstationLabel));
            OnPropertyChanged(nameof(IsUpcomingBookingVisible));
            OnPropertyChanged(nameof(UpcomingBookingTitle));
            OnPropertyChanged(nameof(UpcomingBookingDetails));
            OnPropertyChanged(nameof(CanCreateTransferOffer));
            OnPropertyChanged(nameof(CanConfirmTransfer));
        }
    }

    public void ApplyWorkstationName(string workstationName)
    {
        var normalized = workstationName.Trim();
        if (string.IsNullOrWhiteSpace(normalized)
            || string.Equals(WorkstationName, normalized, StringComparison.Ordinal))
        {
            return;
        }

        _workstationName = normalized;
        OnPropertyChanged(nameof(WorkstationName));
        OnPropertyChanged(nameof(CurrentWorkstationLabel));
        OnPropertyChanged(nameof(DeviceStatus));
        OnPropertyChanged(nameof(UpcomingBookingTitle));
        OnPropertyChanged(nameof(UpcomingBookingDetails));
    }

    public async Task RunHeartbeatLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(5));
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
            if (_activeSession is not null)
            {
                continue;
            }

            if (_accessGate.LockIfIdle())
            {
                PublishAccessState();
            }
        }
    }

    public async Task RunSessionCountdownLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            if (_activeSession is not null)
            {
                OnPropertyChanged(nameof(ActiveTimeSummary));
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

    public bool TryOpenManagerLoginShortcut(
        bool controlPressed,
        bool altPressed,
        bool pPressed)
    {
        if (!controlPressed
            || !altPressed
            || !pPressed
            || !IsAccessLocked
            || IsWaitingForAssignment)
        {
            return false;
        }

        if (_isManagerLoginRequested)
        {
            return true;
        }

        ShowManagerLogin();
        return true;
    }

    public bool TrySuppressLockedSystemShortcut(
        bool altPressed,
        bool tabPressed,
        bool windowsPressed,
        bool rPressed)
    {
        if (!IsAccessLocked)
        {
            return false;
        }

        return (altPressed && tabPressed) || (windowsPressed && rPressed);
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
        if (!IsOnline)
        {
            _portalMessage = _connection.State == ClientConnectionState.Reconnecting
                ? "Восстанавливаем соединение с сервером"
                : "Нет связи с сервером. Вход временно недоступен";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
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
                PortalPassword,
                DeviceId,
                _lifetime.Token);
            var transferred = await TryClaimPendingTransferAsync(authentication.Snapshot.ClientId);
            if (transferred is not null)
            {
                _activeSession = transferred.Session;
                PublishSessionState();
                _portalPasswordResetRequired = authentication.PasswordResetRequired;
                PortalPasswordSetup = string.Empty;
                PortalPasswordSetupConfirmation = string.Empty;
                SetPortalSnapshot(authentication.Snapshot);
                _accessGate.OpenUserSession("Сессия перенесена на этот ПК");
                _portalMessage = string.Empty;
                PortalPassword = string.Empty;
                PublishAccessState();
                return true;
            }
            if (!await EnsureEntryAllowedAsync(authentication.Snapshot.ClientId))
            {
                return false;
            }
            _portalPasswordResetRequired = authentication.PasswordResetRequired;
            PortalPasswordSetup = string.Empty;
            PortalPasswordSetupConfirmation = string.Empty;
            SetPortalSnapshot(authentication.Snapshot);
            await ActivateQueuedPortalEntitlementQuietlyAsync();
            await StartPortalSessionAsync(authentication.Snapshot.ClientId);
            _accessGate.OpenUserSession();
            _portalMessage = string.Empty;
            PortalPassword = string.Empty;
            PublishAccessState();
            return true;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception error)
        {
            _portalMessage = "Не удалось войти. Проверьте данные и состояние игровой сессии";
            if (error is RpcException rpcError
                && rpcError.StatusCode == StatusCode.AlreadyExists
                && rpcError.Status.Detail.Contains(
                    "Client already has an active session",
                    StringComparison.OrdinalIgnoreCase))
            {
                _portalMessage = "У этого пользователя уже есть активная игровая сессия";
            }
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    public async Task<bool> SetPortalPasswordAsync()
    {
        if (!CanSetPortalPassword || string.IsNullOrWhiteSpace(DeviceId))
        {
            return false;
        }

        try
        {
            var authentication = await _clientPortal.ChangePasswordAsync(
                PortalPasswordSetup,
                DeviceId,
                _lifetime.Token);
            _portalPasswordResetRequired = authentication.PasswordResetRequired;
            PortalPasswordSetup = string.Empty;
            PortalPasswordSetupConfirmation = string.Empty;
            SetPortalSnapshot(authentication.Snapshot);
            ShowSessionNotification("Пароль обновлён. Теперь аккаунт защищён новым паролем.");
            return true;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (RpcException error) when (error.StatusCode == StatusCode.InvalidArgument)
        {
            _portalMessage = "Пароль должен содержать от 4 до 128 символов";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
        catch (Exception)
        {
            _portalMessage = "Не удалось сохранить новый пароль. Повторите попытку";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    public async Task<bool> RegisterPortalAsync()
    {
        if (!IsOnline)
        {
            _portalMessage = _connection.State == ClientConnectionState.Reconnecting
                ? "Восстанавливаем соединение с сервером"
                : "Нет связи с сервером. Регистрация временно недоступна";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
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
                PortalRegistrationPassword,
                DeviceId,
                _lifetime.Token);
            if (!await EnsureEntryAllowedAsync(authentication.Snapshot.ClientId))
            {
                return false;
            }
            _portalPasswordResetRequired = false;
            SetPortalSnapshot(authentication.Snapshot);
            await ActivateQueuedPortalEntitlementQuietlyAsync();
            await StartPortalSessionAsync(authentication.Snapshot.ClientId);
            _accessGate.OpenUserSession();
            _isPortalRegistrationRequested = false;
            _portalMessage = string.Empty;
            PortalRegistrationPassword = string.Empty;
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

    private async Task<bool> EnsureEntryAllowedAsync(string clientId)
    {
        var workstationId = WorkstationId;
        if (string.IsNullOrWhiteSpace(workstationId))
        {
            _portalMessage = string.IsNullOrWhiteSpace(DeviceId)
                ? "ПК ещё не привязан администратором"
                : "ПК привязан, но backend не вернул ID игрового места";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }

        try
        {
            var decision = await _session.BackendClient.CheckEntryAsync(
                workstationId,
                clientId,
                guestId: null,
                deviceId: DeviceId!,
                cancellationToken: _lifetime.Token);
            if (decision.Allowed)
            {
                return true;
            }

            _clientPortal.Logout();
            _portalMessage = decision.Reason switch
            {
                "workstation_disabled" => "Это место отключено администратором",
                "reservation_client_mismatch" => "Место забронировано другим клиентом",
                "reservation_client_required" => "Для этого места требуется клиент из бронирования",
                "guest_reservation_protected" => "Место защищено активным бронированием",
                _ => $"Вход запрещён: {decision.Reason}",
            };
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception)
        {
            _clientPortal.Logout();
            _portalMessage = "Не удалось проверить доступ к этому месту";
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
            if (_activeSession is not null && _activeSession.ActivePackage is null)
            {
                await ActivateQueuedPortalEntitlementQuietlyAsync();
            }
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (DeviceAuthenticationRequiredException)
        {
            if (_activeSession?.ClientId is not null && !IsAccessLocked)
            {
                await ResumePortalSessionQuietlyAsync(_activeSession.Id);
            }
        }
        catch (Exception)
        {
            _portalMessage = "История временно недоступна";
            OnPropertyChanged(nameof(AccessMessage));
        }
    }

    private async Task ActivateQueuedPortalEntitlementQuietlyAsync()
    {
        var queued = _portalSnapshot?.Entitlements
            .OrderBy(item => item.QueuePosition)
            .FirstOrDefault(item => item.Status.Equals("queued", StringComparison.OrdinalIgnoreCase));
        if (queued is null
            || string.IsNullOrWhiteSpace(DeviceId)
            || _portalSnapshot?.Entitlements.Any(item =>
                item.Status.Equals("active", StringComparison.OrdinalIgnoreCase)) == true)
        {
            return;
        }

        try
        {
            SetPortalSnapshot(await _clientPortal.ActivateEntitlementAsync(
                DeviceId,
                queued.Id,
                _lifetime.Token));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            // A queued package can be outside its time window or incompatible
            // with the zone. The session can still start in its normal mode.
        }
    }

    public async Task ActivateFirstPortalEntitlementAsync()
    {
        var entitlement = _portalSnapshot?.Entitlements
            .OrderBy(item => item.QueuePosition)
            .FirstOrDefault(item => item.Status == "queued");
        if (entitlement is null || string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }

        try
        {
            SetPortalSnapshot(await _clientPortal.ActivateEntitlementAsync(
                DeviceId,
                entitlement.Id,
                _lifetime.Token));
            await RefreshActiveSessionSnapshotQuietlyAsync();
            _portalMessage = string.Empty;
            OnPropertyChanged(nameof(AccessMessage));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception)
        {
            _portalMessage = "Не удалось активировать пакет. Обновите снимок и повторите.";
            OnPropertyChanged(nameof(AccessMessage));
        }
    }

    public async Task PurchasePortalTariffAsync(
        string tariffId,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(DeviceId) || FindPortalTariff(tariffId) is null)
        {
            return;
        }

        try
        {
            SetPortalSnapshot(await _clientPortal.PurchaseEntitlementAsync(
                DeviceId,
                tariffId,
                $"win-portal-tariff-{Guid.NewGuid():N}",
                cancellationToken));
            if (_activeSession is not null && _activeSession.ActivePackage is null)
            {
                await ActivateQueuedPortalEntitlementQuietlyAsync();
            }
            await RefreshActiveSessionSnapshotQuietlyAsync();
            ShowSessionNotification("Тариф куплен и применён к текущей сессии или добавлен в очередь.");
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (RpcException error) when (IsInsufficientBalance(error))
        {
            ShowSessionNotification("Недостаточно средств на балансе. Пополните депозит и повторите покупку.");
        }
        catch (Exception)
        {
            ShowSessionNotification("Не удалось купить тариф. Проверьте баланс и повторите.");
        }
    }

    public void ToggleTransferPanel()
    {
        _isTransferExpanded = !_isTransferExpanded;
        OnPropertyChanged(nameof(IsTransferPanelVisible));
        OnPropertyChanged(nameof(TransferToggleLabel));
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
        _activeSession = null;
        _sessionTimeProjection.Reset();
        _clientPortal.Logout();
        _portalSnapshot = null;
        _portalPasswordResetRequired = false;
        PortalPasswordSetup = string.Empty;
        PortalPasswordSetupConfirmation = string.Empty;
        _portalSessionIdempotencyKey = null;
        _accessGate.Lock(message);
        _isManagerLoginRequested = false;
        UserAccessCode = string.Empty;
        ManagerPassword = string.Empty;
        PublishSessionState();
        PublishAccessState();
        PublishPortalState();
    }

    public async Task<bool> LogoutAsync(CancellationToken cancellationToken = default)
    {
        var activeSession = _activeSession;
        if (activeSession is not null && !string.IsNullOrWhiteSpace(DeviceId))
        {
            try
            {
                var stopped = await _session.BackendClient.StopSessionAsync(
                    activeSession.Id,
                    DeviceId,
                    cancellationToken);
                RegisterSessionStopped(stopped);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return false;
            }
            catch (Exception)
            {
                _portalMessage = "Не удалось завершить сессию. Проверьте связь и повторите выход.";
                OnPropertyChanged(nameof(AccessMessage));
                return false;
            }
        }

        LockClient("Экран заблокирован");
        return true;
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
            _portalSessionIdempotencyKey = null;
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
        _portalSessionIdempotencyKey = null;
        PublishSessionState();
        ApplySessionStopPolicy();
        return true;
    }

    public async Task<bool> CreateTransferOfferAsync(CancellationToken cancellationToken = default)
    {
        var activeSession = _activeSession;
        var deviceId = DeviceId;
        if (activeSession is null
            || string.IsNullOrWhiteSpace(deviceId)
            || _isTransferWaiting)
        {
            return false;
        }

        try
        {
            var offer = await _session.BackendClient.CreateTransferOfferAsync(
                activeSession.Id,
                targetWorkstationId: null,
                deviceId: deviceId,
                idempotencyKey: $"win-transfer-{Guid.NewGuid():N}",
                cancellationToken: cancellationToken);
            _transferOfferId = offer.Id;
            _transferOfferToken = offer.Token;
            _isTransferWaiting = true;
            OnPropertyChanged(nameof(IsTransferWaiting));
            OnPropertyChanged(nameof(CanCreateTransferOffer));
            OnPropertyChanged(nameof(TransferToggleLabel));
            ShowSessionNotification(
                "Перенос запущен. Войдите в этот же аккаунт на новом ПК — активная сессия и доступное время перейдут автоматически.");
            TrackBackgroundTask(WaitForTransferCompletionAsync(_lifetime.Token));
            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            ShowSessionNotification("Не удалось подготовить перенос: проверьте целевое место и повторите.");
            return false;
        }
    }

    private async Task<SessionTransferResultSnapshot?> TryClaimPendingTransferAsync(string clientId)
    {
        if (string.IsNullOrWhiteSpace(DeviceId) || string.IsNullOrWhiteSpace(WorkstationId))
        {
            return null;
        }

        try
        {
            return await _session.BackendClient.ClaimPendingTransferAsync(
                clientId,
                WorkstationId,
                DeviceId,
                $"win-transfer-claim-{Guid.NewGuid():N}",
                _lifetime.Token);
        }
        catch (RpcException error) when (
            error.StatusCode is StatusCode.NotFound or StatusCode.FailedPrecondition or StatusCode.Aborted)
        {
            return null;
        }
        catch (Exception)
        {
            // A failed claim must not block an ordinary login. The next login
            // attempt can claim the still-pending offer.
            return null;
        }
    }

    private async Task WaitForTransferCompletionAsync(CancellationToken cancellationToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(2));
        try
        {
            while (_isTransferWaiting
                && !string.IsNullOrWhiteSpace(DeviceId)
                && !string.IsNullOrWhiteSpace(_transferOfferId)
                && !string.IsNullOrWhiteSpace(_transferOfferToken)
                && await timer.WaitForNextTickAsync(cancellationToken))
            {
                try
                {
                    var offer = await _session.BackendClient.GetTransferOfferAsync(
                        _transferOfferId,
                        DeviceId,
                        _transferOfferToken,
                        cancellationToken);
                    if (offer.Status.Equals("confirmed", StringComparison.OrdinalIgnoreCase))
                    {
                        CompleteSourceTransfer();
                        return;
                    }

                    if (offer.Status.Equals("expired", StringComparison.OrdinalIgnoreCase))
                    {
                        _isTransferWaiting = false;
                        _transferOfferId = string.Empty;
                        _transferOfferToken = string.Empty;
                        OnPropertyChanged(nameof(IsTransferWaiting));
                        OnPropertyChanged(nameof(CanCreateTransferOffer));
                        OnPropertyChanged(nameof(TransferToggleLabel));
                        ShowSessionNotification("Время ожидания переноса истекло. Попробуйте ещё раз.");
                        return;
                    }
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    return;
                }
                catch (Exception)
                {
                    // The source remains in the waiting state until the server
                    // confirms or expires the offer.
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
    }

    private void CompleteSourceTransfer()
    {
        _isTransferWaiting = false;
        _transferOfferId = string.Empty;
        _transferOfferToken = string.Empty;
        _activeSession = null;
        _portalSessionIdempotencyKey = null;
        _clientPortal.Logout();
        _portalSnapshot = null;
        _portalPasswordResetRequired = false;
        _accessGate.LockSession("Сессия перенесена на новый ПК. Этот экран будет перезапущен.");
        PublishSessionState();
        PublishPortalState();
        PublishAccessState();
        OnPropertyChanged(nameof(IsTransferWaiting));
        OnPropertyChanged(nameof(CanCreateTransferOffer));
        OnPropertyChanged(nameof(TransferToggleLabel));
    }

    public async Task<bool> ConfirmTransferAsync(CancellationToken cancellationToken = default)
    {
        var deviceId = DeviceId;
        var offerId = _incomingTransferOfferId.Trim();
        var token = _incomingTransferToken.Trim();
        if (string.IsNullOrWhiteSpace(deviceId)
            || string.IsNullOrWhiteSpace(offerId)
            || string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        try
        {
            var result = await _session.BackendClient.ConfirmTransferAsync(
                offerId,
                deviceId,
                token,
                $"win-transfer-confirm-{Guid.NewGuid():N}",
                cancellationToken);
            _activeSession = result.Session;
            PublishSessionState();
            ShowSessionNotification("Сессия перенесена на этот ПК. Старый ПК будет перезапущен.");
            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            ShowSessionNotification("Не удалось подтвердить перенос. Повторите вход на новом ПК.");
            return false;
        }
    }

    public Task RunWorkstationHeartbeatLoopAsync(
        Action<string>? onThemeReceived = null,
        Action<string>? onWorkstationNameReceived = null,
        Action<string>? onManagerPasswordVerifierReceived = null,
        Action<WorkstationLockdownPolicySnapshot>? onLockdownPolicyReceived = null,
        Action<SessionSnapshot>? onSessionSnapshotReceived = null,
        Action<ClientConnectionState>? onConnectionStateChanged = null) =>
        string.IsNullOrWhiteSpace(DeviceId)
            ? Task.CompletedTask
            : _session.RunWorkstationHeartbeatLoopAsync(
                DeviceId,
                ClientVersion,
                Capabilities,
                onThemeReceived,
                onWorkstationNameReceived,
                onManagerPasswordVerifierReceived,
                onLockdownPolicyReceived,
                onSessionSnapshotReceived,
                onConnectionStateChanged,
                RefreshActiveSessionSnapshotAsync,
                _lifetime.Token);

    public void ApplyHeartbeatConnectionState(ClientConnectionState state)
    {
        var message = state switch
        {
            ClientConnectionState.Online => "Соединение установлено",
            ClientConnectionState.Reconnecting => "Восстанавливаем соединение с сервером",
            _ => _connection.Message,
        };
        _connection = _connection with
        {
            State = state,
            Message = message,
            LastSuccessfulContact = state == ClientConnectionState.Online
                ? DateTimeOffset.UtcNow
                : _connection.LastSuccessfulContact,
        };
        OnPropertyChanged(nameof(ConnectionMessage));
        OnPropertyChanged(nameof(IsOnline));
        OnPropertyChanged(nameof(ConnectionColor));
        OnPropertyChanged(nameof(IsUserLoginVisible));
        OnPropertyChanged(nameof(IsPortalRegistrationVisible));
        OnPropertyChanged(nameof(IsManagerEntryVisible));
        OnPropertyChanged(nameof(AccessMessage));
    }

    public void ApplySessionSnapshotFromHeartbeat(SessionSnapshot snapshot)
    {
        if (snapshot.Status.Equals("COMPLETED", StringComparison.OrdinalIgnoreCase)
            || snapshot.Status.Equals("SESSION_STATUS_COMPLETED", StringComparison.OrdinalIgnoreCase))
        {
            RegisterSessionStopped(snapshot);
            return;
        }

        if (_activeSession is null
            || _activeSession.Id.Equals(snapshot.Id, StringComparison.Ordinal))
        {
            ApplyActiveSessionSnapshot(snapshot);
            if (snapshot.ClientId is not null
                && _portalSnapshot is null
                && !IsMaintenanceMode
                && !string.IsNullOrWhiteSpace(DeviceId))
            {
                _ = ResumePortalSessionQuietlyAsync(snapshot.Id);
            }
        }
    }

    private async Task ResumePortalSessionQuietlyAsync(string sessionId)
    {
        if (Interlocked.Exchange(ref _portalResumeInFlight, 1) != 0)
        {
            return;
        }

        try
        {
            if (_activeSession?.Id != sessionId
                || _portalSnapshot is not null
                || string.IsNullOrWhiteSpace(DeviceId))
            {
                return;
            }

            var authentication = await _clientPortal.ResumeAsync(
                DeviceId,
                _lifetime.Token);
            if (authentication is null
                || _activeSession?.Id != sessionId
                || _portalSnapshot is not null)
            {
                return;
            }

            _portalPasswordResetRequired = authentication.PasswordResetRequired;
            SetPortalSnapshot(authentication.Snapshot);
            _portalMessage = string.Empty;
            _accessGate.OpenUserSession("Сессия восстановлена");
            PublishAccessState();
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception)
        {
            // Heartbeat will retry resume after a transient backend/network error.
        }
        finally
        {
            Interlocked.Exchange(ref _portalResumeInFlight, 0);
        }
    }

    private async Task RefreshActiveSessionSnapshotAsync()
    {
        var activeSession = _activeSession;
        if (activeSession is null || string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }

        var snapshot = await _session.BackendClient.GetSessionSnapshotAsync(
            activeSession.Id,
            DeviceId,
            _lifetime.Token);
        if (snapshot.Status.Equals("COMPLETED", StringComparison.OrdinalIgnoreCase)
            || snapshot.Status.Equals("SESSION_STATUS_COMPLETED", StringComparison.OrdinalIgnoreCase))
        {
            RegisterSessionStopped(snapshot);
            return;
        }

        ApplyActiveSessionSnapshot(snapshot);
        var replay = await _session.ReplayOfflineOperationsAsync(
            snapshot,
            DeviceId,
            _lifetime.Token);
        if (replay?.Snapshot is not null)
        {
            ApplyActiveSessionSnapshot(replay.Snapshot);
        }
    }

    private async Task RefreshActiveSessionSnapshotQuietlyAsync()
    {
        try
        {
            await RefreshActiveSessionSnapshotAsync();
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception)
        {
            // The purchase/activation result is already server-confirmed. The
            // next heartbeat will refresh the session snapshot independently.
        }
    }

    private async Task StartPortalSessionAsync(string clientId)
    {
        if (string.IsNullOrWhiteSpace(DeviceId) || string.IsNullOrWhiteSpace(WorkstationId))
        {
            throw new InvalidOperationException("ПК ещё не привязан к рабочему месту");
        }

        var idempotencyKey = _portalSessionIdempotencyKey ??= $"win-portal-session-{Guid.NewGuid():N}";
        var started = await _session.BackendClient.StartSessionAsync(
            WorkstationId!,
            DeviceId!,
            clientId,
            guestName: null,
            reservationId: null,
            idempotencyKey: idempotencyKey,
            cancellationToken: _lifetime.Token);
        var snapshot = await _session.BackendClient.GetSessionSnapshotAsync(
            started.Id,
            DeviceId,
            _lifetime.Token);
        ApplyActiveSessionSnapshot(snapshot);
    }

    public void DismissSessionNotification()
    {
        _sessionNotificationLifetime?.Cancel();
        _sessionNotification = string.Empty;
        PublishSessionNotification();
    }

    public Task RunCommandLoopAsync(IWorkstationCommandExecutor executor) =>
        string.IsNullOrWhiteSpace(DeviceId)
            ? Task.CompletedTask
            : _session.RunCommandLoopAsync(DeviceId, executor, _lifetime.Token);

    public void TrackBackgroundTask(Task task) => _backgroundTasks.Add(task);

    public async ValueTask DisposeAsync()
    {
        _sessionNotificationLifetime?.Cancel();
        _sessionNotificationLifetime?.Dispose();
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

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        if (propertyName == nameof(AccessMessage))
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(IsAccessFeedbackVisible)));
        }
    }

    private void PublishAccessState()
    {
        OnPropertyChanged(nameof(AccessMode));
        OnPropertyChanged(nameof(IsAccessLocked));
        OnPropertyChanged(nameof(IsSessionLocked));
        OnPropertyChanged(nameof(IsMaintenanceMode));
        OnPropertyChanged(nameof(IsAccessGateVisible));
        OnPropertyChanged(nameof(IsSecuredContentVisible));
        OnPropertyChanged(nameof(IsUserLoginVisible));
        OnPropertyChanged(nameof(IsPortalRegistrationVisible));
        OnPropertyChanged(nameof(IsPortalContentVisible));
        OnPropertyChanged(nameof(IsPortalPasswordSetupVisible));
        OnPropertyChanged(nameof(IsPortalReadyVisible));
        OnPropertyChanged(nameof(IsPortalPasswordResetRequired));
        OnPropertyChanged(nameof(IsManagerLoginVisible));
        OnPropertyChanged(nameof(IsMaintenanceVisible));
        OnPropertyChanged(nameof(IsManagerEntryVisible));
        OnPropertyChanged(nameof(AccessMessage));
        OnPropertyChanged(nameof(AccessTitle));
        OnPropertyChanged(nameof(AccessSubtitle));
    }

    private void SetPortalSnapshot(ClientPortalSnapshot snapshot)
    {
        _portalSnapshot = snapshot;
        PublishPortalState();
        PublishSessionState();
    }

    private void PublishPortalState()
    {
        OnPropertyChanged(nameof(IsPortalContentVisible));
        OnPropertyChanged(nameof(IsPortalPasswordSetupVisible));
        OnPropertyChanged(nameof(IsPortalReadyVisible));
        OnPropertyChanged(nameof(IsPortalPasswordResetRequired));
        OnPropertyChanged(nameof(IsSecuredContentVisible));
        OnPropertyChanged(nameof(PortalAccountSummary));
        OnPropertyChanged(nameof(PortalContactSummary));
        OnPropertyChanged(nameof(PortalBalanceSummary));
        OnPropertyChanged(nameof(PortalBalanceAmountSummary));
        OnPropertyChanged(nameof(PortalBonusSummary));
        OnPropertyChanged(nameof(PortalAvailableTimeSummary));
        OnPropertyChanged(nameof(PortalAvailableTimeValue));
        OnPropertyChanged(nameof(IsPortalBalanceTimeVisible));
        OnPropertyChanged(nameof(PortalBalanceHistory));
        OnPropertyChanged(nameof(PortalPurchaseHistory));
        OnPropertyChanged(nameof(PortalChargeHistory));
        OnPropertyChanged(nameof(PortalSessionHistory));
        OnPropertyChanged(nameof(PortalEntitlementQueue));
        OnPropertyChanged(nameof(PortalTariffs));
        OnPropertyChanged(nameof(HasPortalTariffs));
        OnPropertyChanged(nameof(IsTariffsVisible));
        OnPropertyChanged(nameof(HasPortalBalance));
        OnPropertyChanged(nameof(IsUpcomingBookingVisible));
        OnPropertyChanged(nameof(UpcomingBookingTitle));
        OnPropertyChanged(nameof(UpcomingBookingDetails));
        OnPropertyChanged(nameof(CanActivatePortalEntitlement));
    }

    private string FormatActivePackageSummary(SessionPackageSnapshot package)
    {
        var entitlement = _portalSnapshot?.Entitlements.FirstOrDefault(item => item.Id == package.Id);
        var tariff = _portalSnapshot?.Tariffs.FirstOrDefault(item => item.Id == package.TariffId);
        var name = entitlement?.TariffName ?? tariff?.Name ?? package.TariffId;
        long? priceCents = entitlement?.PriceCents ?? tariff?.PriceCents;
        var price = priceCents is not null ? $" · {FormatMoney(priceCents.Value)}" : string.Empty;
        return package.RemainingMinutes > 0
            ? $"Пакет «{name}» · {package.RemainingMinutes} мин{price}"
            : $"Пакет «{name}» завершён";
    }

    private static string FormatEntitlementStatus(string status) =>
        status.Trim().ToLowerInvariant() switch
        {
            "active" => "Активен",
            "queued" => "В очереди",
            _ => "Статус не определён",
        };

    private static string FormatPerMinuteTariffSummary(SessionTariffSnapshot tariff)
    {
        var rate = tariff.PricePerMinuteCents > 0
            ? $" · {FormatMoney(tariff.PricePerMinuteCents)}/мин"
            : string.Empty;
        var free = tariff.FreeMinutes > 0
            ? $" · первые {tariff.FreeMinutes} мин бесплатно"
            : string.Empty;
        return $"{tariff.Name}{rate}{free}";
    }

    private static string FormatMoney(long cents) =>
        (cents / 100m).ToString("N2", CultureInfo.GetCultureInfo("ru-RU")) + " ₽";

    private static string FormatDuration(long minutes)
    {
        var hours = minutes / 60;
        var remainder = minutes % 60;
        return hours > 0 ? $"{hours} ч {remainder} мин" : $"{remainder} мин";
    }

    private static string FormatHistoryTimestamp(string value)
    {
        if (!DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var timestamp))
        {
            return value;
        }

        return timestamp.ToLocalTime().ToString(
            "dd.MM.yyyy HH:mm",
            CultureInfo.GetCultureInfo("ru-RU"));
    }

    private void PublishSessionState()
    {
        OnPropertyChanged(nameof(IsActiveSessionVisible));
        OnPropertyChanged(nameof(CanStopActiveSession));
        OnPropertyChanged(nameof(ActiveSessionDescription));
        OnPropertyChanged(nameof(ActiveTimeSummary));
        OnPropertyChanged(nameof(CurrentSessionModeSummary));
        OnPropertyChanged(nameof(CurrentSessionTariffSummary));
        OnPropertyChanged(nameof(IsPortalBalanceTimeVisible));
        OnPropertyChanged(nameof(CanCreateTransferOffer));
        OnPropertyChanged(nameof(CanConfirmTransfer));
        OnPropertyChanged(nameof(IsTransferWaiting));
        OnPropertyChanged(nameof(TransferToggleLabel));
    }

    private void ApplyActiveSessionSnapshot(SessionSnapshot snapshot)
    {
        var previous = _activeSession;
        _activeSession = snapshot;
        _sessionTimeProjection.Apply(snapshot, _clock());
        if (IsAccessLocked
            && !IsMaintenanceMode
            && snapshot.ClientId is null
            && !string.IsNullOrWhiteSpace(snapshot.GuestName))
        {
            _clientPortal.Logout();
            _portalSnapshot = null;
            _portalMessage = string.Empty;
            _accessGate.OpenUserSession("Гостевая сессия открыта");
            PublishAccessState();
            PublishPortalState();
        }
        if (previous?.ActivePackage?.Id is not null
            && snapshot.ActivePackage?.Id is not null
            && previous.ActivePackage.Id != snapshot.ActivePackage.Id)
        {
            var remaining = snapshot.PackageQueue?.Count ?? 0;
            ShowSessionNotification(
                $"Автоматически активирован пакет {snapshot.ActivePackage.TariffId}. В очереди осталось {remaining}.");
        }
        PublishSessionState();
    }

    private ClientPortalReservation? FindUpcomingBooking()
    {
        if (_portalSnapshot is null || string.IsNullOrWhiteSpace(WorkstationId))
        {
            return null;
        }

        return ClientPortalBookingSelector.FindUpcoming(
            _portalSnapshot.Reservations,
            WorkstationId,
            DateTimeOffset.UtcNow);
    }

    private static string FormatUpcomingBooking(
        ClientPortalReservation? reservation,
        string placeLabel)
    {
        if (reservation is null
            || !DateTimeOffset.TryParse(
                reservation.StartAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var start)
            || !DateTimeOffset.TryParse(
                reservation.EndAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var end))
        {
            return string.Empty;
        }

        var period = $"{start.ToLocalTime():dd.MM, HH:mm}–{end.ToLocalTime():HH:mm}";
        return $"{period} · {placeLabel}";
    }

    private static string FormatUpcomingBookingTitle(ClientPortalReservation? reservation)
    {
        if (reservation is null
            || !DateTimeOffset.TryParse(
                reservation.StartAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var start)
            || !DateTimeOffset.TryParse(
                reservation.EndAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out var end))
        {
            return string.Empty;
        }

        return $"{start.ToLocalTime():dd.MM, HH:mm}–{end.ToLocalTime():HH:mm}";
    }

    private void ShowSessionNotification(string message)
    {
        _sessionNotificationLifetime?.Cancel();
        _sessionNotificationLifetime?.Dispose();
        var lifetime = new CancellationTokenSource();
        _sessionNotificationLifetime = lifetime;
        _sessionNotification = message;
        PublishSessionNotification();
        _ = ClearSessionNotificationAsync(lifetime);
    }

    private async Task ClearSessionNotificationAsync(CancellationTokenSource lifetime)
    {
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(3), lifetime.Token);
            if (!lifetime.IsCancellationRequested && ReferenceEquals(_sessionNotificationLifetime, lifetime))
            {
                _sessionNotification = string.Empty;
                PublishSessionNotification();
            }
        }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested)
        {
        }
    }

    private void PublishSessionNotification()
    {
        OnPropertyChanged(nameof(TransferMessage));
        OnPropertyChanged(nameof(IsTransferMessageVisible));
        OnPropertyChanged(nameof(PortalNotification));
        OnPropertyChanged(nameof(IsPortalNotificationVisible));
    }

    private static bool IsInsufficientBalance(RpcException error) =>
        error.Status.Detail.Contains("Insufficient balance", StringComparison.OrdinalIgnoreCase);

    private void ApplySessionStopPolicy()
    {
        _clientPortal.Logout();
        _portalSnapshot = null;
        _portalPasswordResetRequired = false;
        PortalPasswordSetup = string.Empty;
        PortalPasswordSetupConfirmation = string.Empty;
        _portalSessionIdempotencyKey = null;

        if (_lockdownPolicy.LockAfterSession)
        {
            _accessGate.LockSession("Сессия завершена. Введите код для нового входа");
            PublishAccessState();
        }

        PublishPortalState();

        if (_lockdownPolicy.RestartAfterSession)
        {
            _powerController?.ScheduleRestart();
        }
    }
}
