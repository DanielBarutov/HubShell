using GameClub.Client.Presentation;
using Avalonia.Controls;

namespace GameClub.Client.Avalonia.Hosting;

/// <summary>
/// Owns one client composition. The Avalonia window stays platform-neutral;
/// developer and Windows production hosts supply their own transports/adapters.
/// </summary>
public interface IClientHost : IAsyncDisposable
{
    MainViewModel ViewModel { get; }

    string WindowTitle { get; }

    string HostDisclaimer { get; }

    /// <summary>
    /// Optional native desktop behavior owned by the selected host. The Linux
    /// developer host deliberately leaves this null.
    /// </summary>
    IClientWindowAdapter? WindowAdapter { get; }

    Task StartAsync();
}

/// <summary>
/// Keeps platform-specific window and tray behavior out of the shared
/// access-gate/portal view. Implementations are attached only after Avalonia
/// creates a native window handle.
/// </summary>
public interface IClientWindowAdapter : IDisposable
{
    /// <summary>
    /// Requests a transparent native surface before the window opens. This is
    /// needed only when a platform adapter renders rounded outer corners.
    /// </summary>
    bool UsesTransparentWindow { get; }

    void Attach(Window window);

    void ApplyWindowMode(bool accessGateVisible);

    void HideToTray();
}
