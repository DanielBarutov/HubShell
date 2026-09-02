using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Infrastructure;

public sealed class JsonlOfflineJournal : IOfflineJournal
{
    private readonly string _path;
    private readonly string _sequencePath;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web);

    public JsonlOfflineJournal(string? path = null)
    {
        _path = path ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "GameClub",
            "offline-journal.jsonl");
        _sequencePath = _path + ".sequence";
    }

    public async Task<long> NextSequenceAsync(
        string sessionId,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var state = await ReadSequenceStateAsync(cancellationToken);
            var stored = await ReadStoredOperationsAsync(cancellationToken);
            var journalMaximum = stored
                .Where(item => item.SessionId == sessionId)
                .Select(item => item.Sequence)
                .DefaultIfEmpty(0)
                .Max();
            return Math.Max(state.GetValueOrDefault(sessionId), journalMaximum) + 1;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AppendAsync(
        OfflineOperationSnapshot operation,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var stored = await ReadStoredOperationsAsync(cancellationToken);
            var duplicate = stored.FirstOrDefault(item =>
                item.SessionId == operation.SessionId
                && item.IdempotencyKey == operation.IdempotencyKey);
            if (duplicate is not null)
            {
                if (duplicate.Checksum != operation.Checksum)
                {
                    throw new InvalidOperationException("Offline idempotency key is already used");
                }
                return;
            }

            var state = await ReadSequenceStateAsync(cancellationToken);
            var previous = Math.Max(
                state.GetValueOrDefault(operation.SessionId),
                stored
                    .Where(item => item.SessionId == operation.SessionId)
                    .Select(item => item.Sequence)
                    .DefaultIfEmpty(0)
                    .Max());
            if (operation.Sequence != previous + 1)
            {
                throw new InvalidOperationException(
                    $"Offline sequence must be {previous + 1}, got {operation.Sequence}");
            }

            var directory = Path.GetDirectoryName(_path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            var encoded = Protect(JsonSerializer.Serialize(operation, _jsonOptions));
            await using var stream = new FileStream(
                _path,
                FileMode.Append,
                FileAccess.Write,
                FileShare.Read,
                bufferSize: 4096,
                options: FileOptions.WriteThrough);
            await using var writer = new StreamWriter(stream, Encoding.UTF8, 4096, leaveOpen: true);
            await writer.WriteLineAsync(encoded.AsMemory(), cancellationToken);
            await writer.FlushAsync(cancellationToken);
            await stream.FlushAsync(cancellationToken);
            stream.Flush(flushToDisk: true);
            state[operation.SessionId] = operation.Sequence;
            await WriteSequenceStateAsync(state, cancellationToken);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<IReadOnlyList<OfflineOperationSnapshot>> ReadPendingAsync(
        string sessionId,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            if (!File.Exists(_path))
            {
                return Array.Empty<OfflineOperationSnapshot>();
            }

            return (await ReadStoredOperationsAsync(cancellationToken))
                .Where(item => item is not null && item.SessionId == sessionId)
                .OrderBy(item => item.Sequence)
                .ToArray();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task AcknowledgeAsync(
        IReadOnlyCollection<string> operationIds,
        CancellationToken cancellationToken = default)
    {
        if (operationIds.Count == 0 || !File.Exists(_path))
        {
            return;
        }

        await _gate.WaitAsync(cancellationToken);
        try
        {
            var acknowledged = operationIds.ToHashSet(StringComparer.Ordinal);
            var lines = await File.ReadAllLinesAsync(_path, cancellationToken);
            var remaining = lines
                .Where(line => !string.IsNullOrWhiteSpace(line))
                .Select(line =>
                {
                    var operation = JsonSerializer.Deserialize<OfflineOperationSnapshot>(
                        Unprotect(line),
                        _jsonOptions) ?? throw new InvalidDataException("Offline journal entry is empty");
                    return (line, operation);
                })
                .Where(item => !acknowledged.Contains(item.operation.Id))
                .Select(item => item.line)
                .ToArray();
            var temporaryPath = _path + ".tmp";
            await File.WriteAllLinesAsync(temporaryPath, remaining, Encoding.UTF8, cancellationToken);
            File.Move(temporaryPath, _path, overwrite: true);
        }
        finally
        {
            _gate.Release();
        }
    }

    private static string Protect(string value)
    {
        var bytes = ProtectedData.Protect(
            Encoding.UTF8.GetBytes(value),
            optionalEntropy: null,
            scope: DataProtectionScope.CurrentUser);
        return Convert.ToBase64String(bytes);
    }

    private static string Unprotect(string value)
    {
        var bytes = ProtectedData.Unprotect(
            Convert.FromBase64String(value),
            optionalEntropy: null,
            scope: DataProtectionScope.CurrentUser);
        return Encoding.UTF8.GetString(bytes);
    }

    private async Task<IReadOnlyList<OfflineOperationSnapshot>> ReadStoredOperationsAsync(
        CancellationToken cancellationToken)
    {
        if (!File.Exists(_path))
        {
            return Array.Empty<OfflineOperationSnapshot>();
        }

        var lines = await File.ReadAllLinesAsync(_path, cancellationToken);
        return lines
            .Where(line => !string.IsNullOrWhiteSpace(line))
            .Select(line => JsonSerializer.Deserialize<OfflineOperationSnapshot>(
                Unprotect(line),
                _jsonOptions) ?? throw new InvalidDataException("Offline journal entry is empty"))
            .ToArray();
    }

    private async Task<Dictionary<string, long>> ReadSequenceStateAsync(
        CancellationToken cancellationToken)
    {
        if (!File.Exists(_sequencePath))
        {
            return new Dictionary<string, long>(StringComparer.Ordinal);
        }

        var encoded = await File.ReadAllTextAsync(_sequencePath, cancellationToken);
        var state = JsonSerializer.Deserialize<Dictionary<string, long>>(
            Unprotect(encoded),
            _jsonOptions);
        return state ?? new Dictionary<string, long>(StringComparer.Ordinal);
    }

    private async Task WriteSequenceStateAsync(
        IReadOnlyDictionary<string, long> state,
        CancellationToken cancellationToken)
    {
        var directory = Path.GetDirectoryName(_sequencePath);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }
        var temporaryPath = _sequencePath + ".tmp";
        var encoded = Protect(JsonSerializer.Serialize(state, _jsonOptions));
        await using (var stream = new FileStream(
            temporaryPath,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            bufferSize: 4096,
            options: FileOptions.WriteThrough))
        await using (var writer = new StreamWriter(stream, Encoding.UTF8, 4096, leaveOpen: true))
        {
            await writer.WriteAsync(encoded.AsMemory(), cancellationToken);
            await writer.FlushAsync(cancellationToken);
            await stream.FlushAsync(cancellationToken);
            stream.Flush(flushToDisk: true);
        }
        File.Move(temporaryPath, _sequencePath, overwrite: true);
    }
}
