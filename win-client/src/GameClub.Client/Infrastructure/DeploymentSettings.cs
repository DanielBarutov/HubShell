using System.Reflection;

namespace GameClub.Client.Infrastructure;

public static class DeploymentSettings
{
    private const string DefaultEnvironment = "production";
    private const string DefaultAuthAddress = "https://api.gameclub.local:8100";
    private const string DefaultGrpcAddress = "https://api.gameclub.local:51051";

    public static string EnvironmentName =>
        ReadRuntimeOverride("GAMECLUB_ENVIRONMENT")
        ?? ReadMetadata("GameClubEnvironment")
        ?? DefaultEnvironment;

    public static Uri AuthAddress => ResolveAddress(
        "GAMECLUB_AUTH_ADDRESS",
        "GameClubAuthAddress",
        DefaultAuthAddress);

    public static Uri GrpcAddress => ResolveAddress(
        "GAMECLUB_GRPC_ADDRESS",
        "GameClubGrpcAddress",
        DefaultGrpcAddress);

    private static Uri ResolveAddress(
        string environmentVariable,
        string metadataKey,
        string fallback)
    {
        var value = ReadRuntimeOverride(environmentVariable)
            ?? ReadMetadata(metadataKey)
            ?? fallback;
        if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
        {
            throw new InvalidOperationException($"{metadataKey} must be an absolute URI");
        }

        return EndpointPolicy.Validate(endpoint, metadataKey, EnvironmentName);
    }

    private static string? ReadRuntimeOverride(string key)
    {
        var value = Environment.GetEnvironmentVariable(key)?.Trim();
        return string.IsNullOrWhiteSpace(value) ? null : value;
    }

    private static string? ReadMetadata(string key) =>
        Assembly.GetExecutingAssembly()
            .GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(attribute => string.Equals(attribute.Key, key, StringComparison.Ordinal))
            ?.Value;
}
