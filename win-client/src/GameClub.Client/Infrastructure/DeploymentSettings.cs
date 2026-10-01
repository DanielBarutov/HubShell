using System.Reflection;
using GameClub.Client.Application;

namespace GameClub.Client.Infrastructure;

public static class DeploymentSettings
{
    private const string DefaultEnvironment = "production";
    private const string DefaultGrpcAddress = "https://api.gameclub.local:51051";

    public static string EnvironmentName =>
        ReadRuntimeOverride("GAMECLUB_ENVIRONMENT")
        ?? ReadMetadata("GameClubEnvironment")
        ?? DefaultEnvironment;

    public static Uri GrpcAddress => ResolveAddress(
        "GAMECLUB_GRPC_ADDRESS",
        "GameClubGrpcAddress",
        DefaultGrpcAddress);

    public static Uri? V2EventsHttpAddress
    {
        get
        {
            var value = ReadRuntimeOverride("GAMECLUB_V2_EVENTS_HTTP_ADDRESS")
                ?? ReadMetadata("GameClubV2EventsHttpAddress");
            if (string.IsNullOrWhiteSpace(value))
            {
                return null;
            }
            if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
            {
                throw new InvalidOperationException(
                    "GAMECLUB_V2_EVENTS_HTTP_ADDRESS must be an absolute URI");
            }
            return EndpointPolicy.Validate(
                endpoint,
                "GAMECLUB_V2_EVENTS_HTTP_ADDRESS",
                EnvironmentName);
        }
    }

    public static IReadOnlyDictionary<string, string> V2SnapshotPublicKeys =>
        V2SnapshotPublicKeyRing.Parse(
            ReadRuntimeOverride("GAMECLUB_V2_SNAPSHOT_PUBLIC_KEYS")
            ?? ReadMetadata("GameClubV2SnapshotPublicKeys")
            ?? string.Empty);

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
