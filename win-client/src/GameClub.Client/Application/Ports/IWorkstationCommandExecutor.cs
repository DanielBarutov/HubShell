using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IWorkstationCommandExecutor
{
    Task<CommandExecutionResult> ExecuteAsync(
        WorkstationCommandSnapshot command,
        CancellationToken cancellationToken = default);
}
