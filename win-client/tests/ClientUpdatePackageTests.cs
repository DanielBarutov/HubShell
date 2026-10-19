using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientUpdatePackageTests
{
    [Fact]
    public async Task SignedExeOnlyArchiveExtractsWithoutTouchingInstallationData()
    {
        using var package = new Package();
        var manifest = package.Verify();
        var staged = await ClientUpdatePackage.ExtractVerifiedExecutableAsync(
            manifest, package.ArchivePath, package.Staging);
        Assert.Equal(package.Executable, await File.ReadAllBytesAsync(staged));
        Assert.Equal("existing configuration", await File.ReadAllTextAsync(package.ConfigurationPath));
    }

    [Fact]
    public void ChangedManifestAndUntrustedSigningKeyAreRejected()
    {
        using var package = new Package();
        var bytes = package.ManifestBytes();
        var signature = package.Sign(bytes);
        bytes[^1] ^= 1;
        Assert.Throws<CryptographicException>(() => ClientUpdatePackage.VerifyManifest(
            bytes, signature, package.PublicKey, 1, 1));
        using var otherKey = RSA.Create(2048);
        Assert.Throws<CryptographicException>(() => ClientUpdatePackage.VerifyManifest(
            package.ManifestBytes(), package.Sign(package.ManifestBytes()),
            otherKey.ExportSubjectPublicKeyInfoPem(), 1, 1));
    }

    [Theory]
    [InlineData("../HubShell.exe")]
    [InlineData("folder/HubShell.exe")]
    [InlineData("server.ini")]
    public async Task ArchiveCannotExtractAnyOtherPath(string entryName)
    {
        using var package = new Package(entryName);
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdatePackage.ExtractVerifiedExecutableAsync(package.Verify(), package.ArchivePath, package.Staging));
        Assert.False(Directory.Exists(package.Staging));
    }

    [Fact]
    public async Task ArchiveCannotContainConfigurationOrSymbolicLinks()
    {
        using var extra = new Package(extraEntry: true);
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdatePackage.ExtractVerifiedExecutableAsync(extra.Verify(), extra.ArchivePath, extra.Staging));
        using var link = new Package(symlink: true);
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdatePackage.ExtractVerifiedExecutableAsync(link.Verify(), link.ArchivePath, link.Staging));
    }

    [Fact]
    public async Task CorruptArchiveAndExecutableHashMismatchDoNotLeaveAStagedExecutable()
    {
        using var package = new Package();
        var valid = package.Verify();
        var bytes = await File.ReadAllBytesAsync(package.ArchivePath);
        bytes[0] ^= 1;
        await File.WriteAllBytesAsync(package.ArchivePath, bytes);
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdatePackage.ExtractVerifiedExecutableAsync(valid, package.ArchivePath, package.Staging));
        using var wrongExe = new Package();
        var manifest = wrongExe.Verify(wrongExe.Manifest with { ExecutableSha256 = new string('b', 64) });
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdatePackage.ExtractVerifiedExecutableAsync(manifest, wrongExe.ArchivePath, wrongExe.Staging));
        Assert.False(File.Exists(Path.Combine(wrongExe.Staging, "HubShell.exe.new")));
    }

    [Fact]
    public async Task ExistingStagedFileIsNeverOverwrittenOrDeletedOnFailure()
    {
        using var package = new Package();
        Directory.CreateDirectory(package.Staging);
        var path = Path.Combine(package.Staging, "HubShell.exe.new");
        await File.WriteAllTextAsync(path, "previous staged data");
        await Assert.ThrowsAsync<IOException>(() => ClientUpdatePackage.ExtractVerifiedExecutableAsync(
            package.Verify(), package.ArchivePath, package.Staging));
        Assert.Equal("previous staged data", await File.ReadAllTextAsync(path));
    }

    [Fact]
    public void SignedButIncompatibleOrUnsafeMetadataIsRejected()
    {
        using var package = new Package();
        Assert.Throws<InvalidDataException>(() => package.Verify(package.Manifest with { MinUpdaterProtocol = 2 }));
        Assert.Throws<InvalidDataException>(() => package.Verify(package.Manifest with { MaxBackendProtocol = 0 }));
        Assert.Throws<InvalidDataException>(() => package.Verify(package.Manifest with { ReleaseId = "../release" }));
        Assert.Throws<InvalidDataException>(() => package.Verify(package.Manifest with { ExecutableBytes = long.MaxValue }));
    }

    private sealed class Package : IDisposable
    {
        private readonly RSA _key = RSA.Create(2048);
        private readonly string _root = Path.Combine(Path.GetTempPath(), "hubshell-update-" + Guid.NewGuid().ToString("N"));
        public byte[] Executable { get; } = Encoding.UTF8.GetBytes("MZ test executable content");
        public string ArchivePath => Path.Combine(_root, "HubShell.zip");
        public string Staging => Path.Combine(_root, "staging");
        public string ConfigurationPath => Path.Combine(_root, "server.ini");
        public string PublicKey => _key.ExportSubjectPublicKeyInfoPem();
        public ClientReleaseManifest Manifest { get; }

        public Package(string entryName = "HubShell.exe", bool extraEntry = false, bool symlink = false)
        {
            Directory.CreateDirectory(_root);
            File.WriteAllText(ConfigurationPath, "existing configuration");
            using (var archive = ZipFile.Open(ArchivePath, ZipArchiveMode.Create))
            {
                var entry = archive.CreateEntry(entryName);
                if (symlink) entry.ExternalAttributes = unchecked((int)0xA1FF0000);
                using (var output = entry.Open()) output.Write(Executable);
                if (extraEntry) archive.CreateEntry("server.ini");
            }
            Manifest = new ClientReleaseManifest(1, "v2.4.0", new string('a', 40), "win-x64", "HubShell.exe",
                Convert.ToHexString(SHA256.HashData(Executable)).ToLowerInvariant(), Executable.Length,
                Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(ArchivePath))).ToLowerInvariant(),
                new FileInfo(ArchivePath).Length, 1, 1, 1, 1);
        }

        public byte[] ManifestBytes(ClientReleaseManifest? manifest = null) => JsonSerializer.SerializeToUtf8Bytes(
            manifest ?? Manifest, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase });
        public byte[] Sign(byte[] bytes) => _key.SignData(bytes, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        public ClientReleaseManifest Verify(ClientReleaseManifest? manifest = null)
        {
            var bytes = ManifestBytes(manifest);
            return ClientUpdatePackage.VerifyManifest(bytes, Sign(bytes), PublicKey, 1, 1);
        }

        public void Dispose()
        {
            _key.Dispose();
            Directory.Delete(_root, recursive: true);
        }
    }
}
