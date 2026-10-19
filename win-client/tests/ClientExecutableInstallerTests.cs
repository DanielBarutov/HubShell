using System.Text;
using GameClub.Client.Infrastructure.Updates;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientExecutableInstallerTests
{
    [Fact]
    public void VerifiedReplacementAndRollbackPreserveConfigurationAndKeepFleetBlocked()
    {
        using var fixture = new Installation();
        var verifying = fixture.Installer.Install(fixture.Staged, fixture.Manifest, fixture.Journal);
        Assert.Equal("new executable", File.ReadAllText(fixture.Installer.ExecutablePath));
        Assert.Equal("old executable", File.ReadAllText(fixture.Installer.BackupPath));
        Assert.Equal("verifying", fixture.State.Read()!.Stage);
        var rolledBack = fixture.Installer.Rollback(verifying);
        Assert.Equal("old executable", File.ReadAllText(fixture.Installer.ExecutablePath));
        Assert.True(rolledBack.Blocked);
        Assert.Equal("rolled_back", fixture.State.Read()!.Stage);
        Assert.Equal("configuration stays here", File.ReadAllText(fixture.Config));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void RestartRecoversMissingOrUnexpectedExecutableFromVerifiedBackup(bool corrupt)
    {
        using var fixture = new Installation();
        var pending = fixture.Journal with {
            Stage = "replace_pending", OldExecutableSha256 = ClientExecutableInstaller.Hash(fixture.Installer.ExecutablePath) };
        File.Copy(fixture.Installer.ExecutablePath, fixture.Installer.BackupPath);
        if (corrupt) File.WriteAllText(fixture.Installer.ExecutablePath, "partial replacement");
        else File.Delete(fixture.Installer.ExecutablePath);
        fixture.State.Write(pending);
        var recovered = fixture.Installer.RecoverInterruptedReplacement(fixture.State.Read()!);
        Assert.Equal("rolled_back", recovered.Stage);
        Assert.True(recovered.Blocked);
        Assert.Equal("old executable", File.ReadAllText(fixture.Installer.ExecutablePath));
    }

    [Fact]
    public void RestartWithNewHashWaitsForGuiVerificationRatherThanClaimingSuccess()
    {
        using var fixture = new Installation();
        fixture.Installer.Install(fixture.Staged, fixture.Manifest, fixture.Journal);
        var pending = fixture.State.Read()! with { Stage = "replace_pending" };
        fixture.State.Write(pending);
        var recovered = fixture.Installer.RecoverInterruptedReplacement(fixture.State.Read()!);
        Assert.Equal("verifying", recovered.Stage);
        Assert.True(recovered.Blocked);
    }

    [Fact]
    public void CorruptStagingOrBackupNeverOverwritesTheInstalledExecutable()
    {
        using var fixture = new Installation();
        File.WriteAllText(fixture.Staged, "corrupt package");
        Assert.Throws<InvalidDataException>(() => fixture.Installer.Install(fixture.Staged, fixture.Manifest, fixture.Journal));
        Assert.Equal("old executable", File.ReadAllText(fixture.Installer.ExecutablePath));
        File.WriteAllText(fixture.Installer.BackupPath, "wrong backup");
        Assert.Throws<InvalidDataException>(() => fixture.Installer.Rollback(fixture.Journal with {
            OldExecutableSha256 = new string('b', 64) }));
        Assert.Equal("old executable", File.ReadAllText(fixture.Installer.ExecutablePath));
    }

    private sealed class Installation : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "hubshell-installer-" + Guid.NewGuid().ToString("N"));
        public ClientUpdateStateStore State { get; }
        public ClientExecutableInstaller Installer { get; }
        public string Staged { get; }
        public string Config => Path.Combine(_root, "server.ini");
        public ClientReleaseManifest Manifest { get; }
        public ClientUpdateJournal Journal { get; }

        public Installation()
        {
            Directory.CreateDirectory(_root);
            Directory.CreateDirectory(Path.Combine(_root, "staging"));
            Staged = Path.Combine(_root, "staging", "HubShell.exe.new");
            File.WriteAllText(Path.Combine(_root, "HubShell.exe"), "old executable", new UTF8Encoding(false));
            File.WriteAllText(Staged, "new executable", new UTF8Encoding(false));
            File.WriteAllText(Config, "configuration stays here");
            State = new ClientUpdateStateStore(_root);
            Installer = new ClientExecutableInstaller(_root, State);
            var hash = ClientExecutableInstaller.Hash(Staged);
            Manifest = new ClientReleaseManifest(1, "v2.4.0", new string('a', 40), "win-x64",
                "HubShell.exe", hash, new FileInfo(Staged).Length, new string('b', 64), 1, 1, 1, 1, 1);
            Journal = new ClientUpdateJournal(Guid.NewGuid(), Guid.NewGuid(), "v2.4.0", hash, "prepared", true);
        }

        public void Dispose() => Directory.Delete(_root, recursive: true);
    }
}
