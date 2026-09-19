using HubShell.SteamGuest.Agent;
using HubShell.SteamGuest.Core;

try
{
    EnvironmentFile.LoadUnsetValues(AppContext.BaseDirectory);
    var serverUrl = RequiredUri("HUBSHELL_STEAM_SERVER_URL");
    var stationId = Required("HUBSHELL_STEAM_STATION_ID");
    var stationKey = Required("HUBSHELL_STEAM_STATION_KEY");
    var steamPath = Environment.GetEnvironmentVariable("HUBSHELL_STEAM_EXE")
        ?? @"C:\Program Files (x86)\Steam\steam.exe";
    var agent = new GuestSteamAgent(
        new GuestAccountApi(serverUrl, stationKey),
        new SteamProcessLauncher(steamPath),
        new NamedPipeSessionStopSignal());
    await agent.RunAsync(stationId, stationKey);
}
catch (GuestAccountUnavailableException)
{
    Environment.ExitCode = 20;
}
catch (Exception)
{
    // Не записываем исключение: в нём не должно оказаться данных аккаунта.
    Environment.ExitCode = 1;
}

static string Required(string name) => Environment.GetEnvironmentVariable(name) is { Length: > 0 } value
    ? value
    : throw new InvalidOperationException($"Не задана переменная {name}.");

static Uri RequiredUri(string name) => Uri.TryCreate(Required(name), UriKind.Absolute, out var value)
    ? value
    : throw new InvalidOperationException($"Переменная {name} должна содержать абсолютный адрес.");
