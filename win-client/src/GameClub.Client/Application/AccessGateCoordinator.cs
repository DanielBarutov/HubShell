using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Application;

public sealed class AccessGateCoordinator
{
    public static readonly TimeSpan DefaultIdleTimeout = TimeSpan.FromMinutes(10);
    private static readonly TimeSpan FailedAttemptCooldown = TimeSpan.FromSeconds(30);
    private const int MaxFailedAttempts = 5;

    private readonly IAccessCredentialVerifier _credentials;
    private readonly TimeSpan _idleTimeout;
    private AccessGateSnapshot _snapshot;
    private int _failedAttempts;
    private DateTimeOffset _retryAfter = DateTimeOffset.MinValue;

    public AccessGateCoordinator(
        IAccessCredentialVerifier credentials,
        TimeSpan? idleTimeout = null,
        DateTimeOffset? now = null)
    {
        var configuredIdleTimeout = idleTimeout ?? DefaultIdleTimeout;
        if (configuredIdleTimeout <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(idleTimeout), "Idle timeout must be positive");
        }

        _credentials = credentials;
        _idleTimeout = configuredIdleTimeout;
        _snapshot = new AccessGateSnapshot(
            AccessMode.Locked,
            now ?? DateTimeOffset.UtcNow,
            "Введите код доступа пользователя");
    }

    public AccessGateSnapshot Snapshot => _snapshot;

    public bool IsLocked => _snapshot.Mode is AccessMode.Locked or AccessMode.SessionLocked;

    public bool IsSessionLocked => _snapshot.Mode == AccessMode.SessionLocked;

    public bool IsMaintenance => _snapshot.Mode == AccessMode.Maintenance;

    public bool TryUnlockUser(string accessCode, DateTimeOffset? now = null)
    {
        if (!IsLocked)
        {
            _snapshot = _snapshot with { Message = "Сначала закройте текущий режим доступа" };
            return false;
        }

        var timestamp = now ?? DateTimeOffset.UtcNow;
        if (!CanAttempt(timestamp))
        {
            _snapshot = _snapshot with { Message = "Слишком много попыток. Повторите через 30 секунд" };
            return false;
        }

        if (!_credentials.VerifyUserAccess(accessCode))
        {
            RegisterFailure(timestamp);
            _snapshot = _snapshot with { Message = UserFailureMessage() };
            return false;
        }

        ResetFailures();
        _snapshot = new AccessGateSnapshot(
            AccessMode.User,
            timestamp,
            "Доступ открыт");
        return true;
    }

    public bool TryEnterMaintenance(string password, DateTimeOffset? now = null)
    {
        if (!IsLocked)
        {
            _snapshot = _snapshot with { Message = "Сначала заблокируйте клиент" };
            return false;
        }

        var timestamp = now ?? DateTimeOffset.UtcNow;
        if (!CanAttempt(timestamp))
        {
            _snapshot = _snapshot with { Message = "Слишком много попыток. Повторите через 30 секунд" };
            return false;
        }

        if (!_credentials.VerifyManagerPassword(password))
        {
            RegisterFailure(timestamp);
            _snapshot = _snapshot with { Message = ManagerFailureMessage() };
            return false;
        }

        ResetFailures();
        _snapshot = new AccessGateSnapshot(
            AccessMode.Maintenance,
            timestamp,
            "Режим обслуживания открыт");
        return true;
    }

    public void Touch(DateTimeOffset? now = null)
    {
        if (IsLocked)
        {
            return;
        }

        _snapshot = _snapshot with { LastActivityAt = now ?? DateTimeOffset.UtcNow };
    }

    public bool LockIfIdle(DateTimeOffset? now = null)
    {
        if (IsLocked)
        {
            return false;
        }

        var timestamp = now ?? DateTimeOffset.UtcNow;
        if (timestamp - _snapshot.LastActivityAt < _idleTimeout)
        {
            return false;
        }

        Lock("Экран заблокирован после периода бездействия", timestamp);
        return true;
    }

    public void Lock(string message = "Экран заблокирован", DateTimeOffset? now = null)
    {
        _snapshot = new AccessGateSnapshot(
            AccessMode.Locked,
            now ?? DateTimeOffset.UtcNow,
            message);
    }

    public void LockSession(
        string message = "Сессия завершена",
        DateTimeOffset? now = null)
    {
        _snapshot = new AccessGateSnapshot(
            AccessMode.SessionLocked,
            now ?? DateTimeOffset.UtcNow,
            message);
    }

    private bool CanAttempt(DateTimeOffset now)
    {
        if (now < _retryAfter)
        {
            return false;
        }

        if (_failedAttempts >= MaxFailedAttempts)
        {
            ResetFailures();
        }

        return true;
    }

    private void RegisterFailure(DateTimeOffset now)
    {
        _failedAttempts++;
        if (_failedAttempts >= MaxFailedAttempts)
        {
            _retryAfter = now + FailedAttemptCooldown;
        }
    }

    private void ResetFailures()
    {
        _failedAttempts = 0;
        _retryAfter = DateTimeOffset.MinValue;
    }

    private string UserFailureMessage() => !_credentials.IsUserAccessConfigured
        ? "Вход пользователя не настроен администратором"
        : "Неверный код доступа";

    private string ManagerFailureMessage() => !_credentials.IsManagerAccessConfigured
        ? "Режим обслуживания не настроен администратором"
        : "Неверный пароль менеджера";
}
