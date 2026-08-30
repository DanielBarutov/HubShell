namespace GameClub.Client.Domain;

public sealed record WorkstationLockdownPolicySnapshot(
    string DeploymentMode,
    bool ShellEnabled,
    bool UserSelfLoginEnabled,
    bool LockAfterSession,
    bool RestartAfterSession,
    IReadOnlyList<string> HiddenDrives,
    bool BlockExternalStorage,
    bool DisableStartMenu,
    bool DisableDesktopSwitching,
    IReadOnlyList<string> BlockedWindowRules,
    IReadOnlyList<string> AllowedApplicationIds,
    int Version)
{
    public static WorkstationLockdownPolicySnapshot SafeDefault { get; } = new(
        "app_gate",
        ShellEnabled: true,
        UserSelfLoginEnabled: true,
        LockAfterSession: true,
        RestartAfterSession: true,
        HiddenDrives: Array.Empty<string>(),
        BlockExternalStorage: false,
        DisableStartMenu: false,
        DisableDesktopSwitching: false,
        BlockedWindowRules: Array.Empty<string>(),
        AllowedApplicationIds: Array.Empty<string>(),
        Version: 1);
}
