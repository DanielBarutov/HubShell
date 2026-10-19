using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace GameClub.Client.Infrastructure.Updates;

public sealed record ClientReleaseManifest(
    int SchemaVersion,
    string ReleaseId,
    string Commit,
    string Runtime,
    string ExecutableName,
    string ExecutableSha256,
    long ExecutableBytes,
    string ArchiveSha256,
    long ArchiveBytes,
    int MinUpdaterProtocol,
    int MaxUpdaterProtocol,
    int MinBackendProtocol,
    int MaxBackendProtocol);

public static class ClientUpdatePackage
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };

    public static ClientReleaseManifest VerifyManifest(
        byte[] manifestBytes, byte[] signature, string trustedPublicKeyPem,
        int backendProtocol, int updaterProtocol)
    {
        if (manifestBytes.Length is 0 or > 16384)
            throw new InvalidDataException("Invalid release manifest size");
        using var rsa = RSA.Create();
        rsa.ImportFromPem(trustedPublicKeyPem);
        if (rsa.KeySize < 2048 || !rsa.VerifyData(manifestBytes, signature,
                HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))
            throw new CryptographicException("Untrusted release manifest");
        var manifest = JsonSerializer.Deserialize<ClientReleaseManifest>(manifestBytes, JsonOptions)
            ?? throw new InvalidDataException("Missing release manifest");
        if (manifest.SchemaVersion != 1 || manifest.Runtime != "win-x64"
            || manifest.ExecutableName != "HubShell.exe"
            || !Regex.IsMatch(manifest.ReleaseId ?? "", @"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\z")
            || !Regex.IsMatch(manifest.Commit ?? "", @"\A[a-f0-9]{40}\z")
            || !IsHash(manifest.ExecutableSha256) || !IsHash(manifest.ArchiveSha256)
            || manifest.ExecutableBytes is <= 0 or > 536870912
            || manifest.ArchiveBytes is <= 0 or > 536870912
            || manifest.MinUpdaterProtocol < 1 || manifest.MinBackendProtocol < 1
            || updaterProtocol < manifest.MinUpdaterProtocol || updaterProtocol > manifest.MaxUpdaterProtocol
            || backendProtocol < manifest.MinBackendProtocol || backendProtocol > manifest.MaxBackendProtocol)
            throw new InvalidDataException("Invalid or incompatible release manifest");
        return manifest;
    }

    public static async Task<string> ExtractVerifiedExecutableAsync(
        ClientReleaseManifest manifest, string archivePath, string stagingDirectory,
        CancellationToken cancellationToken = default)
    {
        await using var archiveStream = new FileStream(archivePath, FileMode.Open,
            FileAccess.Read, FileShare.Read, 81920, useAsync: true);
        if (archiveStream.Length != manifest.ArchiveBytes
            || !MatchesHash(await SHA256.HashDataAsync(archiveStream, cancellationToken), manifest.ArchiveSha256))
            throw new InvalidDataException("Release archive does not match signed manifest");
        archiveStream.Position = 0;
        using var archive = new ZipArchive(archiveStream, ZipArchiveMode.Read, leaveOpen: true);
        if (archive.Entries.Count != 1)
            throw new InvalidDataException("Release archive must contain only HubShell.exe");
        var entry = archive.Entries[0];
        var unixType = (entry.ExternalAttributes >> 16) & 0xF000;
        if (entry.FullName != "HubShell.exe" || entry.Length != manifest.ExecutableBytes
            || unixType is not (0 or 0x8000))
            throw new InvalidDataException("Invalid executable entry in release archive");
        Directory.CreateDirectory(stagingDirectory);
        if ((File.GetAttributes(stagingDirectory) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Staging directory cannot be a link");
        var destination = Path.Combine(stagingDirectory, "HubShell.exe.new");
        var created = false;
        try
        {
            await using (var output = new FileStream(destination, FileMode.CreateNew,
                             FileAccess.Write, FileShare.None, 81920, useAsync: true))
            {
                created = true;
                using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                await using var input = entry.Open();
                var buffer = new byte[81920];
                long written = 0;
                int count;
                while ((count = await input.ReadAsync(buffer, cancellationToken)) != 0)
                {
                    written = checked(written + count);
                    if (written > manifest.ExecutableBytes)
                        throw new InvalidDataException("Executable exceeds signed size");
                    hash.AppendData(buffer, 0, count);
                    await output.WriteAsync(buffer.AsMemory(0, count), cancellationToken);
                }
                if (written != manifest.ExecutableBytes
                    || !MatchesHash(hash.GetHashAndReset(), manifest.ExecutableSha256))
                    throw new InvalidDataException("Executable does not match signed manifest");
                await output.FlushAsync(cancellationToken);
                output.Flush(flushToDisk: true);
            }
            return destination;
        }
        catch
        {
            if (created) File.Delete(destination);
            throw;
        }
    }

    private static bool IsHash(string? value) =>
        Regex.IsMatch(value ?? "", @"\A[a-f0-9]{64}\z");

    private static bool MatchesHash(byte[] actual, string expected) =>
        CryptographicOperations.FixedTimeEquals(actual, Convert.FromHexString(expected));
}
