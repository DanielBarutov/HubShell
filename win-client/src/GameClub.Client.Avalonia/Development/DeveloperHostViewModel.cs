using GameClub.Client.Application;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Avalonia.Development;

public sealed class DeveloperHostViewModel
{
    private readonly AccessGateCoordinator _accessGate = new(
        new EnvironmentAccessCredentialVerifier("dev"));

    public string Status =>
        $"Ядро загружено. Начальное состояние доступа: {_accessGate.Snapshot.Mode}. Подключение к backend не запускалось.";

    public string EvidenceBoundary =>
        "Это окно Linux подтверждает только работу Avalonia developer-host. Оно не подтверждает работу трея, DPAPI, перезапуска, автозапуска, kiosk policy и Windows runtime.";
}
