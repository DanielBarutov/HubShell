namespace HubShell.SteamGuest.Agent;

public static class EnvironmentFile
{
    public static void LoadUnsetValues(string directory)
    {
        var path = Path.Combine(directory, ".env");
        if (!File.Exists(path))
        {
            return;
        }

        foreach (var line in File.ReadLines(path))
        {
            var value = line.Trim();
            if (value.Length == 0 || value.StartsWith('#'))
            {
                continue;
            }

            var separator = value.IndexOf('=');
            if (separator <= 0)
            {
                continue;
            }

            var key = value[..separator].Trim();
            var configuredValue = value[(separator + 1)..].Trim().Trim('"');
            if (key.Length == 0 || configuredValue.Length == 0 || Environment.GetEnvironmentVariable(key) is not null)
            {
                continue;
            }
            Environment.SetEnvironmentVariable(key, configuredValue);
        }
    }
}
