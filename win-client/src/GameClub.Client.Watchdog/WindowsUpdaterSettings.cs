using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Watchdog;

[SupportedOSPlatform("windows")]
internal sealed record WindowsUpdaterSettings(string BackendAddress, string DeviceId,
    string InstallationId, string EncryptedCredentialSecret, string TrustedPublicKeyPem)
{
    public static WindowsUpdaterSettings? Load(string directory)
    {
        var path = Path.Combine(directory, ".client-updater.json");
        if (!File.Exists(path)) return null;
        var file = new FileInfo(path);
        if (file.Length > 32768 || (file.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Invalid updater configuration file");
        var acl = file.GetAccessControl();
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var admins = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var owner = acl.GetOwner(typeof(SecurityIdentifier));
        if (!Equals(owner, system) && !Equals(owner, admins))
            throw new UnauthorizedAccessException("Updater configuration owner must be SYSTEM or Administrators");
        foreach (FileSystemAccessRule rule in acl.GetAccessRules(true, true, typeof(SecurityIdentifier)))
            if (rule.AccessControlType == AccessControlType.Allow
                && !Equals(rule.IdentityReference, system) && !Equals(rule.IdentityReference, admins))
                throw new UnauthorizedAccessException("Updater credentials cannot be readable by ordinary users");
        var value = JsonSerializer.Deserialize<WindowsUpdaterSettings>(File.ReadAllBytes(path),
            new JsonSerializerOptions(JsonSerializerDefaults.Web) {
                UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow })
            ?? throw new InvalidDataException("Missing updater configuration");
        var address = EndpointPolicy.Validate(new Uri(value.BackendAddress), "Updater backend", "production");
        if (address.UserInfo.Length != 0 || address.Query.Length != 0 || address.Fragment.Length != 0
            || string.IsNullOrWhiteSpace(value.DeviceId) || value.DeviceId.Length > 128
            || string.IsNullOrWhiteSpace(value.InstallationId) || value.InstallationId.Length > 128
            || !value.TrustedPublicKeyPem.Contains("-----BEGIN PUBLIC KEY-----", StringComparison.Ordinal)
            || value.TrustedPublicKeyPem.Contains("PRIVATE KEY", StringComparison.Ordinal))
            throw new InvalidDataException("Invalid updater identity or trust configuration");
        using var rsa = RSA.Create();
        rsa.ImportFromPem(value.TrustedPublicKeyPem);
        if (rsa.KeySize < 2048) throw new InvalidDataException("Updater signing key is too short");
        return value;
    }

    public static void Configure(string directory, string enrollmentFile, string backendAddress, string publicKeyFile)
    {
        using var current = WindowsIdentity.GetCurrent();
        if (!new WindowsPrincipal(current).IsInRole(WindowsBuiltInRole.Administrator))
            throw new UnauthorizedAccessException("Updater configuration requires an administrator");
        if (new FileInfo(enrollmentFile).Length > 4096 || new FileInfo(publicKeyFile).Length > 16384)
            throw new InvalidDataException("Updater enrollment input is too large");
        using var enrollment = JsonDocument.Parse(File.ReadAllBytes(enrollmentFile));
        var root = enrollment.RootElement;
        var secret = root.GetProperty("credential_secret").GetString() ?? "";
        var device = root.GetProperty("device_id").GetString() ?? "";
        var installation = root.GetProperty("installation_id").GetString() ?? "";
        if (secret.Length is < 32 or > 256 || device.Length is < 1 or > 128 || installation.Length is < 1 or > 128)
            throw new InvalidDataException("Invalid updater enrollment");
        EndpointPolicy.Validate(new Uri(backendAddress), "Updater backend", "production");
        var key = File.ReadAllText(publicKeyFile);
        if (!key.Contains("-----BEGIN PUBLIC KEY-----", StringComparison.Ordinal)
            || key.Contains("PRIVATE KEY", StringComparison.Ordinal))
            throw new InvalidDataException("A public signing key is required");
        using (var rsa = RSA.Create())
        {
            rsa.ImportFromPem(key);
            if (rsa.KeySize < 2048) throw new InvalidDataException("Updater signing key is too short");
        }
        var clear = Encoding.UTF8.GetBytes(secret);
        byte[] encrypted;
        try { encrypted = ProtectedData.Protect(clear, null, DataProtectionScope.LocalMachine); }
        finally { CryptographicOperations.ZeroMemory(clear); }
        var value = new WindowsUpdaterSettings(backendAddress, device, installation,
            Convert.ToBase64String(encrypted), key);
        var system = new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null);
        var admins = new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid, null);
        var security = new FileSecurity();
        security.SetAccessRuleProtection(true, false);
        security.SetOwner(admins);
        security.AddAccessRule(new FileSystemAccessRule(system, FileSystemRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(admins, FileSystemRights.FullControl, AccessControlType.Allow));
        var path = Path.Combine(directory, ".client-updater.json");
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".new";
        try
        {
            using (var file = FileSystemAclExtensions.Create(new FileInfo(temporary), FileMode.CreateNew,
                FileSystemRights.Write, FileShare.None, 4096, FileOptions.WriteThrough, security))
            {
                file.Write(JsonSerializer.SerializeToUtf8Bytes(value, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
                file.Flush(flushToDisk: true);
            }
            File.Move(temporary, path, overwrite: true);
            new FileInfo(path).SetAccessControl(security);
            _ = Load(directory)?.DecryptSecret() ?? throw new InvalidDataException("Updater configuration was not saved");
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    public string DecryptSecret()
    {
        var clear = ProtectedData.Unprotect(Convert.FromBase64String(EncryptedCredentialSecret), null,
            DataProtectionScope.LocalMachine);
        try
        {
            var secret = Encoding.UTF8.GetString(clear);
            if (secret.Length is < 32 or > 256) throw new InvalidDataException("Invalid updater credential");
            return secret;
        }
        finally { CryptographicOperations.ZeroMemory(clear); }
    }
}
