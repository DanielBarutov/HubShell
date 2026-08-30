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

        var isDevelopment = string.Equals(environment.Trim(), "dev", StringComparison.OrdinalIgnoreCase);
        if (isDevelopment && IsLoopback(endpoint))
        {
            return endpoint;
        }

        throw new InvalidOperationException(
            $"{endpointName} must use HTTPS outside dev loopback configuration");
    }

    private static bool IsLoopback(Uri endpoint) =>
        endpoint.IsLoopback
        && (endpoint.Port == -1 || endpoint.Port is 80 or 8000 or 50051);
}
