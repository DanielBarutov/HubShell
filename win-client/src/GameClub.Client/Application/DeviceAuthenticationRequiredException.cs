namespace GameClub.Client.Application;

public sealed class DeviceAuthenticationRequiredException : Exception
{
    public DeviceAuthenticationRequiredException(Exception innerException)
        : base("Device authorization is required", innerException)
    {
    }
}
