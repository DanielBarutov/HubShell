namespace GameClub.Client.Application.Ports;

public interface IAccessCredentialVerifier
{
    bool IsUserAccessConfigured { get; }

    bool IsManagerAccessConfigured { get; }

    bool VerifyUserAccess(string accessCode);

    bool VerifyManagerPassword(string password);

    void UpdateManagerPasswordVerifier(string verifier);
}
