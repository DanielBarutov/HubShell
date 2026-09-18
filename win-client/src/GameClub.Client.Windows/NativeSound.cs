using System.Runtime.InteropServices;
using System.Text;

namespace GameClub.Client.Windows;

internal static class NativeSound
{
    private const uint SoundAsync = 0x0001;
    private const uint SoundFilename = 0x00020000;

    public static void PlayStandard() => MessageBeep(0x00000040);

    public static void PlayCustom(string path)
    {
        if (path.EndsWith(".wav", StringComparison.OrdinalIgnoreCase))
        {
            PlaySound(path, IntPtr.Zero, SoundAsync | SoundFilename);
            return;
        }

        _ = Task.Run(() =>
        {
            const string alias = "hubshell_time_notification";
            var escaped = path.Replace("\"", "\\\"", StringComparison.Ordinal);
            mciSendString($"close {alias}", null, 0, IntPtr.Zero);
            mciSendString($"open \"{escaped}\" type mpegvideo alias {alias}", null, 0, IntPtr.Zero);
            mciSendString($"play {alias} wait", null, 0, IntPtr.Zero);
            mciSendString($"close {alias}", null, 0, IntPtr.Zero);
        });
    }

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool MessageBeep(uint type);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PlaySound(string sound, IntPtr module, uint flags);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    private static extern uint mciSendString(
        string command,
        StringBuilder? returnValue,
        uint returnLength,
        IntPtr callback);
}
