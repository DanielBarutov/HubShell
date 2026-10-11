using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Application;

/// <summary>
/// Единственная application-точка V2-входа: transport проверяет signed
/// snapshot, затем coordinator сохраняет пустой local ledger до открытия
/// доступа. V1 portal и server-side timer сюда не входят.
/// </summary>
public sealed class V2OfflineLoginCoordinator
{
    private readonly IV2OfflineSessionGateway _gateway;
    private readonly V2LocalLedgerCoordinator _ledger;
    private string? _passwordResetToken;

    public V2OfflineLoginCoordinator(
        IV2OfflineSessionGateway gateway,
        V2LocalLedgerCoordinator ledger)
    {
        _gateway = gateway;
        _ledger = ledger;
    }

    public bool PasswordResetRequired => !string.IsNullOrWhiteSpace(_passwordResetToken);

    public async Task<V2LocalSessionLedger> LoginAndInitializeAsync(
        string identifier,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        var result = await LoginAndInitializeResultAsync(
            identifier,
            password,
            deviceId,
            idempotencyKey,
            signatureVerifier,
            cancellationToken);
        if (result.Ledger is null)
        {
            throw new InvalidOperationException("V2 login requires a password reset");
        }
        return result.Ledger;
    }

    public async Task<V2OfflineLoginResult> LoginAndInitializeResultAsync(
        string identifier,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        await EnsureNoActiveLedgerAsync(cancellationToken);
        var result = await _gateway.LoginAsync(
            identifier,
            password,
            deviceId,
            idempotencyKey,
            signatureVerifier,
            cancellationToken);
        if (result.PasswordResetRequired)
        {
            if (string.IsNullOrWhiteSpace(result.PasswordResetToken) || result.Ledger is not null)
            {
                throw new InvalidOperationException("V2 password reset challenge is invalid");
            }
            _passwordResetToken = result.PasswordResetToken;
            return result;
        }
        if (result.Ledger is null)
        {
            throw new InvalidOperationException("V2 login returned no session snapshot");
        }
        _passwordResetToken = null;
        var snapshot = result.Ledger;
        if (!string.Equals(snapshot.DeviceId, deviceId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("V2 snapshot belongs to another device");
        }
        await _ledger.InitializeNextSessionAsync(snapshot, cancellationToken);
        return result;
    }

    public async Task<V2LocalSessionLedger> RegisterAndInitializeAsync(
        string nickname,
        string phone,
        string password,
        string deviceId,
        string idempotencyKey,
        IOfflineSnapshotSignatureVerifier signatureVerifier,
        CancellationToken cancellationToken = default)
    {
        await EnsureNoActiveLedgerAsync(cancellationToken);
        var result = await _gateway.RegisterAsync(
            nickname,
            phone,
            password,
            deviceId,
            idempotencyKey,
            signatureVerifier,
            cancellationToken);
        if (result.Ledger is null || result.PasswordResetRequired)
        {
            throw new InvalidOperationException("V2 registration returned an invalid login result");
        }
        var snapshot = result.Ledger;
        if (!string.Equals(snapshot.DeviceId, deviceId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("V2 snapshot belongs to another device");
        }
        await _ledger.InitializeNextSessionAsync(snapshot, cancellationToken);
        return snapshot;
    }

    private async Task EnsureNoActiveLedgerAsync(CancellationToken cancellationToken)
    {
        var snapshot = await _ledger.ReadSnapshotAsync(cancellationToken);
        if (snapshot?.Ledger.Status == V2LocalSessionStatus.Active)
        {
            throw new InvalidOperationException("An active V2 local ledger cannot be replaced");
        }
    }

    public async Task ChangePasswordAsync(
        string newPassword,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        var resetToken = _passwordResetToken;
        if (string.IsNullOrWhiteSpace(resetToken))
        {
            throw new InvalidOperationException("V2 password reset is not pending");
        }
        await _gateway.ChangePasswordAsync(newPassword, deviceId, resetToken, cancellationToken);
        _passwordResetToken = null;
    }
}
