namespace GameClub.Client.Windows;

internal static class ClientProcessRecovery
{
    public static string ClientExecutable(string installationDirectory) =>
        Path.Combine(installationDirectory, "HubShell.exe");

    public static bool RestoreIfMissing(uint? sessionId, Func<uint, bool> isRunning, Action<uint> launch)
    {
        if (sessionId is not uint session || session == 0 || isRunning(session))
        {
            return false;
        }
        launch(session);
        return true;
    }
}
