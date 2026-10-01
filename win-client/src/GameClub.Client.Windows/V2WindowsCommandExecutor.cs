using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Windows;

/// <summary>
/// Executes the explicitly small V2 operator-command vocabulary. It has no
/// session gateway, so an operator command cannot create, stop, or meter a
/// legacy server-owned session through the V2 Windows binary.
/// </summary>
public sealed class V2WindowsCommandExecutor : IWorkstationCommandExecutor
{
    private readonly IWorkstationPowerController _powerController;
    private readonly Action<string> _lockClient;

    public V2WindowsCommandExecutor(
        IWorkstationPowerController powerController,
        Action<string> lockClient)
    {
        _powerController = powerController;
        _lockClient = lockClient;
    }

    public Task<CommandExecutionResult> ExecuteAsync(
        WorkstationCommandSnapshot command,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return Task.FromResult(command.CommandType switch
        {
            "v2.display.lock" => LockClient(),
            "v2.system.restart" => RestartWorkstation(),
            _ => new CommandExecutionResult(false, "Команда не поддерживается V2-клиентом"),
        });
    }

    private CommandExecutionResult LockClient()
    {
        _lockClient("Оператор заблокировал это место");
        return new CommandExecutionResult(true, "Клиентская оболочка заблокирована");
    }

    private CommandExecutionResult RestartWorkstation()
    {
        _lockClient("Оператор перезапускает это место");
        return _powerController.ScheduleRestart();
    }
}
