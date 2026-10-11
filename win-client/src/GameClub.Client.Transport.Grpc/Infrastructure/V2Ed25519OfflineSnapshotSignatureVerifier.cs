using GameClub.Client.Application.Ports;
using NSec.Cryptography;

namespace GameClub.Client.Infrastructure;

/// <summary>Проверка только для V2; Windows-релиз получает только открытые ключи.</summary>
public sealed class V2Ed25519OfflineSnapshotSignatureVerifier : IOfflineSnapshotSignatureVerifier
{
    private readonly Dictionary<string, PublicKey> _publicKeys;

    public V2Ed25519OfflineSnapshotSignatureVerifier(
        IReadOnlyDictionary<string, string> publicKeysBase64)
    {
        _publicKeys = new Dictionary<string, PublicKey>(StringComparer.Ordinal);
        foreach (var (keyId, publicKeyBase64) in publicKeysBase64)
        {
            if (string.IsNullOrWhiteSpace(keyId))
            {
                throw new ArgumentException("V2 snapshot public key id is required", nameof(publicKeysBase64));
            }
            byte[] publicKeyBytes;
            try
            {
                publicKeyBytes = Convert.FromBase64String(publicKeyBase64);
            }
            catch (FormatException error)
            {
                throw new ArgumentException("V2 snapshot public key must be base64", nameof(publicKeysBase64), error);
            }
            if (publicKeyBytes.Length != 32)
            {
                throw new ArgumentException("V2 snapshot Ed25519 public key must contain 32 bytes", nameof(publicKeysBase64));
            }
            _publicKeys.Add(
                keyId,
                PublicKey.Import(SignatureAlgorithm.Ed25519, publicKeyBytes, KeyBlobFormat.RawPublicKey));
        }
        if (_publicKeys.Count == 0)
        {
            throw new ArgumentException("At least one V2 snapshot public key is required", nameof(publicKeysBase64));
        }
    }

    public bool Verify(string signingKeyId, ReadOnlyMemory<byte> payload, ReadOnlyMemory<byte> signature) =>
        _publicKeys.TryGetValue(signingKeyId, out var publicKey)
        && SignatureAlgorithm.Ed25519.Verify(publicKey, payload.Span, signature.Span);
}
