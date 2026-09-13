namespace GameClub.Client.Avalonia.Hosting;

/// <summary>
/// Process startup selects the composition before Avalonia creates App.
/// The default remains the explicit loopback-only Linux developer host.
/// </summary>
public static class AvaloniaClientHostFactory
{
    private static Func<IClientHost>? _create;

    public static void Configure(Func<IClientHost> create)
    {
        ArgumentNullException.ThrowIfNull(create);
        _create = create;
    }

    public static IClientHost Create() => _create?.Invoke()
        ?? new Development.LocalBackendClientHost();
}
