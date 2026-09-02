namespace GameClub.Client.Infrastructure;

public sealed class DeviceEnrollmentPendingException : Exception
{
    public DeviceEnrollmentPendingException()
        : base("Workstation is waiting for administrator assignment")
    {
    }
}

public sealed class DeviceEnrollmentDisabledException : Exception
{
    public DeviceEnrollmentDisabledException()
        : base("Workstation is disabled")
    {
    }
}

public sealed class DeviceEnrollmentRejectedException : Exception
{
    public DeviceEnrollmentRejectedException()
        : base("This installation is already assigned to another workstation")
    {
    }
}
