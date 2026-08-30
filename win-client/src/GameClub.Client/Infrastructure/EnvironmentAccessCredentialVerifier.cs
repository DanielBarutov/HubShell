using GameClub.Client.Application.Ports;

namespace GameClub.Client.Infrastructure;

public sealed class EnvironmentAccessCredentialVerifier : IAccessCredentialVerifier
{
    // Development-only fallback. This is a PBKDF2 hash, not the plaintext password.
    private const string DevManagerPasswordHash =
        "pbkdf2-sha256$210000$Z2FtZXNoZWxsLWRldi1tYW5hZ2VyLXNhbHQ=$gAOXzB5w2LpyQ+gSNlpVEHQ3YoeYycTTHbWVqzthfAk=";
    private readonly string? _userAccessHash;
    private string? _managerPasswordHash;

    public EnvironmentAccessCredentialVerifier(string environment)
    {
        _userAccessHash = Environment.GetEnvironmentVariable("GAMECLUB_CLIENT_ACCESS_PIN_HASH");
        var configuredManagerHash = Environment.GetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH");
        _managerPasswordHash = string.IsNullOrWhiteSpace(configuredManagerHash)
            && string.Equals(environment, "dev", StringComparison.OrdinalIgnoreCase)
            ? DevManagerPasswordHash
            : configuredManagerHash;

        // Hashes are read from the deployment environment only. Plaintext values
        // are intentionally not supported, including in dev.
        EnvironmentName = environment;
    }

    public string EnvironmentName { get; }

    public bool IsUserAccessConfigured => !string.IsNullOrWhiteSpace(_userAccessHash);

    public bool IsManagerAccessConfigured => !string.IsNullOrWhiteSpace(_managerPasswordHash);

    public bool VerifyUserAccess(string accessCode) =>
        PasswordHashVerifier.Verify(accessCode, _userAccessHash);

    public bool VerifyManagerPassword(string password) =>
        PasswordHashVerifier.Verify(password, _managerPasswordHash);

    public void UpdateManagerPasswordVerifier(string verifier)
    {
        if (!string.IsNullOrWhiteSpace(verifier))
        {
            _managerPasswordHash = verifier.Trim();
        }
    }
}
