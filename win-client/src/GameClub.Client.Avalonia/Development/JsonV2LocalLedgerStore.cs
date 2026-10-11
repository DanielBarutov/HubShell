using System.Text.Json;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Avalonia.Development;

/// <summary>
/// Хранилище в открытом виде только для ручной проверки V2 в Linux. Production
/// Windows использует ProtectedV2LocalLedgerStore с DPAPI. Этот адаптер нельзя
/// поставлять как границу хранения Windows-клиента.
/// </summary>
public sealed class JsonV2LocalLedgerStore : IV2LocalLedgerStore
{
    private readonly string _path;
    private readonly string _temporaryPath;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web);

    public JsonV2LocalLedgerStore(string? path = null)
    {
        _path = path
            ?? Environment.GetEnvironmentVariable("GAMECLUB_V2_DEV_LEDGER_PATH")
            ?? Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "GameClub",
                "v2-linux-ledger.json");
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
            var content = await File.ReadAllTextAsync(_path, cancellationToken);
            return JsonSerializer.Deserialize<V2LocalLedgerStorageSnapshot>(content, _jsonOptions)
                ?? throw new InvalidDataException("V2 Linux ledger is empty");
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
            await using (var stream = new FileStream(
                _temporaryPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 4096,
                options: FileOptions.WriteThrough))
            {
                await JsonSerializer.SerializeAsync(stream, snapshot, _jsonOptions, cancellationToken);
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
}
