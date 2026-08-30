using System.Security.Cryptography;

namespace GameClub.Client.Infrastructure;

public static class PasswordHashVerifier
{
    private const string Scheme = "pbkdf2-sha256";
    private const int MinimumIterations = 100_000;
    private const int MaximumIterations = 1_000_000;
    private const int MaximumEncodedHashLength = 4096;
    private const int MaximumSaltLength = 64;
    private const int MaximumDerivedKeyLength = 64;

    public static bool Verify(string? secret, string? encodedHash)
    {
        if (string.IsNullOrEmpty(secret)
            || string.IsNullOrWhiteSpace(encodedHash)
            || encodedHash.Length > MaximumEncodedHashLength)
        {
            return false;
        }

        var parts = encodedHash.Split('$');
        if (parts.Length != 4
            || !string.Equals(parts[0], Scheme, StringComparison.Ordinal)
            || !int.TryParse(parts[1], out var iterations)
            || iterations is < MinimumIterations or > MaximumIterations)
        {
            return false;
        }

        try
        {
            var salt = Convert.FromBase64String(parts[2]);
            var expected = Convert.FromBase64String(parts[3]);
            if (salt.Length is < 16 or > MaximumSaltLength
                || expected.Length is < 16 or > MaximumDerivedKeyLength)
            {
                return false;
            }

            var actual = Rfc2898DeriveBytes.Pbkdf2(
                secret,
                salt,
                iterations,
                HashAlgorithmName.SHA256,
                expected.Length);
            return CryptographicOperations.FixedTimeEquals(actual, expected);
        }
        catch (FormatException)
        {
            return false;
        }
        catch (ArgumentException)
        {
            return false;
        }
    }
}
