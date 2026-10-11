using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Windows;

/// <summary>
/// Выполняет небольшой явно заданный набор команд оператора V2. Здесь нет
/// шлюза сессий, поэтому V2-бинарник Windows не может создать, остановить или
/// тарифицировать старую серверную сессию.
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
            "display.lock" => LockClient(),
            "system.restart" => RestartWorkstation(),
            _ => new CommandExecutionResult(false, "Команда не поддерживается клиентом"),
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
