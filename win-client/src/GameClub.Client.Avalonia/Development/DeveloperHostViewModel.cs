using GameClub.Client.Application;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Avalonia.Development;

public sealed class DeveloperHostViewModel
{
    private readonly AccessGateCoordinator _accessGate = new(
        new EnvironmentAccessCredentialVerifier("dev"));

    public string Status =>
        $"Core loaded. Initial access state: {_accessGate.Snapshot.Mode}. No backend connection was started.";

    public string EvidenceBoundary =>
        "This Linux window proves only the Avalonia developer host. It does not prove Windows tray, DPAPI, restart, autostart, kiosk policy, or Windows runtime.";
}
