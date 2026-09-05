namespace GameClub.Client.Infrastructure;

internal static class StartupDiagnostics
{
    private static readonly object Sync = new();
    private static readonly string LogPath = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "GameClub",
        "startup.log");

    public static void Info(string message) => Write("INFO", message);

    public static void Error(string stage, Exception error) => Write(
        "ERROR",
        $"{stage}: {error.GetType().FullName}: {error.Message}{Environment.NewLine}{error.StackTrace}");

    private static void Write(string level, string message)
    {
        try
        {
            var directory = System.IO.Path.GetDirectoryName(LogPath);
            if (string.IsNullOrWhiteSpace(directory))
            {
                return;
            }

            lock (Sync)
            {
                Directory.CreateDirectory(directory);
                File.AppendAllText(
                    LogPath,
                    $"{DateTimeOffset.Now:O} [{level}] {message}{Environment.NewLine}");
            }
        }
        catch
        {
            // Диагностика не должна становиться причиной падения приложения.
        }
    }
}
