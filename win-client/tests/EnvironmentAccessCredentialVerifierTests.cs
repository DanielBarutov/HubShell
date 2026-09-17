using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class EnvironmentAccessCredentialVerifierTests
{
    [Fact]
    public void ProductionKeepsOfflineManagerFallbackWhenServerVerifierIsMissing()
    {
        var previous = Environment.GetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH");
        try
        {
            Environment.SetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH", null);

            var credentials = new EnvironmentAccessCredentialVerifier("production");

            Assert.True(credentials.IsManagerAccessConfigured);
            Assert.True(credentials.VerifyManagerPassword("password"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH", previous);
        }
    }

    [Fact]
    public void InvalidServerVerifierDoesNotReplaceOfflineManagerFallback()
    {
        var previous = Environment.GetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH");
        try
        {
            Environment.SetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH", "not-a-pbkdf2-verifier");

            var credentials = new EnvironmentAccessCredentialVerifier("production");
            credentials.UpdateManagerPasswordVerifier("also-invalid");

            Assert.True(credentials.VerifyManagerPassword("password"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("GAMECLUB_MANAGER_PASSWORD_HASH", previous);
        }
    }
}
