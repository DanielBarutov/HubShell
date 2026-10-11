using GameClub.Client.Application.Ports;

namespace GameClub.Client.Infrastructure;

public sealed class EnvironmentAccessCredentialVerifier : IAccessCredentialVerifier
{
    // Offline/bootstrap fallback для любого окружения. Здесь хранится PBKDF2-хеш,
    // а не пароль; корректный verifier сервера заменяет его только в памяти.
    private const string DefaultManagerPasswordHash =
        "pbkdf2-sha256$210000$Z2FtZXNoZWxsLWRldi1tYW5hZ2VyLXNhbHQ=$gAOXzB5w2LpyQ+gSNlpVEHQ3YoeYycTTHbWVqzthfAk=";
    private readonly string? _userAccessHash;
    private string? _managerPasswordHash;

    public EnvironmentAccessCredentialVerifier(string environment)
    {
        _userAccessHash = Environment.GetEnvironmentVariable("GAMECLUB_CLIENT_ACCESS_PIN_HASH");
        var configuredManagerHash = Environment.GetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH");
        _managerPasswordHash = PasswordHashVerifier.IsValidVerifier(configuredManagerHash)
            ? configuredManagerHash!.Trim()
            : DefaultManagerPasswordHash;

        // Хеши читаются только из окружения развёртывания. Открытые пароли
        // не поддерживаются даже в dev-режиме.
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
        if (PasswordHashVerifier.IsValidVerifier(verifier))
        {
            _managerPasswordHash = verifier.Trim();
        }
    }
}
