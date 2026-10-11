using System.Diagnostics;
using System.Runtime.Versioning;
using Avalonia;
using Avalonia.Controls;
using GameClub.Client.Application.Ports;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using GameClub.Client.Presentation;

namespace GameClub.Client.Windows;

/// <summary>
/// Нативное поведение рабочего стола только для Windows-развёртывания. Avalonia
/// владеет общим представлением, а адаптер восстанавливает режимы access-gate и
/// виджета и позволяет вернуть компактное окно через трей Windows.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class WindowsClientWindowAdapter : IClientWindowAdapter, ITimeNotificationPresenter
{
    private const double WidgetWidth = 390;
    private const double WidgetHeight = 1000;
    private const double WidgetCornerRadius = 14;
    private Window? _window;
    private Border? _windowContentSurface;
    private NativeTrayIcon? _trayIcon;
    private ClientWindowMode _windowMode = ClientWindowMode.Locked;
    private bool _disposed;

    public bool UsesTransparentWindow => true;

    public void Attach(Window window)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        _window = window;
        _windowContentSurface = window.FindControl<Border>("WindowContentSurface");
        window.SystemDecorations = SystemDecorations.None;
        window.CanResize = false;
        window.Topmost = true;
        if (window.ActualTransparencyLevel != WindowTransparencyLevel.Transparent)
        {
            StartupDiagnostics.Info(
                $"Avalonia Windows transparency fallback: {window.ActualTransparencyLevel}");
        }

        var windowHandle = window.TryGetPlatformHandle()?.Handle ?? IntPtr.Zero;
        if (windowHandle == IntPtr.Zero)
        {
            Trace.TraceError("HubShell tray was not initialized: Avalonia did not expose a native window handle.");
            return;
        }

        try
        {
            _trayIcon = new NativeTrayIcon(windowHandle, RestoreFromTray, ExitFromTray);
            StartupDiagnostics.Info("Avalonia Windows tray initialized");
        }
        catch (Exception error)
        {
            // Ошибка трея не должна лишить станцию защиты access-gate.
            // Работу трея отдельно проверяют на Windows.
            Trace.TraceError($"HubShell tray initialization failed: {error}");
            StartupDiagnostics.Error("Avalonia Windows tray initialization failed", error);
        }
    }

    public void ApplyWindowMode(ClientWindowMode mode)
    {
        if (_disposed || _window is null)
        {
            return;
        }

        _window.SystemDecorations = SystemDecorations.None;
        _window.CanResize = false;
        _window.Topmost = true;
        _windowMode = mode;

        if (mode is ClientWindowMode.Locked or ClientWindowMode.Maintenance)
        {
            _window.MinHeight = 520;
            SetWindowContentCornerRadius(0);
            _window.WindowState = WindowState.FullScreen;
            return;
        }

        SetWindowContentCornerRadius(WidgetCornerRadius);
        _window.WindowState = WindowState.Normal;
        _window.Width = WidgetWidth;
        var widgetHeight = _window.DataContext is MainViewModel { IsGuestWidgetVisible: true } ? 700 : WidgetHeight;
        var screen = _window.Screens.ScreenFromWindow(_window) ?? _window.Screens.Primary;
        var availableHeight = screen is null ? widgetHeight : screen.WorkingArea.Height / screen.Scaling - 36;
        _window.MinHeight = Math.Min(520, Math.Max(0, availableHeight));
        _window.Height = Math.Clamp(availableHeight, _window.MinHeight, widgetHeight);
        PlaceWidgetNearRightEdge(_window);
    }

    public void HideToTray()
    {
        if (_disposed || _window is null || _windowMode == ClientWindowMode.Locked)
        {
            return;
        }

        _window.Hide();
    }

    public void Present(TimeNotificationCandidate candidate)
    {
        if (candidate.PlaySound)
        {
            if (candidate.Sound.Equals("custom", StringComparison.OrdinalIgnoreCase)
                && candidate.CustomSoundPath is not null
                && (candidate.CustomSoundPath.EndsWith(".wav", StringComparison.OrdinalIgnoreCase)
                    || candidate.CustomSoundPath.EndsWith(".mp3", StringComparison.OrdinalIgnoreCase))
                && File.Exists(candidate.CustomSoundPath))
            {
                NativeSound.PlayCustom(candidate.CustomSoundPath);
            }
            else
            {
                NativeSound.PlayStandard();
            }
        }

        if (candidate.ShowSystemNotification)
        {
            _trayIcon?.ShowBalloon("HubShell", candidate.Message);
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _trayIcon?.Dispose();
        _trayIcon = null;
        _windowContentSurface = null;
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
        var width = (int)Math.Ceiling(window.Width * scale);
        var height = (int)Math.Ceiling(window.Height * scale);
        var workArea = screen.WorkingArea;
        window.Position = new PixelPoint(
            workArea.X + Math.Max(18, workArea.Width - width - 18),
            workArea.Y + Math.Max(18, (workArea.Height - height) / 2));
    }

    private void SetWindowContentCornerRadius(double radius)
    {
        if (_windowContentSurface is not null)
        {
            _windowContentSurface.CornerRadius = new CornerRadius(radius);
        }
    }
}
