using GameClub.Client.Windows;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class AccessGateKeyboardGuardTests
{
    [Theory]
    [InlineData(0x5B, 0x44)]
    [InlineData(0x5C, 0x52)]
    public void WindowsChordsAndTheirReleaseAreSuppressedOnlyWhileLocked(uint windowsKey, uint letter)
    {
        var guard = new AccessGateKeyboardGuard();
        Assert.False(guard.ShouldSuppress(true, true, letter));
        Assert.True(guard.ShouldSuppress(true, true, windowsKey));
        Assert.True(guard.ShouldSuppress(true, true, letter));
        Assert.True(guard.ShouldSuppress(true, false, letter));
        Assert.True(guard.ShouldSuppress(true, false, windowsKey));
        Assert.False(guard.ShouldSuppress(true, true, letter));
        Assert.False(guard.ShouldSuppress(false, true, windowsKey));
        Assert.False(guard.ShouldSuppress(false, true, letter));
    }

    [Fact]
    public void MaintenanceOrUserModeClearsHeldWindowsStateAndLeavesManagerShortcutUntouched()
    {
        var guard = new AccessGateKeyboardGuard();
        Assert.True(guard.ShouldSuppress(true, true, 0x5B));
        Assert.False(guard.ShouldSuppress(false, true, 0x52));
        Assert.False(guard.ShouldSuppress(true, true, 0x52));
        Assert.False(guard.ShouldSuppress(true, true, 0x11)); // Ctrl
        Assert.False(guard.ShouldSuppress(true, true, 0x12)); // Alt
        Assert.False(guard.ShouldSuppress(true, true, 0x50)); // P
        Assert.False(guard.ShouldSuppress(true, true, 0x2E)); // Delete
    }
}
