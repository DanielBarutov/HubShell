namespace GameClub.Client.Avalonia.Hosting;

/// <summary>
/// При запуске процесса composition выбирается до создания App в Avalonia.
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
        ?? new Development.V2LinuxClientHost();
}
