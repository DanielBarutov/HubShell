using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using Avalonia.Threading;
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
    private IntPtr _foregroundHook;
    private readonly ForegroundCallback _foregroundCallback;
    private readonly KeyboardCallback _keyboardCallback;
    private readonly AccessGateKeyboardGuard _keyboardGuard = new();
    private IntPtr _keyboardHook;

    public WindowsClientWindowAdapter()
    {
        _foregroundCallback = OnForegroundChanged;
        _keyboardCallback = OnKeyboardEvent;
    }

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

        _foregroundHook = SetWinEventHook(3, 3, IntPtr.Zero, _foregroundCallback, 0, 0, 0);
        if (_foregroundHook == IntPtr.Zero)
        {
            StartupDiagnostics.Error("Desktop foreground tracking failed", new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
        }
        window.ShowActivated = false;
        UpdateKeyboardHook();
        try
        {
            _trayIcon = new NativeTrayIcon(windowHandle, RestoreFromTray);
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
        _window.Topmost = mode == ClientWindowMode.Locked;
        _windowMode = mode;
        UpdateKeyboardHook();

        if (mode == ClientWindowMode.Locked)
        {
            _window.MinHeight = 520;
            SetWindowContentCornerRadius(0);
            _window.Show();
            _window.WindowState = WindowState.FullScreen;
            _window.Activate();
            return;
        }

        if (mode == ClientWindowMode.Maintenance)
        {
            SetWindowContentCornerRadius(14);
            _window.WindowState = WindowState.Normal;
            _window.MinHeight = 520;
            _window.Width = 1120;
            _window.Height = 680;
            var maintenanceScreen = _window.Screens.ScreenFromWindow(_window) ?? _window.Screens.Primary;
            if (maintenanceScreen is not null)
            {
                _window.Position = new PixelPoint(
                    maintenanceScreen.WorkingArea.X + Math.Max(0, (maintenanceScreen.WorkingArea.Width - (int)(_window.Width * maintenanceScreen.Scaling)) / 2),
                    maintenanceScreen.WorkingArea.Y + Math.Max(0, (maintenanceScreen.WorkingArea.Height - (int)(_window.Height * maintenanceScreen.Scaling)) / 2));
            }
            _window.Show();
            _window.Activate();
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
        UpdateDesktopVisibility();
    }

    public void HideToTray()
    {
        if (_disposed || _window is null || _windowMode == ClientWindowMode.Locked)
        {
            return;
        }

        if (_windowMode == ClientWindowMode.Maintenance)
        {
            _window.Hide();
        }
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

        if (_foregroundHook != IntPtr.Zero)
        {
            UnhookWinEvent(_foregroundHook);
            _foregroundHook = IntPtr.Zero;
        }
        RemoveKeyboardHook();
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

        if (_windowMode == ClientWindowMode.User)
        {
            UpdateDesktopVisibility();
            return;
        }
        _window.Show();
        _window.Activate();
    }

    private void UpdateKeyboardHook()
    {
        if (_windowMode != ClientWindowMode.Locked)
        {
            RemoveKeyboardHook();
            return;
        }
        if (_keyboardHook != IntPtr.Zero)
        {
            return;
        }
        _keyboardHook = SetWindowsHookEx(13, _keyboardCallback, GetModuleHandle(null), 0);
        if (_keyboardHook == IntPtr.Zero)
        {
            StartupDiagnostics.Error("Access-gate keyboard hook failed",
                new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
        }
    }

    private void RemoveKeyboardHook()
    {
        if (_keyboardHook != IntPtr.Zero)
        {
            UnhookWindowsHookEx(_keyboardHook);
            _keyboardHook = IntPtr.Zero;
        }
        _keyboardGuard.Reset();
    }

    private IntPtr OnKeyboardEvent(int code, IntPtr message, IntPtr data)
    {
        if (code == 0)
        {
            var keyboardMessage = unchecked((uint)message.ToInt64());
            if (keyboardMessage is 0x100 or 0x101 or 0x104 or 0x105
                && _keyboardGuard.ShouldSuppress(_windowMode == ClientWindowMode.Locked,
                    keyboardMessage is 0x100 or 0x104, unchecked((uint)Marshal.ReadInt32(data))))
            {
                return new IntPtr(1);
            }
        }
        return CallNextHookEx(_keyboardHook, code, message, data);
    }

    private delegate IntPtr KeyboardCallback(int code, IntPtr message, IntPtr data);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int hookType, KeyboardCallback callback, IntPtr module, uint threadId);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string? moduleName);

    private void OnForegroundChanged(IntPtr hook, uint eventType, IntPtr hwnd, int objectId, int childId, uint threadId, uint time) =>
        Dispatcher.UIThread.Post(UpdateDesktopVisibility);

    private void UpdateDesktopVisibility()
    {
        if (_disposed || _window is null || _windowMode != ClientWindowMode.User)
        {
            return;
        }
        var foreground = GetForegroundWindow();
        if (foreground == IntPtr.Zero)
        {
            return;
        }
        GetWindowThreadProcessId(foreground, out var processId);
        var className = new StringBuilder(256);
        GetClassName(foreground, className, className.Capacity);
        var desktop = className.ToString() is "Progman" or "WorkerW";
        if (processId == Environment.ProcessId)
        {
            return;
        }
        if (desktop)
        {
            _window.Show();
            if (_window.WindowState == WindowState.Minimized)
            {
                _window.WindowState = WindowState.Normal;
            }
        }
        else
        {
            _window.Hide();
        }
    }

    private delegate void ForegroundCallback(IntPtr hook, uint eventType, IntPtr hwnd, int objectId, int childId, uint threadId, uint time);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWinEventHook(uint minimum, uint maximum, IntPtr module, ForegroundCallback callback, uint processId, uint threadId, uint flags);
    [DllImport("user32.dll")]
    private static extern bool UnhookWinEvent(IntPtr hook);
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder className, int maximum);

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
