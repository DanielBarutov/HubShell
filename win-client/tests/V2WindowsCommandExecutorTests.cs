using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Windows;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2WindowsCommandExecutorTests
{
    [Fact]
    public async Task ExecutesOnlyV2LockAndRestartCommands()
    {
        var power = new RecordingPowerController();
        var lockReasons = new List<string>();
        var executor = new V2WindowsCommandExecutor(power, lockReasons.Add);

        var legacy = await executor.ExecuteAsync(Command("session.stop"));
        var locked = await executor.ExecuteAsync(Command("v2.display.lock"));
        var restarted = await executor.ExecuteAsync(Command("v2.system.restart"));

        Assert.False(legacy.Success);
        Assert.True(locked.Success);
        Assert.True(restarted.Success);
        Assert.Equal(1, power.RestartCalls);
        Assert.Equal(
            ["Оператор заблокировал это место", "Оператор перезапускает это место"],
            lockReasons);
    }

    private static WorkstationCommandSnapshot Command(string commandType) => new(
        Id: "command-1",
        WorkstationId: "",
        CommandType: commandType,
        PayloadJson: "{}",
        IdempotencyKey: "idempotency-1",
        Status: "queued",
        AcknowledgementMessage: "",
        ExpiresAt: "");

    private sealed class RecordingPowerController : IWorkstationPowerController
    {
        public int RestartCalls { get; private set; }

        public CommandExecutionResult ScheduleRestart()
        {
            RestartCalls++;
            return new CommandExecutionResult(true, "Restart scheduled");
        }
    }
}
