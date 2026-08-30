using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

public interface IWorkstationPowerController
{
    CommandExecutionResult ScheduleRestart();
}
