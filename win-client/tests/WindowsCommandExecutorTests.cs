using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class WindowsCommandExecutorTests
{
    [Fact]
    public async Task DisplayLockLocksClientShellWithoutInvokingWindowsLogon()
    {
        var lockCalls = 0;
        var executor = new WindowsCommandExecutor(
            displayLockConsumer: () => lockCalls++);
        var command = new WorkstationCommandSnapshot(
            "command-1",
            "workstation-1",
            "display.lock",
            "{}",
            "lock-1",
            string.Empty,
            string.Empty,
            string.Empty);

        var result = await executor.ExecuteAsync(command);

        Assert.True(result.Success);
        Assert.Equal(1, lockCalls);
        Assert.Contains("оболочка", result.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task DisplayLockFailsClosedWhenClientShellIsNotConnected()
    {
        var executor = new WindowsCommandExecutor();
        var command = new WorkstationCommandSnapshot(
            "command-1",
            "workstation-1",
            "display.lock",
            "{}",
            "lock-1",
            string.Empty,
            string.Empty,
            string.Empty);

        var result = await executor.ExecuteAsync(command);

        Assert.False(result.Success);
        Assert.Contains("не подключена", result.Message, StringComparison.OrdinalIgnoreCase);
    }
}
