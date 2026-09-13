using System.Diagnostics;
using System.Runtime.Versioning;
using Avalonia;
using Avalonia.Controls;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Windows;

/// <summary>
/// Native desktop behavior for the Windows deployment only. Avalonia owns the
/// shared view while this adapter restores the previous access-gate/widget
/// modes and makes the compact widget recoverable through the Windows tray.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsClientWindowAdapter : IClientWindowAdapter
{
    private const double WidgetWidth = 390;
    private const double WidgetHeight = 700;
    private Window? _window;
    private NativeTrayIcon? _trayIcon;
    private bool _disposed;

    public void Attach(Window window)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _window = window;
        window.SystemDecorations = SystemDecorations.None;
        window.CanResize = false;

        var windowHandle = window.TryGetPlatformHandle()?.Handle ?? IntPtr.Zero;
        if (windowHandle == IntPtr.Zero)
        {
            Trace.TraceError("HubShell tray was not initialized: Avalonia did not expose a native window handle.");
            return;
        }

        try
        {
            _trayIcon = new NativeTrayIcon(windowHandle, RestoreFromTray, ExitFromTray);
        }
        catch (Exception error)
        {
            // A tray failure must not prevent the access gate from protecting
            // the station. Native Windows smoke validates the tray separately.
            Trace.TraceError($"HubShell tray initialization failed: {error}");
        }
    }

    public void ApplyWindowMode(bool accessGateVisible)
    {
        if (_disposed || _window is null)
        {
            return;
        }

        _window.SystemDecorations = SystemDecorations.None;
        _window.CanResize = false;
        _window.Topmost = true;

        if (accessGateVisible)
        {
            _window.WindowState = WindowState.FullScreen;
            return;
        }

        _window.WindowState = WindowState.Normal;
        _window.Width = WidgetWidth;
        _window.Height = WidgetHeight;
        PlaceWidgetNearRightEdge(_window);
    }

    public void HideToTray()
    {
        if (_disposed || _window is null || _window.WindowState == WindowState.FullScreen)
        {
            return;
        }

        _window.Hide();
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _trayIcon?.Dispose();
        _trayIcon = null;
        _window = null;
        _disposed = true;
    }

    private void RestoreFromTray()
    {
        if (_disposed || _window is null)
        {
            return;
        }

        _window.Show();
        _window.Activate();
    }

    private void ExitFromTray()
    {
        if (_disposed)
        {
            return;
        }

        _window?.Close();
    }

    private static void PlaceWidgetNearRightEdge(Window window)
    {
        var screen = window.Screens.ScreenFromWindow(window) ?? window.Screens.Primary;
        if (screen is null)
        {
            return;
        }

        var scale = screen.Scaling;
        var width = (int)Math.Ceiling(WidgetWidth * scale);
        var height = (int)Math.Ceiling(WidgetHeight * scale);
        var workArea = screen.WorkingArea;
        window.Position = new PixelPoint(
            workArea.X + Math.Max(18, workArea.Width - width - 18),
            workArea.Y + Math.Max(18, (workArea.Height - height) / 2));
    }
}
