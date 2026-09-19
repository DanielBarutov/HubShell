using HubShell.SteamGuest.Agent;
using Xunit;

namespace HubShell.SteamGuest.Tests;

public sealed class EnvironmentFileTests
{
    [Fact(DisplayName = "Читает .env рядом с приложением и не заменяет системную настройку")]
    public void Читает_env_рядом_с_приложением_и_сохраняет_приоритет_системной_настройки()
    {
        const string fileValue = "from-file";
        const string processValue = "from-process";
        var directory = Path.Combine(Path.GetTempPath(), $"steam-guest-env-{Guid.NewGuid():N}");
        Directory.CreateDirectory(directory);
        File.WriteAllText(Path.Combine(directory, ".env"), "STEAM_GUEST_TEST_FILE=from-file\nSTEAM_GUEST_TEST_OVERRIDE=from-file\n");
        var originalFile = Environment.GetEnvironmentVariable("STEAM_GUEST_TEST_FILE");
        var originalOverride = Environment.GetEnvironmentVariable("STEAM_GUEST_TEST_OVERRIDE");
        try
        {
            Environment.SetEnvironmentVariable("STEAM_GUEST_TEST_FILE", null);
            Environment.SetEnvironmentVariable("STEAM_GUEST_TEST_OVERRIDE", processValue);

            EnvironmentFile.LoadUnsetValues(directory);

            Assert.Equal(fileValue, Environment.GetEnvironmentVariable("STEAM_GUEST_TEST_FILE"));
            Assert.Equal(processValue, Environment.GetEnvironmentVariable("STEAM_GUEST_TEST_OVERRIDE"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("STEAM_GUEST_TEST_FILE", originalFile);
            Environment.SetEnvironmentVariable("STEAM_GUEST_TEST_OVERRIDE", originalOverride);
            Directory.Delete(directory, recursive: true);
        }
    }
}
