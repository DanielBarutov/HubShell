using System.Net.NetworkInformation;

namespace GameClub.Client.Infrastructure;

public static class MacAddressProvider
{
    public static IReadOnlyList<string> GetActiveMacAddresses()
    {
        return NetworkInterface.GetAllNetworkInterfaces()
            .Where(networkInterface =>
                networkInterface.OperationalStatus == OperationalStatus.Up
                && networkInterface.NetworkInterfaceType != NetworkInterfaceType.Loopback)
            .Select(networkInterface => networkInterface.GetPhysicalAddress().GetAddressBytes())
            .Where(bytes => bytes.Length == 6 && bytes.Any(byteValue => byteValue != 0))
            .Select(Format)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string Format(byte[] bytes) =>
        string.Join(":", bytes.Select(byteValue => byteValue.ToString("X2")));
}
