using System.Security.Cryptography;
using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class PasswordHashVerifierTests
{
    [Fact]
    public void VerifiesPbkdf2Sha256HashAndRejectsWrongSecret()
    {
        var salt = Enumerable.Range(1, 16).Select(value => (byte)value).ToArray();
        var derived = Rfc2898DeriveBytes.Pbkdf2(
            "manager-secret",
            salt,
            100_000,
            HashAlgorithmName.SHA256,
            32);
        var encoded = string.Join(
            "$",
            "pbkdf2-sha256",
            "100000",
            Convert.ToBase64String(salt),
            Convert.ToBase64String(derived));

        Assert.True(PasswordHashVerifier.Verify("manager-secret", encoded));
        Assert.False(PasswordHashVerifier.Verify("wrong-secret", encoded));
    }

    [Fact]
    public void RejectsUnsupportedOrUnboundedHashParameters()
    {
        Assert.False(PasswordHashVerifier.Verify(
            "manager-secret",
            "pbkdf2-sha256$99999$AQEBAQEBAQEBAQEBAQEBAQ==$AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="));
        Assert.False(PasswordHashVerifier.Verify(
            "manager-secret",
            "pbkdf2-sha256$100000$AQEBAQEBAQEBAQEBAQEBAQ==$AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
                + new string('x', 4097)));
    }
}
