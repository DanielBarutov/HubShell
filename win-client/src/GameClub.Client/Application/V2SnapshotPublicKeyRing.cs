namespace GameClub.Client.Application;

/// <summary>
/// Разбирает публикуемый deployment keyring V2. Формат: key-id=base64;... .
/// Это только открытые Ed25519-ключи; приватные server keys сюда не попадают.
/// </summary>
public static class V2SnapshotPublicKeyRing
{
    public static IReadOnlyDictionary<string, string> Parse(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException("V2 snapshot public keyring is required");
        }

        var keys = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var item in value.Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var separator = item.IndexOf('=');
            if (separator <= 0 || separator == item.Length - 1)
            {
                throw new InvalidOperationException("V2 snapshot public keyring entry must be key-id=base64");
            }
            var keyId = item[..separator].Trim();
            var publicKey = item[(separator + 1)..].Trim();
            if (keyId.Length == 0 || publicKey.Length == 0 || !keys.TryAdd(keyId, publicKey))
            {
                throw new InvalidOperationException("V2 snapshot public keyring contains an invalid or duplicate key id");
            }
        }

        if (keys.Count == 0)
        {
            throw new InvalidOperationException("V2 snapshot public keyring is required");
        }
        return keys;
    }
}
