using System.ComponentModel;
using System.Runtime.InteropServices;

namespace GameClub.Client.Infrastructure;

internal sealed class NativeTrayIcon : IDisposable
{
    private const int GwlWndProc = -4;
    private const uint NifIcon = 0x00000002;
    private const uint NifMessage = 0x00000001;
    private const uint NifTip = 0x00000004;
    private const uint NimAdd = 0x00000000;
    private const uint NimDelete = 0x00000002;
    private const uint WmApp = 0x00008000;
    private const uint WmLButtonDoubleClick = 0x00000203;
    private const uint WmNull = 0x00000000;
    private const uint WmRButtonUp = 0x00000205;
    private const uint WmTrayIcon = WmApp + 0x44;
    private const uint MfString = 0x00000000;
    private const uint TpmNonotify = 0x00000080;
    private const uint TpmRetcmd = 0x00000100;
    private const uint TpmRightButton = 0x00000002;
    private const uint TrayShowCommand = 1;
    private const uint TrayExitCommand = 2;
    private static readonly IntPtr IdiApplication = new(32512);

    private readonly Action _onExit;
    private readonly Action _onRestore;
    private readonly IntPtr _windowHandle;
    private readonly WindowProc _windowProc;
    private readonly IntPtr _previousWindowProc;
    private bool _disposed;

    public NativeTrayIcon(IntPtr windowHandle, Action onRestore, Action onExit)
    {
        if (windowHandle == IntPtr.Zero)
        {
            throw new ArgumentException("Window handle is required.", nameof(windowHandle));
        }

        _windowHandle = windowHandle;
        _onRestore = onRestore;
        _onExit = onExit;
        _windowProc = HandleWindowMessage;
        _previousWindowProc = SetWindowLongPtr(
            _windowHandle,
            GwlWndProc,
            Marshal.GetFunctionPointerForDelegate(_windowProc));
        if (_previousWindowProc == IntPtr.Zero)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Не удалось подключить обработчик tray-сообщений.");
        }

        try
        {
            var data = CreateNotifyIconData();
            if (!Shell_NotifyIcon(NimAdd, ref data))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Не удалось создать иконку GameClub в tray.");
            }
        }
        catch
        {
            RestoreWindowProcedure();
            throw;
        }
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        var data = CreateNotifyIconData();
        Shell_NotifyIcon(NimDelete, ref data);
        RestoreWindowProcedure();
        _disposed = true;
        GC.KeepAlive(_windowProc);
    }

    private IntPtr HandleWindowMessage(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam)
    {
        _ = wParam;
        if (message == WmTrayIcon)
        {
            var notification = unchecked((uint)lParam.ToInt64());
            if (notification == WmLButtonDoubleClick)
            {
                _onRestore();
                return IntPtr.Zero;
            }

            if (notification == WmRButtonUp)
            {
                ShowContextMenu();
                return IntPtr.Zero;
            }
        }

        return CallWindowProc(_previousWindowProc, hwnd, message, wParam, lParam);
    }

    private void ShowContextMenu()
    {
        var menu = CreatePopupMenu();
        if (menu == IntPtr.Zero)
        {
            return;
        }

        try
        {
            AppendMenu(menu, MfString, new UIntPtr(TrayShowCommand), "Показать");
            AppendMenu(menu, MfString, new UIntPtr(TrayExitCommand), "Выйти");
            if (!GetCursorPos(out var cursorPosition))
            {
                return;
            }

            SetForegroundWindow(_windowHandle);
            var command = TrackPopupMenu(
                menu,
                TpmRetcmd | TpmNonotify | TpmRightButton,
                cursorPosition.X,
                cursorPosition.Y,
                0,
                _windowHandle,
                IntPtr.Zero);
            PostMessage(_windowHandle, WmNull, IntPtr.Zero, IntPtr.Zero);

            if (command == TrayShowCommand)
            {
                _onRestore();
            }
            else if (command == TrayExitCommand)
            {
                _onExit();
            }
        }
        finally
        {
            DestroyMenu(menu);
        }
    }

    private NotifyIconData CreateNotifyIconData() => new()
    {
        CbSize = (uint)Marshal.SizeOf<NotifyIconData>(),
        WindowHandle = _windowHandle,
        Id = 1,
        Flags = NifMessage | NifIcon | NifTip,
        CallbackMessage = WmTrayIcon,
        IconHandle = LoadIcon(IntPtr.Zero, IdiApplication),
        Tip = "GameClub",
        Info = string.Empty,
        InfoTitle = string.Empty,
    };

    private void RestoreWindowProcedure()
    {
        if (_previousWindowProc != IntPtr.Zero)
        {
            SetWindowLongPtr(_windowHandle, GwlWndProc, _previousWindowProc);
        }
    }

    private delegate IntPtr WindowProc(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NotifyIconData
    {
        public uint CbSize;
        public IntPtr WindowHandle;
        public uint Id;
        public uint Flags;
        public uint CallbackMessage;
        public IntPtr IconHandle;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string Tip;

        public uint State;
        public uint StateMask;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)]
        public string Info;

        public uint TimeoutOrVersion;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)]
        public string InfoTitle;

        public uint InfoFlags;
        public Guid GuidItem;
        public IntPtr BalloonIconHandle;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool Shell_NotifyIcon(uint message, ref NotifyIconData data);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadIcon(IntPtr instance, IntPtr resource);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreatePopupMenu();

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AppendMenu(IntPtr menu, uint flags, UIntPtr itemId, string text);

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint TrackPopupMenu(
        IntPtr menu,
        uint flags,
        int x,
        int y,
        int reserved,
        IntPtr owner,
        IntPtr reservedRect);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DestroyMenu(IntPtr menu);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetCursorPos(out Point point);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr windowHandle);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PostMessage(IntPtr windowHandle, uint message, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", EntryPoint = "CallWindowProcW", SetLastError = true)]
    private static extern IntPtr CallWindowProc(
        IntPtr previousWindowProc,
        IntPtr hwnd,
        uint message,
        IntPtr wParam,
        IntPtr lParam);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr64(IntPtr hwnd, int index, IntPtr newValue);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongW", SetLastError = true)]
    private static extern IntPtr SetWindowLong32(IntPtr hwnd, int index, IntPtr newValue);

    private static IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr newValue) =>
        IntPtr.Size == 8
            ? SetWindowLongPtr64(hwnd, index, newValue)
            : SetWindowLong32(hwnd, index, newValue);
}
