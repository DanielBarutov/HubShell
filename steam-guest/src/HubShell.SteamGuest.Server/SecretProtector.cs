using System.Security.Cryptography;
using System.Text;

namespace HubShell.SteamGuest.Server;

public sealed class SecretProtector
{
    private readonly byte[] _key;

    public SecretProtector(string base64Key)
    {
        _key = Convert.FromBase64String(base64Key);
        if (_key.Length != 32)
        {
            throw new InvalidOperationException("STEAM_GUEST_MASTER_KEY должен содержать 32 байта в base64.");
        }
    }

    public string Protect(string value)
    {
        var nonce = RandomNumberGenerator.GetBytes(12);
        var plaintext = Encoding.UTF8.GetBytes(value);
        var ciphertext = new byte[plaintext.Length];
        var tag = new byte[16];
        using var aes = new AesGcm(_key, tag.Length);
        aes.Encrypt(nonce, plaintext, ciphertext, tag);
        return Convert.ToBase64String(nonce.Concat(tag).Concat(ciphertext).ToArray());
    }

    public string Unprotect(string value)
    {
        var payload = Convert.FromBase64String(value);
        if (payload.Length < 29)
        {
            throw new InvalidOperationException("Зашифрованный секрет повреждён.");
        }

        var nonce = payload[..12];
        var tag = payload[12..28];
        var ciphertext = payload[28..];
        var plaintext = new byte[ciphertext.Length];
        using var aes = new AesGcm(_key, tag.Length);
        aes.Decrypt(nonce, ciphertext, tag, plaintext);
        return Encoding.UTF8.GetString(plaintext);
    }
}
