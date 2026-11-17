namespace GameClub.Client.Domain;

public sealed record WorkstationHeartbeatSnapshot(
    string DeviceId,
    string GroupId,
    string Theme,
    string ManagerPasswordVerifier = "",
    WorkstationLockdownPolicySnapshot? LockdownPolicy = null,
    SessionSnapshot? SessionSnapshot = null,
    string WorkstationName = "",
    DateTimeOffset? ReservationStartsAt = null,
    DateTimeOffset? ReservationEndsAt = null);


public sealed record WorkstationReservationWindow(DateTimeOffset StartsAt, DateTimeOffset EndsAt)
{
    public bool RequiresStop(DateTimeOffset activatedAt, DateTimeOffset now) =>
        activatedAt < StartsAt && now >= StartsAt && now < EndsAt;
}
