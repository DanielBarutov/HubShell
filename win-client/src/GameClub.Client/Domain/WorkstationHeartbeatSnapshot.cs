namespace GameClub.Client.Domain;

public sealed record WorkstationHeartbeatSnapshot(
    string DeviceId,
    string GroupId,
    string Theme,
    string ManagerPasswordVerifier = "",
    WorkstationLockdownPolicySnapshot? LockdownPolicy = null,
    SessionSnapshot? SessionSnapshot = null);
