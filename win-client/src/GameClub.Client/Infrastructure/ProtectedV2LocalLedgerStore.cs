using System.Runtime.Versioning;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Windows-реализация V2 local ledger. Один защищённый файл делает изменение
/// ledger и добавление события outbox неразделимыми при выключении питания.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ProtectedV2LocalLedgerStore : IV2LocalLedgerStore
{
    private readonly string _path;
    private readonly string _temporaryPath;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web);

    public ProtectedV2LocalLedgerStore(string? path = null)
    {
        _path = path ?? Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "GameClub",
            "v2-local-ledger.json");
        _temporaryPath = _path + ".tmp";
    }

    public async Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            RecoverInterruptedWrite();
            if (!File.Exists(_path))
            {
                return null;
            }
            var protectedContent = await File.ReadAllTextAsync(_path, cancellationToken);
            return JsonSerializer.Deserialize<V2LocalLedgerStorageSnapshot>(
                Unprotect(protectedContent),
                _jsonOptions)
                ?? throw new InvalidDataException("V2 local ledger is empty");
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task WriteAsync(
        V2LocalLedgerStorageSnapshot snapshot,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken);
        try
        {
            var directory = Path.GetDirectoryName(_path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }
            var protectedContent = Protect(JsonSerializer.Serialize(snapshot, _jsonOptions));
            await using (var stream = new FileStream(
                _temporaryPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 4096,
                options: FileOptions.WriteThrough))
            await using (var writer = new StreamWriter(stream, Encoding.UTF8, 4096, leaveOpen: true))
            {
                await writer.WriteAsync(protectedContent.AsMemory(), cancellationToken);
                await writer.FlushAsync(cancellationToken);
                await stream.FlushAsync(cancellationToken);
                stream.Flush(flushToDisk: true);
            }
            File.Move(_temporaryPath, _path, overwrite: true);
        }
        finally
        {
            _gate.Release();
        }
    }

    private void RecoverInterruptedWrite()
    {
        if (!File.Exists(_path) && File.Exists(_temporaryPath))
        {
            File.Move(_temporaryPath, _path);
        }
    }

    private static string Protect(string value) =>
        Convert.ToBase64String(ProtectedData.Protect(
            Encoding.UTF8.GetBytes(value),
            optionalEntropy: null,
            scope: DataProtectionScope.CurrentUser));

    private static string Unprotect(string value) =>
        Encoding.UTF8.GetString(ProtectedData.Unprotect(
            Convert.FromBase64String(value),
            optionalEntropy: null,
            scope: DataProtectionScope.CurrentUser));
}
