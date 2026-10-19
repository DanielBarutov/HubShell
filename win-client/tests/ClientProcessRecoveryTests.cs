using GameClub.Client.Windows;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientProcessRecoveryTests
{
    [Fact]
    public void SeparateWatchdogLaunchesTheGuiFromItsOwnInstallationDirectory()
    {
        var installation = Path.Combine(Path.GetTempPath(), "GameClub");
        Assert.Equal(Path.Combine(installation, "HubShell.exe"),
            ClientProcessRecovery.ClientExecutable(installation));
    }

    [Fact]
    public void NoUserSessionDoesNotStartAClientInTheServiceSession()
    {
        Assert.False(ClientProcessRecovery.RestoreIfMissing(null,
            _ => throw new InvalidOperationException(), _ => throw new InvalidOperationException()));
        Assert.False(ClientProcessRecovery.RestoreIfMissing(0,
            _ => throw new InvalidOperationException(), _ => throw new InvalidOperationException()));
    }

    [Fact]
    public void MissingClientIsRestoredOnceInTheSameSession()
    {
        var running = false;
        var starts = new List<uint>();
        bool Restore() => ClientProcessRecovery.RestoreIfMissing(7, _ => running, session =>
        {
            starts.Add(session);
            running = true;
        });
        Assert.True(Restore());
        Assert.False(Restore());
        Assert.Equal(new uint[] { 7 }, starts);
        running = false;
        Assert.True(Restore());
        Assert.Equal(new uint[] { 7, 7 }, starts);
    }

    [Fact]
    public void FailedLaunchIsNotReportedAsSuccessfulRecovery()
    {
        Assert.Throws<InvalidOperationException>(() => ClientProcessRecovery.RestoreIfMissing(7,
            _ => false, _ => throw new InvalidOperationException("launch failed")));
    }
}
