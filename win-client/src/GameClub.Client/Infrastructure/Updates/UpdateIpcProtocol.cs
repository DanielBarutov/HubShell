using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace GameClub.Client.Infrastructure.Updates;

public sealed record UpdateIpcRequest(string Command, Guid DeploymentId, Guid RoundId);
public sealed record UpdateIpcStatus(
    [property: JsonRequired] string? DeviceId,
    [property: JsonRequired] string InstallationId,
    [property: JsonRequired] string ReleaseId,
    [property: JsonRequired] bool ActiveSession,
    [property: JsonRequired] int PendingFacts,
    [property: JsonRequired] bool Ready,
    [property: JsonRequired] bool Blocked,
    bool Closing = false, string? ErrorCode = null,
    [property: JsonRequired] Guid? SessionId = null,
    [property: JsonRequired] long LastSequence = 0,
    [property: JsonRequired] string? LastPayloadHash = null,
    [property: JsonRequired] int ProtocolVersion = 1);


public static class UpdateIpcProtocol
{
    public static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    public static string PipeName(string directory, int sessionId) => "HubShell.Updates."
        + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar).ToUpperInvariant())))[..16]
        + "." + sessionId;

    public static string ReleaseId(Assembly assembly)
    {
        var value = assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
            .FirstOrDefault(value => value.Key == "HubShellReleaseId")?.Value;
        return string.IsNullOrWhiteSpace(value) ? "development" : value;
    }
}

public sealed record ClientUpdateJournal(Guid DeploymentId, Guid RoundId, string ReleaseId,
    string ExecutableSha256, string Stage, bool Blocked, string? OldExecutableSha256 = null);

public sealed class ClientUpdateStateStore
{
    private readonly string _path;
    public ClientUpdateStateStore(string directory) => _path = Path.Combine(directory, ".client-update.json");

    public ClientUpdateJournal? Read()
    {
        if (!File.Exists(_path)) return null;
        if ((File.GetAttributes(_path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Update journal cannot be a link");
        if (new FileInfo(_path).Length > 16384) throw new InvalidDataException("Update journal is too large");
        var data = File.ReadAllBytes(_path);
        var value = JsonSerializer.Deserialize<ClientUpdateJournal>(data, UpdateIpcProtocol.Json)
            ?? throw new InvalidDataException("Invalid update journal");
        if ((value.Stage == "completed") != !value.Blocked
            || value.DeploymentId == Guid.Empty || value.RoundId == Guid.Empty
            || !Regex.IsMatch(value.ReleaseId ?? "", @"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\z")
            || !Regex.IsMatch(value.ExecutableSha256 ?? "", @"\A[a-f0-9]{64}\z")
            || value.Stage is not ("prepared" or "closing" or "backup_pending" or "replace_pending"
                or "verifying" or "installed" or "failed" or "rolled_back" or "completed"))
            throw new InvalidDataException("Incomplete update journal");
        return value;
    }

    public void Write(ClientUpdateJournal value)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(value, UpdateIpcProtocol.Json);
        var temporary = _path + ".new";
        if (File.Exists(temporary) && (File.GetAttributes(temporary) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Update journal temporary file cannot be a link");
        using (var file = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            file.Write(bytes);
            file.Flush(flushToDisk: true);
        }
        File.Move(temporary, _path, overwrite: true);
    }
}
