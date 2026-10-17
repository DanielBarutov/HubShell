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
    private readonly IV2ClientPortalGateway? _v2ClientPortal;
    private bool _minuteBonusBusy;
    private bool _minuteBonusPending;
    private bool _minuteBonusCancellationPending;
    private readonly IV2OfflineSessionGateway? _v2OfflineSession;
    private readonly IV2GuestSessionGateway? _v2GuestSession;
    private readonly V2OfflineLoginCoordinator? _v2OfflineLogin;
    private readonly V2LocalLedgerCoordinator? _v2Ledger;
    private readonly V2MinuteLedgerRunner? _v2MinuteRunner;
    private readonly IOfflineSnapshotSignatureVerifier? _v2SignatureVerifier;
    private readonly SessionTimeProjection _sessionTimeProjection = new();
    private readonly TimeNotificationDispatcher _timeNotificationDispatcher;
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
    private V2LocalSessionLedger? _activeV2Ledger;
    private bool _isV2MinuteBillingPaused;
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
    private bool _v2ServerEventTransportFailed;
    private bool _isV2ServerStopPending;
    private int _v2ServerEventIssueCount;
    private string? _portalSessionIdempotencyKey;
    private CancellationTokenSource? _sessionNotificationLifetime;

    public MainViewModel(
        ClientSessionCoordinator session,
        IAccessCredentialVerifier accessCredentials,
        string? deviceId = null,
        string clientVersion = "0.1.0",
        IReadOnlyCollection<string>? capabilities = null,
        IWorkstationPowerController? powerController = null,
        Func<DateTimeOffset>? clock = null,
        ITimeNotificationPresenter? timeNotificationPresenter = null,
        V2OfflineLoginCoordinator? v2OfflineLogin = null,
        V2LocalLedgerCoordinator? v2Ledger = null,
        V2MinuteLedgerRunner? v2MinuteRunner = null,
        IOfflineSnapshotSignatureVerifier? v2SignatureVerifier = null,
        IV2OfflineSessionGateway? v2OfflineSession = null,
        IV2GuestSessionGateway? v2GuestSession = null,
        IV2ClientPortalGateway? v2ClientPortal = null)
    {
        _session = session;
        _accessCredentials = accessCredentials;
        _accessGate = new AccessGateCoordinator(_accessCredentials);
        _clientPortal = session.ClientPortal;
        _v2ClientPortal = v2ClientPortal ?? session.V2ClientPortal;
        _v2OfflineSession = v2OfflineSession ?? session.V2OfflineSession;
        _v2GuestSession = v2GuestSession ?? session.BackendClient as IV2GuestSessionGateway;
        _powerController = powerController;
        _clock = clock ?? (() => DateTimeOffset.UtcNow);
        _timeNotificationDispatcher = new TimeNotificationDispatcher(timeNotificationPresenter);
        if ((v2OfflineLogin is null) != (v2Ledger is null)
            || (v2OfflineLogin is null) != (v2MinuteRunner is null)
            || (v2OfflineLogin is null) != (v2SignatureVerifier is null))
        {
            throw new ArgumentException("V2 access-gate dependencies must be configured together");
        }
        _v2OfflineLogin = v2OfflineLogin;
        _v2Ledger = v2Ledger;
        _v2MinuteRunner = v2MinuteRunner;
        _v2SignatureVerifier = v2SignatureVerifier;
        DeviceId = deviceId;
        ClientVersion = clientVersion;
        Capabilities = capabilities ?? Array.Empty<string>();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public CancellationToken LifetimeToken => _lifetime.Token;

    public string ConnectionMessage => _connection.Message;
    public string BackendVersion => _connection.BackendVersion;
    public bool HasV2ServerEventIssues => _v2ServerEventIssueCount > 0;
    public bool IsV2ServerEventTransportFailed => _v2ServerEventTransportFailed;
    public bool HasV2DeliveryWarning => HasV2ServerEventIssues || IsV2ServerEventTransportFailed;
    public string V2DeliveryStatus => _v2ServerEventTransportFailed
        ? "Ошибка синхронизации"
        : HasV2ServerEventIssues
            ? "Требует проверки"
            : "Синхронизация работает";
    public string V2DeliveryMessage => _v2ServerEventTransportFailed
        ? "Обновления временно не доставляются. Повторим попытку автоматически."
        : HasV2ServerEventIssues
            ? $"Отклонено обновлений: {_v2ServerEventIssueCount}. Финансовые изменения не применены."
            : "Обновления применяются локально до подтверждения сервера.";
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
    public bool IsSecuredContentVisible => !IsAccessLocked
        && !IsMaintenanceMode
        && _portalSnapshot is null
        && !_portalPasswordResetRequired
        && !IsGuestWidgetVisible;
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
    public bool IsPortalContentVisible => (_portalSnapshot is not null || _portalPasswordResetRequired)
        && _activeV2Ledger?.IsGuest != true
        && !IsAccessLocked
        && !IsMaintenanceMode;
    public bool IsGuestWidgetVisible => _activeV2Ledger?.IsGuest == true
        && !IsAccessLocked
        && !IsMaintenanceMode;
    public bool IsWidgetContentVisible => IsPortalContentVisible || IsGuestWidgetVisible;
    public bool IsAccountWidgetReadyVisible => IsPortalContentVisible && !_portalPasswordResetRequired;
    public string WidgetAccountSummary => IsGuestWidgetVisible ? "Гость" : PortalAccountSummary;
    public bool IsPortalPasswordSetupVisible => _portalPasswordResetRequired;
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
    public bool CanSetPortalPassword => _portalPasswordSetup.Length is >= 4 and <= 128;
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
    private long? CurrentPortalBalanceCents => _activeV2Ledger is { IsGuest: false } ledger
        ? ledger.BalanceCents
        : _portalSnapshot?.BalanceCents;
    public string PortalBalanceAmountSummary => CurrentPortalBalanceCents is { } balance
        ? FormatMoney(balance)
        : string.Empty;
    public string PortalBonusAmountSummary => _portalSnapshot?.BonusWallet is { } wallet
        ? $"Бонусы: {FormatMoney(wallet.TotalCents)}"
        : "Бонусы: недоступно";
    public string PortalBonusReservedSummary => _portalSnapshot?.BonusWallet is { } wallet
        ? $"Зарезервировано для игры: {FormatMoney(wallet.ReservedCents)}"
        : "Точный бонусный счёт недоступен";
    public string PortalBonusSummary => _portalSnapshot is null
        ? string.Empty
        : _portalSnapshot.BonusWallet is { } wallet
            ? $"Доступно бонусов: {FormatMoney(wallet.AvailableCents)}\nОжидает начисления: {FormatMoney(wallet.PendingCents)}\nРезерв для игры: {FormatMoney(wallet.ReservedCents)}"
            : "Точный бонусный счёт недоступен";
    public string PortalAvailableTimeValue => _portalSnapshot is null
        ? string.Empty
        : FormatDuration(_portalSnapshot.AvailableTimeMinutes);
    public string PortalBalanceSummary => _portalSnapshot is null
        ? string.Empty
        : $"Баланс: {PortalBalanceAmountSummary} · {PortalBonusSummary}";
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
    public IReadOnlyList<PortalEntitlementRow> PortalEntitlementRows => _portalSnapshot?.Entitlements
        .Where(item => item.Status.Equals("active", StringComparison.OrdinalIgnoreCase)
            || item.Status.Equals("queued", StringComparison.OrdinalIgnoreCase))
        .OrderBy(item => item.QueuePosition)
        .Select(item => new PortalEntitlementRow(
            item.TariffName ?? "Пакет",
            FormatEntitlementStatus(item.Status),
            $"{item.RemainingMinutes} из {item.DurationMinutes} мин",
            item.Status.Equals("active", StringComparison.OrdinalIgnoreCase)))
        .ToArray() ?? Array.Empty<PortalEntitlementRow>();
    public IReadOnlyList<PortalEntitlementRow> WidgetEntitlementRows => _activeV2Ledger is { IsGuest: true } guest
        ? guest.Packages
            .Where(item => item.Status is V2LocalPackageStatus.Active or V2LocalPackageStatus.Queued)
            .Select(item => new PortalEntitlementRow(
                V2PackageName(guest, item),
                item.Status == V2LocalPackageStatus.Active ? "Активен" : "В очереди",
                $"{item.RemainingMinutes} мин",
                item.Status == V2LocalPackageStatus.Active))
            .ToArray()
        : PortalEntitlementRows;
    public IReadOnlyList<string> PortalEntitlementQueue => PortalEntitlementRows
        .Select(item => $"{item.Name} · {item.StatusSummary} · {item.RemainingSummary}")
        .ToArray();
    public IReadOnlyList<ClientPortalTariff> PortalTariffs => _portalSnapshot?.Tariffs
        ?? Array.Empty<ClientPortalTariff>();
    public bool HasPortalTariffs => PortalTariffs.Count > 0;
    public bool IsTariffsVisible => HasPortalTariffs && !_portalPasswordResetRequired
        && _activeV2Ledger?.IsGuest != true;
    public bool HasPortalBalance => CurrentPortalBalanceCents > 0;
    public ClientPortalTariff? FindPortalTariff(string tariffId) =>
        _portalSnapshot?.Tariffs.FirstOrDefault(item => item.Id == tariffId);
    public bool IsUpcomingBookingVisible => _activeV2Ledger?.IsGuest != true
        && FindUpcomingBooking() is not null;
    public string UpcomingBookingTitle => FormatUpcomingBookingTitle(FindUpcomingBooking());
    public string UpcomingBookingDetails => FormatUpcomingBooking(
        FindUpcomingBooking(),
        CurrentWorkstationLabel);
    public bool IsTransferPanelVisible => _isTransferExpanded && !_portalPasswordResetRequired
        && _activeV2Ledger?.IsGuest != true;
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
    public bool IsActiveSessionVisible => (_activeSession is not null || _activeV2Ledger is not null)
        && !_portalPasswordResetRequired;
    public bool CanStopActiveSession => (_activeSession is not null || _activeV2Ledger is not null)
        && !_portalPasswordResetRequired
        && (!IsAccessLocked || _activeV2Ledger is not null)
        && !IsMaintenanceMode;
    public string ActiveSessionDescription => _activeV2Ledger is not null
        ? $"{(_activeV2Ledger.IsGuest ? "Гость" : "Игрок")} · V2 local ledger · {CurrentWorkstationLabel}"
        : _activeSession is null
            ? string.Empty
            : $"{_activeSession.GuestName ?? _activeSession.ClientId ?? "Гость"} · с {_activeSession.StartedAt}";
    public string WidgetTimerSummary
    {
        get
        {
            if (_activeV2Ledger is not null && V2LocalLedgerEngine.HasFreePerMinuteTime(_activeV2Ledger))
            {
                return "∞";
            }
            long? minutes = _activeV2Ledger is not null
                ? V2LocalLedgerEngine.RemainingMinutes(_activeV2Ledger)
                : _sessionTimeProjection.GetRemainingMinutes(_clock());
            return minutes is long value
                ? $"{Math.Max(0, value) / 60:00}:{Math.Max(0, value) % 60:00}"
                : "--:--";
        }
    }
    public string ActiveTimeSummary => _activeV2Ledger is not null
        ? V2ActiveTimeSummary(_activeV2Ledger)
        : _activeSession is null
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
    public string CurrentSessionModeSummary => _activeV2Ledger is not null
        ? V2LocalLedgerEngine.CurrentSource(_activeV2Ledger) switch
        {
            V2TimeSource.LoginGrant => "Бесплатное время входа",
            V2TimeSource.Package => "Пакет времени",
            V2TimeSource.PerMinute => "Поминутная игра",
            _ => "Сессия завершена",
        }
        : _activeSession is null
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
    public string CurrentSessionTariffSummary => _activeV2Ledger is not null
        ? V2TariffSummary(_activeV2Ledger)
        : _activeSession is null
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

    public async Task RecoverV2SessionAsync(
        V2LocalLedgerRecoveryCoordinator recovery,
        CancellationToken cancellationToken = default)
    {
        if (_v2Ledger is null || string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }

        try
        {
            var result = await recovery.RecoverAsync(DeviceId, cancellationToken);
            _v2ServerEventIssueCount = result.ServerEventIssueCount;
            _v2ServerEventTransportFailed = false;
            PublishV2ServerEventState();
            if (result.State != V2LedgerRecoveryState.Active || result.Ledger is null)
            {
                return;
            }

            _activeSession = null;
            _activeV2Ledger = result.Ledger;
            _sessionTimeProjection.Reset();
            if (!result.Ledger.IsGuest && _v2ClientPortal is not null)
            {
                try
                {
                    SetPortalSnapshot(
                        await ResumeV2PortalSnapshotAsync(cancellationToken));
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                {
                    throw;
                }
                catch (RpcException error) when (
                    error.StatusCode is StatusCode.Unavailable or StatusCode.DeadlineExceeded)
                {
                    ClientLog.RpcFailure("v2.portal", error, "resume portal after restart");
                    _portalMessage = "Профиль недоступен без сервера; локальная сессия восстановлена.";
                }
                catch (DeviceAuthenticationRequiredException error)
                {
                    ClientLog.Exception("v2.portal", error, "device identity unavailable during resume");
                    _portalMessage = "Не удалось восстановить профиль; локальная сессия сохранена.";
                }
            }
            if (await StopV2SessionIfServerCompletedAsync())
            {
                return;
            }
            await RetryPendingV2PackagePurchaseAsync(cancellationToken);
            _accessGate.OpenUserSession("Сессия восстановлена после перезапуска");
            PublishSessionState();
            PublishAccessState();
            PublishPortalState();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.recovery", error, "restore local V2 session");
            _activeV2Ledger = null;
            _accessGate.LockSession("V2 ledger требует проверки после перезапуска");
            _portalMessage = "Локальная сессия требует проверки. Доступ заблокирован.";
            PublishSessionState();
            PublishAccessState();
            OnPropertyChanged(nameof(AccessMessage));
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
            await PollGuestAccessAsync();
        }
    }

    private async Task PollGuestAccessAsync()
    {
        if (_v2GuestSession is null || _v2SignatureVerifier is null || string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }
        if (_activeV2Ledger is { IsGuest: false })
        {
            return;
        }
        try
        {
            var activeGuest = _activeV2Ledger is null ? null
                : await _v2Ledger!.ReadLedgerAsync(_lifetime.Token);
            var ledger = await _v2GuestSession.RedeemPendingGuestAccessAsync(
                DeviceId,
                _v2SignatureVerifier,
                _lifetime.Token, activeGuest);
            if (ledger is not null)
            {
                if (activeGuest is not null)
                {
                    var transition = await _v2Ledger!.ApplyGuestPackageAsync(ledger, _lifetime.Token);
                    _activeV2Ledger = transition.Ledger;
                    PublishSessionState();
                }
                else
                {
                    await _v2Ledger!.InitializeNextSessionAsync(ledger, _lifetime.Token);
                    OpenV2Session(ledger, "Гостевая сессия открыта");
                }
            }
        }
        catch (RpcException error) when (
            _activeV2Ledger is { IsGuest: true }
            && error.StatusCode == StatusCode.AlreadyExists
            && error.Status.Detail == "Guest session is no longer active")
        {
            await ApplyV2ServerStopAsync();
        }
        catch (RpcException error) when (
            error.StatusCode is StatusCode.Unavailable or StatusCode.DeadlineExceeded or StatusCode.AlreadyExists)
        {
            ClientLog.RpcFailure("v2.guest", error, "guest access poll");
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.guest", error, "guest access poll");
        }
    }

    public async Task RunAccessLockLoopAsync()
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(30));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            if (_activeSession is not null || _activeV2Ledger is not null)
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
            if (_activeV2Ledger is not null && !_isV2ServerStopPending)
            {
                await ConsumeV2DueMinutesAsync();
            }
            if (_activeSession is not null)
            {
                OnPropertyChanged(nameof(ActiveTimeSummary));
                OnPropertyChanged(nameof(WidgetTimerSummary));
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
        bool rPressed,
        bool dPressed = false)
    {
        if (!IsAccessLocked)
        {
            return false;
        }

        return (altPressed && tabPressed) || (windowsPressed && (rPressed || dPressed));
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
        ClientLog.Info("auth", $"login requested mode={(_v2OfflineLogin is not null ? "v2" : "legacy")} identifierLength={PortalIdentifier.Length}");
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

        if (_v2OfflineLogin is not null)
        {
            return await LoginV2Async();
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
            ClientLog.Exception("auth", error, "legacy login failed");
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    public async Task<bool> SetPortalPasswordAsync()
    {
        ClientLog.Info("auth", "password reset submission requested");
        if (string.IsNullOrWhiteSpace(DeviceId))
        {
            return false;
        }
        if (!CanSetPortalPassword)
        {
            _portalMessage = "Пароль должен содержать от 4 до 128 символов";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
        if (!string.Equals(
                _portalPasswordSetup,
                _portalPasswordSetupConfirmation,
                StringComparison.Ordinal))
        {
            _portalMessage = "Пароли не совпадают. Повторите новый пароль во втором поле.";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }

        try
        {
            if (_v2OfflineLogin is not null && _v2OfflineLogin.PasswordResetRequired)
            {
                var newPassword = PortalPasswordSetup;
                await _v2OfflineLogin.ChangePasswordAsync(
                    newPassword,
                    DeviceId,
                    _lifetime.Token);
                ClientLog.Info("auth", "password reset accepted by backend");
                PortalPasswordSetup = string.Empty;
                PortalPasswordSetupConfirmation = string.Empty;
                PortalPassword = newPassword;
                _portalMessage = string.Empty;
                var loggedIn = await LoginV2Async();
                if (loggedIn)
                {
                    ShowSessionNotification("Пароль обновлён. Сессия открыта.");
                    return true;
                }
                _portalPasswordResetRequired = false;
                _portalMessage = "Пароль сохранён, но автоматический вход не выполнен. Войдите с новым паролем.";
                _accessGate.LockSession(_portalMessage);
                PublishAccessState();
                PublishPortalState();
                return false;
            }

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
            ClientLog.RpcFailure("auth", error, "password reset validation");
            _portalMessage = "Пароль должен содержать от 4 до 128 символов";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
        catch (Exception error)
        {
            ClientLog.Exception("auth", error, "password reset failed");
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

        if (_v2OfflineLogin is not null)
        {
            return await RegisterV2Async();
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
        if (_activeV2Ledger?.IsGuest == true
            || (_portalSnapshot is null && _activeV2Ledger is null)
            || string.IsNullOrWhiteSpace(DeviceId)
            || (IsAccessLocked && !_isV2ServerStopPending))
        {
            return;
        }

        try
        {
            if (_activeV2Ledger is not null && _v2ClientPortal is not null)
            {
                try
                {
                    SetPortalSnapshot(_portalSnapshot is null
                        ? await ResumeV2PortalSnapshotAsync(_lifetime.Token)
                        : await _v2ClientPortal.RefreshAsync(DeviceId, cancellationToken: _lifetime.Token));
                }
                catch (RpcException error) when (error.StatusCode == StatusCode.Unauthenticated)
                {
                    SetPortalSnapshot(await ResumeV2PortalSnapshotAsync(_lifetime.Token));
                }
            }
            else
            {
                if (_portalSnapshot is null)
                {
                    return;
                }
                SetPortalSnapshot(await RefreshPortalSnapshotAsync(DeviceId, _lifetime.Token));
            }
            if (await StopV2SessionIfServerCompletedAsync())
            {
                return;
            }
            await RetryPendingV2PackagePurchaseAsync(_lifetime.Token);
            if (_activeSession is not null && _activeSession.ActivePackage is null)
            {
                await ActivateQueuedPortalEntitlementQuietlyAsync();
            }
            await SynchronizePendingMinuteBonusAsync();
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (RpcException error) when (
            _activeV2Ledger is not null
            && error.StatusCode is StatusCode.Unavailable or StatusCode.DeadlineExceeded)
        {
            ClientLog.RpcFailure("v2.portal", error, "refresh or resume portal");
            _portalMessage = "Портал временно недоступен; локальная сессия продолжает работать.";
            OnPropertyChanged(nameof(AccessMessage));
        }
        catch (RpcException error) when (
            _activeV2Ledger is not null
            && error.StatusCode is StatusCode.AlreadyExists or StatusCode.NotFound or StatusCode.PermissionDenied)
        {
            ClientLog.RpcFailure("v2.portal", error, "resume active V2 session");
            _activeV2Ledger = null;
            _accessGate.LockSession("Сессия не подтверждена сервером; требуется оператор");
            _portalMessage = "Сервер не подтвердил активную сессию. Обратитесь к оператору.";
            PublishSessionState();
            PublishAccessState();
            PublishPortalState();
        }
        catch (DeviceAuthenticationRequiredException)
        {
            if (_activeV2Ledger is not null)
            {
            _portalMessage = "Не удалось восстановить portal-доступ; локальная сессия сохранена.";
                OnPropertyChanged(nameof(AccessMessage));
                return;
            }
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

    private async Task<bool> StopV2SessionIfServerCompletedAsync()
    {
        var ledger = _activeV2Ledger;
        if (ledger is null)
        {
            return false;
        }

        var serverSession = _portalSnapshot?.Sessions.FirstOrDefault(item =>
            Guid.TryParse(item.Id, out var sessionId) && sessionId == ledger.SessionId);
        if (serverSession is null
            || !serverSession.Status.Equals("completed", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return await ApplyV2ServerStopAsync();
    }

    private async Task<bool> ApplyV2ServerStopAsync()
    {
        try
        {
            var transition = await _v2Ledger!.ApplyServerStopAsync(_lifetime.Token);
            _activeV2Ledger = transition.Ledger;
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.ledger", error, "persist operator session stop");
            _portalMessage = "Сервер завершил сеанс; клиент заблокирован до проверки локального ledger.";
            _isV2ServerStopPending = true;
            _accessGate.LockSession("Требуется сохранить завершение сессии");
            OnPropertyChanged(nameof(AccessMessage));
            PublishSessionState();
            PublishAccessState();
            return true;
        }
        _activeV2Ledger = null;
        _isV2ServerStopPending = false;
        _portalMessage ??= "Сеанс завершён оператором.";
        _accessGate.LockSession("Сеанс завершён оператором");
        ApplySessionStopPolicy(clearV1PortalState: false);
        PublishSessionState();
        PublishAccessState();
        return true;
    }

    private Task<ClientPortalSnapshot> RefreshPortalSnapshotAsync(
        string deviceId,
        CancellationToken cancellationToken)
    {
        if (_v2OfflineLogin is not null)
        {
            return _v2ClientPortal is null
                ? Task.FromException<ClientPortalSnapshot>(
                    new InvalidOperationException("Client portal transport is not configured."))
                : _v2ClientPortal.RefreshAsync(deviceId, cancellationToken: cancellationToken);
        }
        return _clientPortal.RefreshAsync(deviceId, cancellationToken: cancellationToken);
    }

    private Task<ClientPortalSnapshot> ResumeV2PortalSnapshotAsync(
        CancellationToken cancellationToken)
    {
        if (_v2ClientPortal is null
            || string.IsNullOrWhiteSpace(DeviceId)
            || _activeV2Ledger is null)
        {
            return Task.FromException<ClientPortalSnapshot>(
                new InvalidOperationException("V2 portal recovery requires a device and active local ledger"));
        }
        return _v2ClientPortal.ResumePortalAsync(
            DeviceId,
            _activeV2Ledger.SessionId.ToString(),
            _activeV2Ledger.ClientId.ToString(),
            cancellationToken);
    }

    private Task<ClientPortalSnapshot> ActivatePortalEntitlementAsync(
        string deviceId,
        string entitlementId,
        CancellationToken cancellationToken)
    {
        if (_v2OfflineLogin is not null)
        {
            return _v2ClientPortal is null
                ? Task.FromException<ClientPortalSnapshot>(
                    new InvalidOperationException("Client portal transport is not configured."))
                : _v2ClientPortal.ActivateEntitlementAsync(deviceId, entitlementId, cancellationToken);
        }
        return _clientPortal.ActivateEntitlementAsync(deviceId, entitlementId, cancellationToken);
    }

    private Task<ClientPortalSnapshot> PurchasePortalEntitlementAsync(
        string deviceId,
        string tariffId,
        string idempotencyKey,
        CancellationToken cancellationToken,
        BonusPurchaseConfirmation? bonusConfirmation = null)
    {
        if (_v2OfflineLogin is not null)
        {
            return _v2ClientPortal is null
                ? Task.FromException<ClientPortalSnapshot>(
                    new InvalidOperationException("Client portal transport is not configured."))
                : _v2ClientPortal.PurchaseEntitlementAsync(
                    deviceId, tariffId, idempotencyKey, _v2SignatureVerifier!, cancellationToken, bonusConfirmation);
        }
        return _clientPortal.PurchaseEntitlementAsync(
            deviceId, tariffId, idempotencyKey, cancellationToken);
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
            SetPortalSnapshot(await ActivatePortalEntitlementAsync(DeviceId, queued.Id, _lifetime.Token));
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            // Пакет может быть вне временного окна или не подходить для зоны.
            // В этом случае сессия всё равно запускается в обычном режиме.
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
            SetPortalSnapshot(await ActivatePortalEntitlementAsync(DeviceId, entitlement.Id, _lifetime.Token));
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

    public bool CanQuoteBonusPackage => _v2ClientPortal is not null && _activeV2Ledger is { IsGuest: false };

    public bool IsMinuteBonusVisible => CanQuoteBonusPackage && _activeV2Ledger is { Status: V2LocalSessionStatus.Active } ledger
        && !V2LocalLedgerEngine.HasFreePerMinuteTime(ledger)
        && ledger.Tariffs.Any(item => item.PerMinutePriceCents > 0 && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, ledger.ZoneId));
    public bool CanChangeMinuteBonus => IsMinuteBonusVisible && !_minuteBonusBusy;
    public bool IsMinuteBonusSelected => _activeV2Ledger?.MinuteBonus?.Enabled == true || (_minuteBonusPending && !_minuteBonusCancellationPending);
    public string MinuteBonusStatus => _minuteBonusBusy ? "Ожидаем ответ сервера…"
        : _minuteBonusCancellationPending ? "Оплата выключена. Отмена запроса и освобождение резерва ожидают синхронизации."
        : _minuteBonusPending ? _activeV2Ledger?.MinuteBonus is { Enabled: true } previous
            ? $"Увеличение ожидает подтверждения. Прежний резерв: {FormatMoney(previous.RemainingCents)}."
            : "Запрос включения ожидает подтверждения; новый резерв пока не расходуется."
        : _activeV2Ledger is { BalanceCents: < 0, MinuteBonus: { Enabled: true } } ? "При денежном долге бонусы не списываются. Резерв сохраняется до погашения долга или отключения."
        : _activeV2Ledger?.MinuteBonus is { Enabled: true } budget ? $"Остаток для поминутки: {FormatMoney(budget.RemainingCents)} · лимит {budget.PaymentLimitBps / 100m:0.##}%"
        : "Поминутка оплачивается с депозита. Освобождение прежнего резерва — после синхронизации.";

    private void PublishMinuteBonusState()
    {
        OnPropertyChanged(nameof(IsMinuteBonusVisible));
        OnPropertyChanged(nameof(CanChangeMinuteBonus));
        OnPropertyChanged(nameof(IsMinuteBonusSelected));
        OnPropertyChanged(nameof(MinuteBonusStatus));
    }

    private async Task<bool> ReadMinuteBonusRequestStateAsync()
    {
        if (_v2Ledger is null || _activeV2Ledger is null) return false;
        try {
            var pending = await _v2Ledger.ReadPendingMinuteBonusAsync(_lifetime.Token);
            _minuteBonusPending = pending.Request is not null;
            _minuteBonusCancellationPending = pending.CancellationPending;
            PublishMinuteBonusState();
            return true;
        }
        catch (Exception) {
            ShowSessionNotification("Не удалось прочитать состояние бонусной оплаты. Повторите синхронизацию.");
            return false;
        }
    }

    public async Task<BonusGameQuote?> QuoteMinuteBonusAsync()
    {
        if (!CanChangeMinuteBonus || _activeV2Ledger is not { } ledger) return null;
        _minuteBonusBusy = true;
        PublishMinuteBonusState();
        try {
            return await _v2ClientPortal!.QuoteMinuteBonusAsync(new(ledger.ClientId, ledger.SessionId, ledger.DeviceId,
                ledger.SnapshotId, ledger.SnapshotVersion, ledger.NextSequence - 1, ledger.PreviousPayloadHash,
                $"minute-quote-{Guid.NewGuid():N}"), _lifetime.Token);
        }
        catch (Exception) { ShowSessionNotification("Расчёт недоступен. Дождитесь синхронизации списаний и проверьте соединение."); return null; }
        finally { _minuteBonusBusy = false; PublishMinuteBonusState(); }
    }

    public async Task SetMinuteBonusAsync(bool enabled)
    {
        if (!CanChangeMinuteBonus || _v2Ledger is null || _v2ClientPortal is null) return;
        _minuteBonusBusy = true;
        PublishMinuteBonusState();
        try {
            if (!enabled) {
                var transition = await _v2Ledger.DisableMinuteBonusAsync(Guid.NewGuid(), _clock(), _lifetime.Token);
                _activeV2Ledger = transition.Ledger;
                _minuteBonusCancellationPending = true;
                await ReadMinuteBonusRequestStateAsync();
                PublishSessionState();
            }
            _activeV2Ledger = await _v2Ledger.SynchronizeMinuteBonusCancellationAsync(
                (request, token) => _v2ClientPortal.CancelMinuteBonusAsync(request, token), _lifetime.Token);
            if (enabled) _activeV2Ledger = await _v2Ledger.EnableMinuteBonusAsync(
                (request, token) => _v2ClientPortal.EnableMinuteBonusAsync(request, _v2SignatureVerifier!, token), _lifetime.Token);
        }
        catch (Exception) { ShowSessionNotification(enabled
            ? "Запрос ожидает подтверждения. Повтор не увеличит резерв дважды; выключатель отменит запрос."
            : "Оплата минут выключена. Резерв освободится после синхронизации."); }
        finally {
            await ReadMinuteBonusRequestStateAsync();
            _minuteBonusBusy = false;
            PublishSessionState();
        }
    }

    private async Task SynchronizePendingMinuteBonusAsync()
    {
        if (_minuteBonusBusy || _v2Ledger is null || _v2ClientPortal is null || _activeV2Ledger is not { Status: V2LocalSessionStatus.Active }) return;
        if (!await ReadMinuteBonusRequestStateAsync()) return;
        if (!_minuteBonusPending) return;
        _minuteBonusBusy = true;
        PublishMinuteBonusState();
        try {
            _activeV2Ledger = _minuteBonusCancellationPending
                ? await _v2Ledger.SynchronizeMinuteBonusCancellationAsync((request, token) => _v2ClientPortal.CancelMinuteBonusAsync(request, token), _lifetime.Token)
                : await _v2Ledger.EnableMinuteBonusAsync((request, token) => _v2ClientPortal.EnableMinuteBonusAsync(request, _v2SignatureVerifier!, token), _lifetime.Token);
        }
        catch (Exception) { /* The durable intent remains pending until its checkpoint is confirmed. */ }
        finally { await ReadMinuteBonusRequestStateAsync(); _minuteBonusBusy = false; PublishSessionState(); }
    }

    public async Task<BonusGameQuote?> QuotePortalTariffAsync(string tariffId, bool useBonus)
    {
        if (!CanQuoteBonusPackage || string.IsNullOrWhiteSpace(DeviceId)) return null;
        try
        {
            if (await _v2Ledger!.ReadPendingPortalPackagePurchaseAsync(_lifetime.Token) is not null)
            {
                await RetryPendingV2PackagePurchaseAsync(_lifetime.Token);
                return null;
            }
            return await _v2ClientPortal!.QuoteEntitlementAsync(DeviceId, tariffId, useBonus, _lifetime.Token);
        }
        catch (Exception)
        {
            ShowSessionNotification("Не удалось получить расчёт покупки. Проверьте соединение и повторите.");
            return null;
        }
    }

    public async Task PurchasePortalTariffAsync(
        string tariffId,
        CancellationToken cancellationToken = default,
        BonusPurchaseConfirmation? bonusConfirmation = null)
    {
        if (string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }

        V2PendingPortalPackagePurchase? pendingPurchase = null;
        try
        {
            if (_activeV2Ledger is not null)
            {
                pendingPurchase = await _v2Ledger!.ReadPendingPortalPackagePurchaseAsync(
                    cancellationToken);
                if (pendingPurchase is not null
                    && !string.Equals(pendingPurchase.TariffId, tariffId, StringComparison.Ordinal))
                {
                    ShowSessionNotification(
                        "Сначала завершите синхронизацию предыдущей покупки пакета.");
                    return;
                }
                if (pendingPurchase is null)
                {
                    if (FindPortalTariff(tariffId) is null)
                    {
                        return;
                    }
                    pendingPurchase = await _v2Ledger.BeginPortalPackagePurchaseAsync(
                        tariffId,
                        cancellationToken,
                        bonusConfirmation);
                }
            }
            else if (FindPortalTariff(tariffId) is null)
            {
                return;
            }
            var snapshot = await PurchasePortalEntitlementAsync(
                DeviceId,
                tariffId,
                pendingPurchase?.IdempotencyKey ?? $"win-portal-tariff-{Guid.NewGuid():N}",
                cancellationToken,
                pendingPurchase?.BonusConfirmation);
            if (pendingPurchase is not null)
            {
                var transition = await _v2Ledger!.CompletePortalPackagePurchaseAsync(
                    tariffId,
                    _clock(),
                    cancellationToken,
                    snapshot.PurchasedPackage);
                _activeV2Ledger = transition.Ledger;
                PublishSessionState();
            }
            SetPortalSnapshot(snapshot);
            if (pendingPurchase is null
                && _activeSession is not null
                && _activeSession.ActivePackage is null)
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
            await AbandonPendingV2PortalPackagePurchaseQuietlyAsync(pendingPurchase);
            ShowSessionNotification("Недостаточно средств на балансе. Пополните депозит и повторите покупку.");
        }
        catch (RpcException error)
        {
            if (pendingPurchase is not null
                && error.StatusCode is StatusCode.InvalidArgument
                    or StatusCode.PermissionDenied
                    or StatusCode.FailedPrecondition
                    or StatusCode.NotFound)
            {
                await AbandonPendingV2PortalPackagePurchaseQuietlyAsync(pendingPurchase);
            }
            ShowSessionNotification(error.StatusCode is StatusCode.Unavailable or StatusCode.DeadlineExceeded
                ? "Покупка ожидает синхронизации; повтор не спишет средства ещё раз."
                : error.StatusCode == StatusCode.FailedPrecondition && pendingPurchase?.BonusConfirmation is not null
                ? "Расчёт покупки изменился. Откройте пакет и подтвердите новые суммы."
                : "Не удалось купить тариф. Проверьте баланс и повторите.");
        }
        catch (Exception)
        {
            ShowSessionNotification(pendingPurchase is null
                ? "Не удалось купить тариф. Проверьте баланс и повторите."
                : "Покупка ожидает синхронизации; повтор не спишет средства ещё раз.");
        }
    }

    private async Task RetryPendingV2PackagePurchaseAsync(
        CancellationToken cancellationToken)
    {
        if (_activeV2Ledger is null || _v2Ledger is null)
        {
            return;
        }
        try
        {
            var pending = await _v2Ledger.ReadPendingPortalPackagePurchaseAsync(cancellationToken);
            if (pending is not null)
            {
                await PurchasePortalTariffAsync(pending.TariffId, cancellationToken);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.ledger", error, "retry pending portal package purchase");
            _portalMessage = "Покупка пакета ожидает синхронизации; повтор не спишет средства ещё раз.";
            OnPropertyChanged(nameof(AccessMessage));
        }
    }

    private async Task AbandonPendingV2PortalPackagePurchaseQuietlyAsync(
        V2PendingPortalPackagePurchase? pendingPurchase)
    {
        if (pendingPurchase is null || _v2Ledger is null)
        {
            return;
        }
        try
        {
            await _v2Ledger.AbandonPendingPortalPackagePurchaseAsync(_lifetime.Token);
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.ledger", error, "clear rejected portal package purchase");
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
        _activeV2Ledger = null;
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
        if (_activeV2Ledger is not null)
        {
            return await StopV2SessionAsync(cancellationToken);
        }
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
        _sessionTimeProjection.Apply(session, _clock());
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
        if (_activeV2Ledger is not null)
        {
            return await StopV2SessionAsync(cancellationToken);
        }
        var activeSession = _activeSession;
        if (activeSession is null || string.IsNullOrWhiteSpace(DeviceId) || !CanStopActiveSession)
        {
            return false;
        }

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
        return true;
    }

    private async Task<bool> StopV2SessionAsync(CancellationToken cancellationToken)
    {
        try
        {
            var transition = await _v2Ledger!.StopEarlyAsync(
                Guid.NewGuid(),
                _clock(),
                cancellationToken);
            _activeV2Ledger = transition.Ledger;
            var serverStopConfirmed = false;
            if (_v2OfflineSession is not null || _v2GuestSession is not null)
            {
                try
                {
                    serverStopConfirmed = await StopV2OnServerAsync(
                        transition.Ledger,
                        cancellationToken);
                }
                catch (Exception error)
                {
                    ClientLog.Exception("v2.session", error, "server stop failed; retaining stop fact");
                }
            }
            _portalMessage = serverStopConfirmed
                ? "Выход выполнен. Резерв бонусов освободится после подтверждения списаний сервером."
                : "Сеанс остановлен локально; сервер завершит его после доставки события.";
            _accessGate.LockSession("Сессия завершена");
            _activeV2Ledger = null;
            ApplySessionStopPolicy(clearV1PortalState: false);
            PublishSessionState();
            PublishAccessState();
            return true;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            return false;
        }
        catch (Exception)
        {
            _portalMessage = "Не удалось безопасно завершить сессию. Повторите после восстановления связи/журнала.";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    private async Task<bool> StopV2OnServerAsync(
        V2LocalSessionLedger ledger,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(DeviceId))
        {
            return false;
        }
        if (ledger.IsGuest)
        {
            if (_v2GuestSession is null)
            {
                return false;
            }
            await _v2GuestSession.StopGuestSessionAsync(
                DeviceId,
                ledger.SessionId.ToString(),
                ledger.GuestPaymentId!.Value.ToString(),
                cancellationToken);
            return true;
        }
        if (_v2OfflineSession is null)
        {
            return false;
        }
        await _v2OfflineSession.StopSessionAsync(
            DeviceId,
            ledger.SessionId.ToString(),
            ledger.ClientId.ToString(),
            cancellationToken);
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
            // Ошибка claim не должна блокировать обычный вход. Следующая попытка
            // входа сможет забрать оставшееся предложение.
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
                    // Источник остаётся в состоянии ожидания, пока сервер
                    // не подтвердит предложение или не завершит его срок.
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
        Action<ClientConnectionState>? onConnectionStateChanged = null,
        Action? onWorkstationDisabled = null) =>
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
                onWorkstationDisabled,
                RefreshActiveSessionSnapshotAsync,
                _lifetime.Token);

    public void ApplyHeartbeatConnectionState(ClientConnectionState state)
    {
        var message = state switch
        {
            ClientConnectionState.Online => "Соединение установлено",
            ClientConnectionState.Reconnecting => "Восстанавливаем соединение с сервером",
            ClientConnectionState.Offline => "Место отключено администратором",
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

    public void ApplyV2ServerEventPollResult(int rejectedCount)
    {
        _v2ServerEventTransportFailed = false;
        if (rejectedCount > 0)
        {
            _v2ServerEventIssueCount = Math.Max(_v2ServerEventIssueCount, rejectedCount);
        }
        PublishV2ServerEventState();
    }

    public void ApplyV2ServerEventTransportFailure(Exception _)
    {
        _v2ServerEventTransportFailed = true;
        PublishV2ServerEventState();
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
            // Покупка и активация уже подтверждены сервером. Следующий heartbeat
            // отдельно обновит snapshot сессии.
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

    private async Task StopPreviouslyTerminatedV2SessionAsync(
        CancellationToken cancellationToken)
    {
        if (_v2Ledger is null
            || (_v2OfflineSession is null && _v2GuestSession is null)
            || string.IsNullOrWhiteSpace(DeviceId))
        {
            return;
        }

        var previous = (await _v2Ledger.ReadSnapshotAsync(cancellationToken))?.Ledger;
        if (previous is null
            || previous.Status is not (V2LocalSessionStatus.Stopped or V2LocalSessionStatus.Exhausted))
        {
            return;
        }
        if (!string.Equals(previous.DeviceId, DeviceId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Completed V2 ledger belongs to another device");
        }

        for (var attempt = 0; ; attempt++)
        {
            try
            {
                if (!await StopV2OnServerAsync(previous, cancellationToken))
                {
                    throw new InvalidOperationException("V2 session stop transport is unavailable");
                }
                return;
            }
            catch (RpcException error) when (error.StatusCode == StatusCode.NotFound)
            {
                ClientLog.Info(
                    "v2.session",
                    $"previous session missing on server; login will clean its orphaned lease session_id={previous.SessionId}");
                return;
            }
            catch (RpcException error) when (
                error.StatusCode is StatusCode.Unavailable or StatusCode.DeadlineExceeded)
            {
                if (attempt >= 2)
                {
                    throw;
                }
                await Task.Delay(TimeSpan.FromMilliseconds(250 * (attempt + 1)), cancellationToken);
            }
        }
    }

    private async Task<bool> LoginV2Async()
    {
        ClientLog.Info("auth", $"v2 login started identifierLength={PortalIdentifier.Length}");
        try
        {
            await StopPreviouslyTerminatedV2SessionAsync(_lifetime.Token);
            var result = await _v2OfflineLogin!.LoginAndInitializeResultAsync(
                PortalIdentifier,
                PortalPassword,
                DeviceId!,
                $"v2-login-{Guid.NewGuid():N}",
                _v2SignatureVerifier!,
                _lifetime.Token);
            if (result.PasswordResetRequired)
            {
                ClientLog.Info("auth", "v2 login requires password reset");
                OpenV2PasswordReset();
                PortalPassword = string.Empty;
                return true;
            }
            var portalSnapshot = _v2ClientPortal is null
                ? null
                : await _v2ClientPortal.RefreshAsync(DeviceId!, cancellationToken: _lifetime.Token);
            OpenV2Session(result.Ledger!, "Сессия открыта");
            ClientLog.Info("auth", "v2 login succeeded");
            if (portalSnapshot is not null)
            {
                SetPortalSnapshot(portalSnapshot);
            }
            PortalPassword = string.Empty;
            return true;
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
            return false;
        }
        catch (RpcException error)
        {
            ClientLog.RpcFailure("auth", error, "v2 login");
            _portalMessage = error.Status.Detail.Contains(
                    "V2 workstation does not accept V1 session creation",
                    StringComparison.OrdinalIgnoreCase)
                ? "Это место настроено на V2, а запущен старый V1-клиент. Перезапустите Linux-клиент V2."
                : error.StatusCode switch
                {
                    StatusCode.Unauthenticated => "Неверный никнейм/телефон или пароль.",
                    StatusCode.AlreadyExists when error.Status.Detail.Contains(
                        "Client already has an active session",
                        StringComparison.OrdinalIgnoreCase)
                        => "У этого пользователя уже есть активная игровая сессия.",
                    StatusCode.AlreadyExists when error.Status.Detail.Contains(
                        "active V2 lease",
                        StringComparison.OrdinalIgnoreCase)
                        => "Предыдущая сессия ещё не завершена. Повторите вход после обновления состояния.",
                    StatusCode.PermissionDenied => "V2-вход запрещён для этого игрового места.",
                    _ => "Не удалось войти в V2. Проверьте данные и состояние места",
                };
            if (error.StatusCode == StatusCode.AlreadyExists
                && error.Status.Detail.Contains(
                    "Client already has an active session",
                    StringComparison.OrdinalIgnoreCase))
            {
                _portalMessage = "У этого пользователя уже есть активная игровая сессия.";
            }
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
        catch (Exception error)
        {
            ClientLog.Exception("auth", error, "v2 login failed");
            _portalMessage = "Не удалось войти. Проверьте данные и состояние сессии";
            OnPropertyChanged(nameof(AccessMessage));
            return false;
        }
    }

    private async Task<bool> RegisterV2Async()
    {
        try
        {
            var ledger = await _v2OfflineLogin!.RegisterAndInitializeAsync(
                PortalNickname,
                PortalPhone,
                PortalRegistrationPassword,
                DeviceId!,
                $"v2-register-{Guid.NewGuid():N}",
                _v2SignatureVerifier!,
                _lifetime.Token);
            var portalSnapshot = _v2ClientPortal is null
                ? null
                : await _v2ClientPortal.RefreshAsync(DeviceId!, cancellationToken: _lifetime.Token);
            OpenV2Session(ledger, "Аккаунт создан, сессия открыта");
            if (portalSnapshot is not null)
            {
                SetPortalSnapshot(portalSnapshot);
            }
            _isPortalRegistrationRequested = false;
            PortalRegistrationPassword = string.Empty;
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

    private void OpenV2Session(V2LocalSessionLedger ledger, string message)
    {
        if (_activeV2Ledger?.SessionId != ledger.SessionId) {
            _minuteBonusPending = false;
            _minuteBonusCancellationPending = false;
            _minuteBonusBusy = false;
        }
        _activeSession = null;
        _activeV2Ledger = ledger;
        _isV2MinuteBillingPaused = false;
        _sessionTimeProjection.Reset();
        _portalPasswordResetRequired = false;
        _portalMessage = string.Empty;
        _accessGate.OpenUserSession(message);
        PublishSessionState();
        PublishAccessState();
        PublishPortalState();
    }

    private void OpenV2PasswordReset()
    {
        _activeSession = null;
        _activeV2Ledger = null;
        _sessionTimeProjection.Reset();
        _portalSnapshot = null;
        _portalPasswordResetRequired = true;
        _portalMessage = "Администратор сбросил пароль. Задайте новый пароль, чтобы продолжить.";
        _accessGate.OpenUserSession("Требуется новый пароль");
        PublishSessionState();
        PublishAccessState();
        PublishPortalState();
    }

    private async Task ConsumeV2DueMinutesAsync()
    {
        if (_isV2MinuteBillingPaused)
        {
            return;
        }
        var before = _activeV2Ledger;
        var stage = "consume_minutes";
        try
        {
            var transitions = await _v2MinuteRunner!.ConsumeDueMinutesAsync(_clock(), _lifetime.Token);
            if (transitions.Count == 0)
            {
                return;
            }
            var last = transitions[^1];
            _activeV2Ledger = last.Ledger;
            ClientLog.Info("v2.minute", $"minute commit succeeded session_id={last.Ledger.SessionId} " +
                $"snapshot_id={last.Ledger.SnapshotId} transitions={transitions.Count} " +
                $"status={last.Ledger.Status} login_grant_remaining={last.Ledger.LoginGrantRemainingMinutes} " +
                $"balance_cents={last.Ledger.BalanceCents} last_boundary={last.Ledger.LastConsumedMinuteUtc:O} " +
                $"lock_workstation={last.LockWorkstation}");
            stage = "publish_session_state";
            PublishSessionState();
            if (last.LockWorkstation)
            {
                stage = "stop_on_server";
                await StopV2OnServerAsync(last.Ledger, _lifetime.Token);
                stage = "lock_access";
                _activeV2Ledger = null;
                _accessGate.LockSession("Время или доступный баланс сессии закончились");
                ApplySessionStopPolicy(clearV1PortalState: false);
                PublishSessionState();
                PublishAccessState();
            }
        }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
        {
        }
        catch (Exception error)
        {
            ClientLog.Exception("v2.minute", error,
                $"ConsumeV2DueMinutesAsync failed stage={stage} " +
                $"session_id={before?.SessionId} snapshot_id={before?.SnapshotId} " +
                $"snapshot_version={before?.SnapshotVersion} zone_id={before?.ZoneId} " +
                $"status_before={before?.Status} status_current={_activeV2Ledger?.Status} " +
                $"login_grant_before={before?.LoginGrantRemainingMinutes} balance_before_cents={before?.BalanceCents} " +
                $"activated_at={before?.ActivatedAtUtc:O} last_boundary_before={before?.LastConsumedMinuteUtc:O} " +
                $"per_minute_candidates={before?.Tariffs.Count(item => (item.IsPerMinute || item.PerMinutePriceCents > 0) && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, before.ZoneId))} " +
                $"stack={error.StackTrace}");
            _isV2MinuteBillingPaused = true;
            _portalMessage = "Не удалось безопасно обновить V2 ledger. Доступ заблокирован до проверки";
            _accessGate.LockSession("V2 ledger требует проверки");
            PublishSessionState();
            PublishAccessState();
        }
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
        OnPropertyChanged(nameof(IsGuestWidgetVisible));
        OnPropertyChanged(nameof(IsWidgetContentVisible));
        OnPropertyChanged(nameof(IsAccountWidgetReadyVisible));
        OnPropertyChanged(nameof(WidgetAccountSummary));
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
        OnPropertyChanged(nameof(IsGuestWidgetVisible));
        OnPropertyChanged(nameof(IsWidgetContentVisible));
        OnPropertyChanged(nameof(IsAccountWidgetReadyVisible));
        OnPropertyChanged(nameof(WidgetAccountSummary));
        OnPropertyChanged(nameof(IsPortalPasswordSetupVisible));
        OnPropertyChanged(nameof(IsPortalReadyVisible));
        OnPropertyChanged(nameof(IsPortalPasswordResetRequired));
        OnPropertyChanged(nameof(IsSecuredContentVisible));
        OnPropertyChanged(nameof(PortalAccountSummary));
        OnPropertyChanged(nameof(PortalContactSummary));
        OnPropertyChanged(nameof(PortalBalanceSummary));
        OnPropertyChanged(nameof(PortalBalanceAmountSummary));
        OnPropertyChanged(nameof(PortalBonusSummary));
        OnPropertyChanged(nameof(PortalBonusAmountSummary));
        OnPropertyChanged(nameof(PortalBonusReservedSummary));
        OnPropertyChanged(nameof(PortalAvailableTimeSummary));
        OnPropertyChanged(nameof(PortalAvailableTimeValue));
        OnPropertyChanged(nameof(IsPortalBalanceTimeVisible));
        OnPropertyChanged(nameof(PortalBalanceHistory));
        OnPropertyChanged(nameof(PortalPurchaseHistory));
        OnPropertyChanged(nameof(PortalChargeHistory));
        OnPropertyChanged(nameof(PortalSessionHistory));
        OnPropertyChanged(nameof(PortalEntitlementQueue));
        OnPropertyChanged(nameof(PortalEntitlementRows));
        OnPropertyChanged(nameof(WidgetEntitlementRows));
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

    private static string V2ActiveTimeSummary(V2LocalSessionLedger ledger) =>
        ledger.Status == V2LocalSessionStatus.Active
            ? V2LocalLedgerEngine.HasFreePerMinuteTime(ledger)
                ? "Бесплатно"
                : $"Осталось {FormatDuration(V2LocalLedgerEngine.RemainingMinutes(ledger))}"
            : "Сессия завершена";

    private static string V2TariffSummary(V2LocalSessionLedger ledger) =>
        V2LocalLedgerEngine.CurrentSource(ledger) switch
        {
            V2TimeSource.LoginGrant =>
                $"Бесплатные минуты · осталось {FormatDuration(ledger.LoginGrantRemainingMinutes)}",
            V2TimeSource.Package => ledger.Packages.FirstOrDefault(item =>
                item.Status is V2LocalPackageStatus.Active or V2LocalPackageStatus.Queued)
                is { } package
                    ? $"Пакет «{V2PackageName(ledger, package)}» · {package.RemainingMinutes} мин"
                    : "Пакет завершён",
            V2TimeSource.PerMinute => ledger.Tariffs.FirstOrDefault(item =>
                (item.IsPerMinute || item.PerMinutePriceCents > 0)
                && V2LocalSessionLedger.IsZoneCompatible(item.ZoneId, ledger.ZoneId))
                is { } tariff
                    ? $"{tariff.Name} · {FormatMoney(tariff.PerMinutePriceCents)}/мин"
                    : "Поминутный тариф недоступен",
            _ => "Тариф завершён",
        };

    private static string V2PackageName(
        V2LocalSessionLedger ledger,
        V2LocalPackage package) =>
        ledger.Tariffs.FirstOrDefault(item =>
                string.Equals(item.Id, package.TariffId, StringComparison.Ordinal))
            is { Name: var name }
            && !string.IsNullOrWhiteSpace(name)
                ? name
                : "Тариф времени";

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
        PublishMinuteBonusState();
        OnPropertyChanged(nameof(PortalBalanceAmountSummary));
        OnPropertyChanged(nameof(PortalBalanceSummary));
        OnPropertyChanged(nameof(HasPortalBalance));
        OnPropertyChanged(nameof(IsGuestWidgetVisible));
        OnPropertyChanged(nameof(IsWidgetContentVisible));
        OnPropertyChanged(nameof(IsAccountWidgetReadyVisible));
        OnPropertyChanged(nameof(IsSecuredContentVisible));
        OnPropertyChanged(nameof(IsPortalContentVisible));
        OnPropertyChanged(nameof(WidgetAccountSummary));
        OnPropertyChanged(nameof(WidgetEntitlementRows));
        OnPropertyChanged(nameof(IsUpcomingBookingVisible));
        OnPropertyChanged(nameof(IsTariffsVisible));
        OnPropertyChanged(nameof(IsTransferPanelVisible));
        OnPropertyChanged(nameof(IsActiveSessionVisible));
        OnPropertyChanged(nameof(CanStopActiveSession));
        OnPropertyChanged(nameof(ActiveSessionDescription));
        OnPropertyChanged(nameof(ActiveTimeSummary));
        OnPropertyChanged(nameof(WidgetTimerSummary));
        OnPropertyChanged(nameof(CurrentSessionModeSummary));
        OnPropertyChanged(nameof(CurrentSessionTariffSummary));
        OnPropertyChanged(nameof(IsPortalBalanceTimeVisible));
        OnPropertyChanged(nameof(CanCreateTransferOffer));
        OnPropertyChanged(nameof(CanConfirmTransfer));
        OnPropertyChanged(nameof(IsTransferWaiting));
        OnPropertyChanged(nameof(TransferToggleLabel));
    }

    private void PublishV2ServerEventState()
    {
        OnPropertyChanged(nameof(HasV2ServerEventIssues));
        OnPropertyChanged(nameof(IsV2ServerEventTransportFailed));
        OnPropertyChanged(nameof(HasV2DeliveryWarning));
        OnPropertyChanged(nameof(V2DeliveryStatus));
        OnPropertyChanged(nameof(V2DeliveryMessage));
    }

    private void ApplyActiveSessionSnapshot(SessionSnapshot snapshot)
    {
        var previous = _activeSession;
        _activeSession = snapshot;
        _sessionTimeProjection.Apply(snapshot, _clock());
        foreach (var notification in _timeNotificationDispatcher.Dispatch(snapshot.TimeNotifications))
        {
            ShowSessionNotification(notification.Message);
        }
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

    private void ApplySessionStopPolicy(bool clearV1PortalState = true)
    {
        if (clearV1PortalState)
        {
            _clientPortal.Logout();
        }
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

public sealed record PortalEntitlementRow(
    string Name,
    string StatusSummary,
    string RemainingSummary,
    bool IsActive);
