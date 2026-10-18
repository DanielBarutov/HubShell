using System.Runtime.InteropServices;
using Grpc.Core;

namespace GameClub.Client.Application;

/// <summary>
/// Минимальный локальный журнал клиента для диагностики запуска и авторизации.
/// Он не заменяет серверное журналирование и намеренно не принимает секреты.
/// </summary>
public static class ClientLog
{
    private const long MaxFileBytes = 2 * 1024 * 1024;
    private static readonly object Sync = new();
    private static string? _path;
    private static bool _initialized;

    public static string FilePath
    {
        get
        {
            lock (Sync)
            {
                return _path ?? ResolvePath();
            }
        }
    }

    public static void Initialize(string component)
    {
        lock (Sync)
        {
            if (_initialized)
            {
                return;
            }

            _path = ResolvePath();
            _initialized = true;
            WriteLocked(
                "INFO",
                "startup",
                $"client started component={Sanitize(component)} pid={Environment.ProcessId} " +
                $"os={Sanitize(RuntimeInformation.OSDescription)} runtime={Sanitize(RuntimeInformation.FrameworkDescription)} " +
                $"base={Sanitize(AppContext.BaseDirectory)}");
        }
    }

    public static void Info(string category, string message) => Write("INFO", category, message);

    public static void Warning(string category, string message) => Write("WARN", category, message);

    public static void Error(string category, string message) => Write("ERROR", category, message);

    public static void Exception(string category, Exception error, string message)
    {
        var details = error is RpcException rpc
            ? $"type={error.GetType().Name} status={rpc.StatusCode} detail={Sanitize(rpc.Status.Detail)}"
            : $"type={error.GetType().Name} message={Sanitize(error.Message)}";
        Write("ERROR", category, $"{message} {details}");
    }

    public static void RpcFailure(string category, RpcException error, string operation) =>
        Exception(category, error, $"operation={Sanitize(operation)}");

    private static void Write(string level, string category, string message)
    {
        lock (Sync)
        {
            if (!_initialized)
            {
                return;
            }

            _path ??= ResolvePath();
            WriteLocked(level, category, message);
        }
    }

    private static void WriteLocked(string level, string category, string message)
    {
        try
        {
            var path = _path ?? ResolvePath();
            var directory = Path.GetDirectoryName(path);
            if (!string.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }

            RotateIfNeeded(path);
            var line = $"{DateTimeOffset.UtcNow:O} level={level} category={Sanitize(category)} " +
                       $"thread={Environment.CurrentManagedThreadId} {Sanitize(message)}{Environment.NewLine}";
            File.AppendAllText(path, line);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ArgumentException)
        {
            // Диагностика не должна ломать запуск клиента, если каталог недоступен.
            try
            {
                Console.Error.WriteLine($"HubShell client log unavailable: {error.GetType().Name}");
            }
            catch
            {
                // В том числе консоль может отсутствовать у собранного WinExe.
            }
        }
    }

    private static void RotateIfNeeded(string path)
    {
        if (!File.Exists(path) || new FileInfo(path).Length < MaxFileBytes)
        {
            return;
        }

        var backup = path + ".1";
        try
        {
            File.Delete(backup);
            File.Move(path, backup);
        }
        catch (IOException)
        {
            // Текущий файл всё равно можно дописать, если ротация временно занята.
        }
    }

    private static string ResolvePath()
    {
        var configured = Environment.GetEnvironmentVariable("GAMECLUB_CLIENT_LOG_PATH")?.Trim();
        if (!string.IsNullOrWhiteSpace(configured))
        {
            try
            {
                return Path.GetFullPath(configured);
            }
            catch (ArgumentException)
            {
                // Ниже будет использован безопасный путь по умолчанию.
            }
        }

        var localApplicationData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        if (string.IsNullOrWhiteSpace(localApplicationData))
        {
            localApplicationData = AppContext.BaseDirectory;
        }

        return Path.Combine(localApplicationData, "HubShell", "logs", "client.log");
    }

    private static string Sanitize(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "-";
        }

        var normalized = value.Replace('\r', ' ').Replace('\n', ' ').Trim();
        foreach (var marker in new[] { "password=", "token=", "authorization=", "bearer " })
        {
            var start = normalized.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (start >= 0)
            {
                var end = normalized.IndexOf(' ', start + marker.Length);
                normalized = normalized[..start] + marker + "<redacted>" +
                    (end >= 0 ? normalized[end..] : string.Empty);
            }
        }

        return normalized.Length <= 800 ? normalized : normalized[..800] + "...";
    }
}
