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

    private static readonly Lazy<IReadOnlyDictionary<string, string>> FileSettings = new(
        () => LoadConfiguration(Path.Combine(AppContext.BaseDirectory, "server.ini")));

    public static Uri GrpcAddress => ResolveAddress(
        "GAMECLUB_GRPC_ADDRESS",
        "GameClubGrpcAddress",
        DefaultGrpcAddress);

    public static Uri? V2EventsHttpAddress
    {
        get
        {
            var value = ReadRuntimeOverride("GAMECLUB_V2_EVENTS_HTTP_ADDRESS")
                ?? ReadFileSetting("V2EventsHttpAddress")
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
            ?? ReadFileSetting("V2SnapshotPublicKeys")
            ?? ReadMetadata("GameClubV2SnapshotPublicKeys")
            ?? string.Empty);

    private static Uri ResolveAddress(
        string environmentVariable,
        string metadataKey,
        string fallback)
    {
        var value = ReadRuntimeOverride(environmentVariable)
            ?? ReadFileSetting("GrpcAddress")
            ?? ReadMetadata(metadataKey)
            ?? fallback;
        if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
        {
            throw new InvalidOperationException($"{metadataKey} must be an absolute URI");
        }

        return EndpointPolicy.Validate(endpoint, metadataKey, EnvironmentName);
    }

    private static string? ReadFileSetting(string key) =>
        FileSettings.Value.TryGetValue(key, out var value) ? value : null;

    internal static IReadOnlyDictionary<string, string> LoadConfiguration(string path)
    {
        var settings = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(path))
        {
            return settings;
        }
        foreach (var rawLine in File.ReadLines(path))
        {
            var line = rawLine.Trim();
            if (line.Length == 0 || line.StartsWith(';') || line.StartsWith('#'))
            {
                continue;
            }
            var separator = line.IndexOf('=');
            if (separator <= 0)
            {
                throw new InvalidOperationException("server.ini: expected key=value");
            }
            var key = line[..separator].Trim();
            var value = line[(separator + 1)..].Trim();
            if (!new[] { "GrpcAddress", "V2EventsHttpAddress", "V2SnapshotPublicKeys" }
                .Contains(key, StringComparer.OrdinalIgnoreCase) || !settings.TryAdd(key, value))
            {
                throw new InvalidOperationException($"server.ini: unknown or repeated key {key}");
            }
            if (key.EndsWith("Address", StringComparison.OrdinalIgnoreCase) && value.Length > 0)
            {
                if (!Uri.TryCreate(value, UriKind.Absolute, out var endpoint))
                {
                    throw new InvalidOperationException($"server.ini: {key} must be an absolute URI");
                }
                EndpointPolicy.Validate(endpoint, key, EnvironmentName);
            }
            if (key.Equals("GrpcAddress", StringComparison.OrdinalIgnoreCase) && value.Length == 0)
            {
                throw new InvalidOperationException("server.ini: GrpcAddress is required");
            }
        }
        if (!settings.ContainsKey("GrpcAddress"))
        {
            throw new InvalidOperationException("server.ini: GrpcAddress is required");
        }
        return settings;
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
