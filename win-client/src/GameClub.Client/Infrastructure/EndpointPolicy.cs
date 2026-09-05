using System.Net;
using System.Net.Sockets;

namespace GameClub.Client.Infrastructure;

public static class EndpointPolicy
{
    public static Uri GetEnvironmentEndpoint(
        string environmentVariable,
        string fallback,
        string environment)
    {
        var configured = Environment.GetEnvironmentVariable(environmentVariable);
        var value = string.IsNullOrWhiteSpace(configured) ? fallback : configured.Trim();
        if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
        {
            throw new InvalidOperationException($"{environmentVariable} must be an absolute URI");
        }

        return Validate(endpoint, environmentVariable, environment);
    }

    public static Uri Validate(Uri endpoint, string endpointName, string environment)
    {
        if (!string.Equals(endpoint.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
            && !string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"{endpointName} must use http or https");
        }

        if (string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return endpoint;
        }

        if (IsPrivateNetwork(endpoint))
        {
            return endpoint;
        }

        throw new InvalidOperationException(
            $"{endpointName} must use HTTPS outside a private local network");
    }

    private static bool IsPrivateNetwork(Uri endpoint)
    {
        if (endpoint.IsLoopback)
        {
            return true;
        }

        if (!IPAddress.TryParse(endpoint.Host, out var address)
            || address.AddressFamily != AddressFamily.InterNetwork)
        {
            return false;
        }

        var bytes = address.GetAddressBytes();
        return bytes[0] == 10
            || (bytes[0] == 172 && bytes[1] is >= 16 and <= 31)
            || (bytes[0] == 192 && bytes[1] == 168);
    }
}
