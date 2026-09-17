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

    public static bool IsValidVerifier(string? encodedHash) =>
        TryParseVerifier(encodedHash, out _, out _, out _);

    public static bool Verify(string? secret, string? encodedHash)
    {
        if (string.IsNullOrEmpty(secret)
            || !TryParseVerifier(encodedHash, out var iterations, out var salt, out var expected))
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

    private static bool TryParseVerifier(
        string? encodedHash,
        out int iterations,
        out byte[] salt,
        out byte[] expected)
    {
        iterations = 0;
        salt = Array.Empty<byte>();
        expected = Array.Empty<byte>();

        if (string.IsNullOrWhiteSpace(encodedHash)
            || encodedHash.Length > MaximumEncodedHashLength)
        {
            return false;
        }

        var parts = encodedHash.Split('$');
        if (parts.Length != 4
            || !string.Equals(parts[0], Scheme, StringComparison.Ordinal)
            || !int.TryParse(parts[1], out iterations)
            || iterations is < MinimumIterations or > MaximumIterations)
        {
            return false;
        }

        try
        {
            salt = Convert.FromBase64String(parts[2]);
            expected = Convert.FromBase64String(parts[3]);
            return salt.Length is >= 16 and <= MaximumSaltLength
                && expected.Length is >= 16 and <= MaximumDerivedKeyLength;
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
