using System.ComponentModel;
using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;
using GameClub.Client.Infrastructure.Updates;

namespace GameClub.Client.Watchdog;

[SupportedOSPlatform("windows")]
internal sealed class WindowsUpdateGuiClient
{
    private readonly string _directory;
    public WindowsUpdateGuiClient(string directory) => _directory = Path.GetFullPath(directory);

    public async Task<UpdateIpcStatus> RequestAsync(int sessionId, UpdateIpcRequest request,
        CancellationToken cancellationToken)
    {
        if (sessionId <= 0) throw new InvalidOperationException("No interactive console session");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(15));
        await using var pipe = new NamedPipeClientStream(".", UpdateIpcProtocol.PipeName(_directory, sessionId),
            PipeDirection.InOut, PipeOptions.Asynchronous, TokenImpersonationLevel.Identification);
        await pipe.ConnectAsync(5000, timeout.Token);
        if (!GetNamedPipeServerProcessId(pipe.SafePipeHandle, out var processId))
            throw new Win32Exception(Marshal.GetLastWin32Error());
        using var process = Process.GetProcessById(checked((int)processId));
        if (process.SessionId != sessionId || !string.Equals(process.MainModule?.FileName,
                Path.Combine(_directory, "HubShell.exe"), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Update pipe does not belong to the installed GUI");
        using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, leaveOpen: true);
        using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, leaveOpen: true);
        await writer.WriteLineAsync(JsonSerializer.Serialize(request, UpdateIpcProtocol.Json).AsMemory(), timeout.Token);
        await writer.FlushAsync(timeout.Token);
        var line = await reader.ReadLineAsync(timeout.Token);
        if (line is null || line.Length > 16384) throw new InvalidDataException("Invalid GUI update reply");
        var result = JsonSerializer.Deserialize<UpdateIpcStatus>(line, UpdateIpcProtocol.Json)
            ?? throw new InvalidDataException("Missing GUI update reply");
        if (result.ProtocolVersion != 1 || result.PendingFacts < 0 || result.LastSequence < 0)
            throw new InvalidDataException("Incompatible GUI update reply");
        return result;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out uint processId);
}
