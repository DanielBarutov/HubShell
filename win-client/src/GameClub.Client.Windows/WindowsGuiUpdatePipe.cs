using System.IO.Pipes;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;

namespace GameClub.Client.Windows;

[SupportedOSPlatform("windows")]
internal sealed class WindowsGuiUpdatePipe
{
    private readonly Func<UpdateIpcRequest, CancellationToken, Task<UpdateIpcStatus>> _handle;
    private readonly Action _close;

    public WindowsGuiUpdatePipe(Func<UpdateIpcRequest, CancellationToken, Task<UpdateIpcStatus>> handle,
        Action close)
    {
        _handle = handle;
        _close = close;
    }

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        using var process = System.Diagnostics.Process.GetCurrentProcess();
        var name = UpdateIpcProtocol.PipeName(AppContext.BaseDirectory, process.SessionId);
        var acl = new PipeSecurity();
        SecurityIdentifier user;
        using (var identity = WindowsIdentity.GetCurrent())
            user = identity.User ?? throw new InvalidOperationException("Missing user SID");
        foreach (var sid in new[] { user, new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null) })
            acl.AddAccessRule(new PipeAccessRule(sid, PipeAccessRights.FullControl, AccessControlType.Allow));
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                await using var pipe = NamedPipeServerStreamAcl.Create(name, PipeDirection.InOut, 1,
                    PipeTransmissionMode.Byte, PipeOptions.Asynchronous, 4096, 4096, acl);
                await pipe.WaitForConnectionAsync(cancellationToken);
                var trusted = false;
                try
                {
                    pipe.RunAsClient(() =>
                    {
                        using var identity = WindowsIdentity.GetCurrent();
                        trusted = identity.IsSystem;
                    });
                }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException or InvalidOperationException)
                { continue; }
                if (!trusted) continue;
                using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                timeout.CancelAfter(TimeSpan.FromSeconds(15));
                try
                {
                    using var reader = new StreamReader(pipe, Encoding.UTF8, false, 4096, leaveOpen: true);
                    using var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, leaveOpen: true);
                    var line = await reader.ReadLineAsync(timeout.Token);
                    if (line is null || line.Length > 4096) continue;
                    var request = JsonSerializer.Deserialize<UpdateIpcRequest>(line, UpdateIpcProtocol.Json);
                    if (request is null || request.Command is not ("status" or "prepare" or "close" or "release")) continue;
                    var result = await _handle(request, timeout.Token);
                    await writer.WriteLineAsync(JsonSerializer.Serialize(result, UpdateIpcProtocol.Json).AsMemory(), timeout.Token);
                    await writer.FlushAsync(timeout.Token);
                    if (result.Closing) _close();
                }
                catch (Exception error) when (error is IOException or JsonException or OperationCanceledException or InvalidOperationException)
                {
                    if (cancellationToken.IsCancellationRequested) break;
                }
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
    }
}
