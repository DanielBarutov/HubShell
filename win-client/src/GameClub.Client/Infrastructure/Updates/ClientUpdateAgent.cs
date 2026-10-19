using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace GameClub.Client.Infrastructure.Updates;

public interface IUpdateGuiPlatform
{
    Task PauseRecoveryAsync(CancellationToken token);
    Task ResumeRecoveryAsync(CancellationToken token);
    Task<UpdateIpcStatus> QueryAsync(UpdateIpcRequest request, CancellationToken token);
    Task WaitForExitAsync(CancellationToken token);
    Task StartGuiAsync(CancellationToken token);
    Task StopFailedGuiAsync(CancellationToken token);
}

public sealed record AgentDeployment(Guid Id, Guid RoundId, string ReleaseId, string ExecutableSha256,
    string Phase, bool BlockGui, bool MayInstall, long LastSequence, string? ReportStage, bool GuiConfirmed);
public sealed record AgentCommand(AgentDeployment? Deployment, int BackendProtocol);

/// <summary>Portable protocol/file workflow; the Windows adapter owns processes and IPC.</summary>
public sealed class ClientUpdateAgent
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web)
        { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    private readonly HttpClient _http;
    private readonly Uri _backend;
    private readonly string _deviceId, _installationId, _secret, _publicKey, _directory;
    private readonly IUpdateGuiPlatform _gui;
    private readonly ClientUpdateStateStore _state;
    private readonly ClientExecutableInstaller _installer;
    private readonly Guid _instanceId = Guid.NewGuid();
    private string? _token;
    private DateTimeOffset _tokenExpiry;
    private bool _recovered;
    internal TimeSpan HealthTimeout { get; set; } = TimeSpan.FromSeconds(60);

    public ClientUpdateAgent(HttpClient http, Uri backend, string deviceId, string installationId,
        string credentialSecret, string trustedPublicKeyPem, string directory, IUpdateGuiPlatform gui)
    {
        _http = http; _backend = backend; _deviceId = deviceId; _installationId = installationId;
        _secret = credentialSecret; _publicKey = trustedPublicKeyPem; _directory = directory; _gui = gui;
        _state = new ClientUpdateStateStore(directory);
        _installer = new ClientExecutableInstaller(directory, _state);
    }

    public async Task TickAsync(CancellationToken token)
    {
        await RecoverAsync(token);
        var command = await CommandAsync(token);
        var item = command.Deployment;
        if (item is null) return; // An unknown server state never removes a local block.
        if (item.Id == Guid.Empty || item.RoundId == Guid.Empty || command.BackendProtocol != 1
            || item.ReleaseId is null || item.ExecutableSha256 is null
            || !Regex.IsMatch(item.ReleaseId, @"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\z")
            || !Regex.IsMatch(item.ExecutableSha256, @"\A[a-f0-9]{64}\z") || item.LastSequence < 0
            || item.Phase is not ("polling" or "preparing" or "authorized" or "failed" or "completed"))
            throw new InvalidDataException("Incompatible deployment command");
        var local = _state.Read();
        if (item.Phase == "completed")
        {
            if (local is not null && local.DeploymentId == item.Id)
            {
                _state.Write(local with { Stage = "completed", Blocked = false });
                await _gui.QueryAsync(new("release", local.DeploymentId, local.RoundId), token);
                var staging = Path.Combine(_directory, ".updates", item.Id.ToString("N"));
                if (Directory.Exists(staging) && (File.GetAttributes(staging) & FileAttributes.ReparsePoint) == 0)
                {
                    foreach (var name in new[] { "HubShell.zip", "HubShell.exe.new" })
                    {
                        var path = Path.Combine(staging, name);
                        if (File.Exists(path) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) == 0) File.Delete(path);
                    }
                    if (!Directory.EnumerateFileSystemEntries(staging).Any()) Directory.Delete(staging);
                }
            }
            return;
        }
        if (local is { Blocked: true } && local.DeploymentId != item.Id)
            throw new InvalidDataException("An unfinished local deployment cannot be replaced");
        if (item.BlockGui && (local is null || local.RoundId != item.RoundId))
        {
            local = new(item.Id, item.RoundId, item.ReleaseId, item.ExecutableSha256, "prepared", true,
                local is not null && local.ReleaseId == item.ReleaseId ? local.OldExecutableSha256 : null);
            _state.Write(local);
        }
        var status = await StatusAsync(item, token);
        if (item.Phase == "failed")
        {
            // Preserve the recorded install/rollback result until an explicit fleet retry.
            return;
        }
        if (item.Phase == "authorized" && local?.Stage == "installed")
        {
            await ConfirmInstalledAsync(item, status, token);
            return;
        }
        ClientReleaseManifest manifest;
        string staged;
        try { (manifest, staged) = await StageAsync(item, command.BackendProtocol, token); }
        catch (Exception error) when (error is IOException or System.Security.Cryptography.CryptographicException
            or JsonException or HttpRequestException || error is OperationCanceledException && !token.IsCancellationRequested)
        {
            await ReportAsync(item, status with { Ready = false }, "ready", item.LastSequence + 1,
                null, "package_unavailable", token);
            return;
        }
        if (item.Phase != "authorized")
        {
            await ReportAsync(item, status, "ready", item.LastSequence + 1, null, status.ErrorCode, token);
            return;
        }
        if (local?.Stage == "verifying")
        {
            await InstallAsync(item, manifest, staged, status, token);
            return;
        }
        if (item.ReportStage is "installing" or "verifying" or "installed")
        {
            // A lost begin-install response is not permission to start replacing files.
            await ReportAsync(item, status, "failed", item.LastSequence + 1, null, "install_interrupted", token);
            return;
        }
        await ReportAsync(item, status, "ready", item.LastSequence + 1, null, status.ErrorCode, token);
        command = await CommandAsync(token);
        var latest = command.Deployment;
        if (latest is null || latest.Id != item.Id || latest.RoundId != item.RoundId || !latest.MayInstall
            || !status.Ready || status.ActiveSession || status.PendingFacts != 0 || !status.Blocked) return;
        await PostAsync($"/{item.Id}/begin-install", ReportBody(latest, status, "installing",
            latest.LastSequence + 1, null, null), token);
        await InstallAsync(latest, manifest, staged, status, token);
    }

    private async Task RecoverAsync(CancellationToken token)
    {
        if (_recovered) return;
        await RecoverLocalAsync(_directory, _gui, token);
        _recovered = true;
    }

    public static async Task RecoverLocalAsync(string directory, IUpdateGuiPlatform gui, CancellationToken token)
    {
        var state = new ClientUpdateStateStore(directory);
        var installer = new ClientExecutableInstaller(directory, state);
        var local = state.Read();
        if (local?.Stage is not ("closing" or "backup_pending" or "replace_pending" or "verifying" or "installed")) return;
        await gui.PauseRecoveryAsync(token);
        var safe = false;
        try
        {
            var installed = File.Exists(installer.ExecutablePath) ? ClientExecutableInstaller.Hash(installer.ExecutablePath) : null;
            if (installed != local.ExecutableSha256 && installed != local.OldExecutableSha256)
                await gui.StopFailedGuiAsync(token);
            installer.RecoverInterruptedReplacement(local);
            safe = true;
            await gui.StartGuiAsync(token);
        }
        finally { if (safe) await gui.ResumeRecoveryAsync(CancellationToken.None); }
    }

    private async Task InstallAsync(AgentDeployment item, ClientReleaseManifest manifest, string staged,
        UpdateIpcStatus authorizedStatus, CancellationToken token)
    {
        await _gui.PauseRecoveryAsync(token);
        var local = new ClientUpdateJournal(item.Id, item.RoundId, item.ReleaseId,
            item.ExecutableSha256, "closing", true,
            _state.Read()?.OldExecutableSha256 ?? ClientExecutableInstaller.Hash(_installer.ExecutablePath));
        _state.Write(local);
        try
        {
            var replace = ClientExecutableInstaller.Hash(_installer.ExecutablePath) != item.ExecutableSha256;
            if (replace || authorizedStatus.ReleaseId != item.ReleaseId)
            {
                var closing = await _gui.QueryAsync(new("close", item.Id, item.RoundId), token);
                RequireIdentity(closing);
                if (!closing.Closing || !closing.Ready || closing.ActiveSession || closing.PendingFacts != 0
                    || closing.SessionId != authorizedStatus.SessionId || closing.LastSequence != authorizedStatus.LastSequence
                    || closing.LastPayloadHash != authorizedStatus.LastPayloadHash)
                    throw new InvalidDataException("GUI readiness changed before replacement");
                await _gui.WaitForExitAsync(token);
                if (replace) local = _installer.Install(staged, manifest, local);
                else { local = local with { Stage = "verifying" }; _state.Write(local); }
                await _gui.StartGuiAsync(token);
            }
            else
            {
                local = local with { Stage = "verifying" };
                _state.Write(local);
            }
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(HealthTimeout);
            while (true)
            {
                deadline.Token.ThrowIfCancellationRequested();
                UpdateIpcStatus? status = null;
                try { status = await StatusAsync(item, deadline.Token); }
                catch (Exception error) when (error is IOException or TimeoutException or InvalidOperationException) { }
                if (status is { Ready: true } && status.ReleaseId == item.ReleaseId)
                {
                    await ConfirmInstalledAsync((await CommandAsync(deadline.Token)).Deployment
                        ?? throw new InvalidDataException("Deployment disappeared"), status, deadline.Token);
                    break;
                }
                await Task.Delay(1000, deadline.Token);
            }
        }
        catch (Exception) when (!token.IsCancellationRequested)
        {
            var current = _state.Read() ?? local;
            if (current.Stage == "installed") return; // Retry the report; never undo a healthy client for a network failure.
            if (current.Stage is "verifying" or "replace_pending" or "backup_pending")
            {
                await _gui.StopFailedGuiAsync(token);
                if (File.Exists(_installer.BackupPath)) current = _installer.Rollback(current);
                else { current = current with { Stage = "failed" }; _state.Write(current); }
            }
            else { current = current with { Stage = "failed" }; _state.Write(current); }
            if (!ExecutableIsVerified(current))
                throw new InvalidDataException("No verified executable is available for restart");
            await _gui.StartGuiAsync(token);
            var latest = (await CommandAsync(token)).Deployment;
            if (latest is not null && latest.Id == item.Id && latest.RoundId == item.RoundId)
                await ReportAsync(latest, await StatusAsync(item, token),
                    current.Stage == "rolled_back" ? "rolled_back" : "failed", latest.LastSequence + 1,
                    null, "install_failed", token);
        }
        finally
        {
            if (ExecutableIsVerified(_state.Read() ?? local))
                await _gui.ResumeRecoveryAsync(CancellationToken.None);
        }
    }

    private bool ExecutableIsVerified(ClientUpdateJournal journal)
    {
        try
        {
            var hash = ClientExecutableInstaller.Hash(_installer.ExecutablePath);
            return hash == journal.ExecutableSha256 || hash == journal.OldExecutableSha256;
        }
        catch (IOException) { return false; }
    }

    private async Task ConfirmInstalledAsync(AgentDeployment item, UpdateIpcStatus status, CancellationToken token)
    {
        if (!status.Ready || status.ActiveSession || status.PendingFacts != 0 || !status.Blocked
            || status.ReleaseId != item.ReleaseId || ClientExecutableInstaller.Hash(_installer.ExecutablePath) != item.ExecutableSha256)
            throw new InvalidDataException("New GUI has not become healthy");
        var local = _state.Read() ?? throw new InvalidDataException("Missing local deployment journal");
        _state.Write(local with { Stage = "installed" });
        await ReportAsync(item, status, "installed", item.LastSequence + 1, item.ExecutableSha256, null, token);
    }

    private async Task<UpdateIpcStatus> StatusAsync(AgentDeployment item, CancellationToken token)
    {
        try
        {
            var status = await _gui.QueryAsync(new(item.BlockGui ? "prepare" : "status", item.Id, item.RoundId), token);
            RequireIdentity(status);
            return status;
        }
        catch (Exception error) when (error is IOException or TimeoutException or InvalidOperationException)
        {
            return new(_deviceId, _installationId, "unknown", true, 0, false, item.BlockGui, ErrorCode: "gui_unavailable");
        }
    }

    private void RequireIdentity(UpdateIpcStatus status)
    {
        if (status.DeviceId != _deviceId || status.InstallationId != _installationId || status.ProtocolVersion != 1)
            throw new InvalidDataException("GUI belongs to another installation");
    }

    private async Task<(ClientReleaseManifest, string)> StageAsync(AgentDeployment item, int backendProtocol, CancellationToken token)
    {
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromMinutes(2));
        token = deadline.Token;
        var release = $"/api/v1/client-updates/releases/{Uri.EscapeDataString(item.ReleaseId)}/";
        var bytes = await DownloadAsync(release + "release.json", 16384, token);
        var signature = await DownloadAsync(release + "release.json.sig", 2048, token);
        var manifest = ClientUpdatePackage.VerifyManifest(bytes, signature, _publicKey, backendProtocol, 1);
        if (manifest.ReleaseId != item.ReleaseId || manifest.ExecutableSha256 != item.ExecutableSha256)
            throw new InvalidDataException("Signed package does not match deployment");
        var directory = Path.Combine(_directory, ".updates", item.Id.ToString("N"));
        Directory.CreateDirectory(directory);
        if ((File.GetAttributes(directory) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Update staging cannot be a link");
        var staged = Path.Combine(directory, "HubShell.exe.new");
        if (File.Exists(staged) && ClientExecutableInstaller.Hash(staged) == manifest.ExecutableSha256)
            return (manifest, staged);
        if (File.Exists(staged)) File.Delete(staged);
        var archivePath = Path.Combine(directory, "HubShell.zip");
        using var request = new HttpRequestMessage(HttpMethod.Get, new Uri(_backend, release + "HubShell.zip"));
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        response.EnsureSuccessStatusCode();
        await using (var output = new FileStream(archivePath, FileMode.Create, FileAccess.Write, FileShare.None, 81920, true))
        await using (var input = await response.Content.ReadAsStreamAsync(token))
        {
            var buffer = new byte[81920];
            long size = 0;
            int count;
            while ((count = await input.ReadAsync(buffer, token)) != 0)
            {
                size += count;
                if (size > manifest.ArchiveBytes) throw new InvalidDataException("Archive exceeds signed size");
                await output.WriteAsync(buffer.AsMemory(0, count), token);
            }
            if (size != manifest.ArchiveBytes) throw new InvalidDataException("Incomplete archive");
        }
        return (manifest, await ClientUpdatePackage.ExtractVerifiedExecutableAsync(manifest, archivePath, directory, token));
    }

    private object ReportBody(AgentDeployment item, UpdateIpcStatus status, string stage, long sequence,
        string? installedHash, string? errorCode) => new {
            round_id = item.RoundId, sequence, instance_id = _instanceId,
            active_session = status.ActiveSession, pending_facts = status.PendingFacts, ready = status.Ready,
            stage, installed_sha256 = installedHash, error_code = errorCode,
            session_id = status.SessionId, last_sequence = status.LastSequence, last_payload_hash = status.LastPayloadHash,
            running_release_id = status.ReleaseId,
        };
    private Task ReportAsync(AgentDeployment item, UpdateIpcStatus status, string stage, long sequence,
        string? installedHash, string? error, CancellationToken token) =>
        PostAsync($"/{item.Id}/reports", ReportBody(item, status, stage, sequence, installedHash, error), token);

    private async Task<AgentCommand> CommandAsync(CancellationToken token)
    {
        using var response = await SendAsync(HttpMethod.Get, $"/agent/current?instance_id={_instanceId}", null, token);
        return await response.Content.ReadFromJsonAsync<AgentCommand>(Json, token)
            ?? throw new InvalidDataException("Missing agent command");
    }
    private async Task PostAsync(string path, object body, CancellationToken token)
    { using var response = await SendAsync(HttpMethod.Post, path, body, token); }

    private async Task<HttpResponseMessage> SendAsync(HttpMethod method, string path, object? body, CancellationToken token)
    {
        if (_token is null || _tokenExpiry <= DateTimeOffset.UtcNow)
        {
            using var authentication = await _http.PostAsJsonAsync(new Uri(_backend, "/api/v1/client-updates/agent-token"),
                new { device_id = _deviceId, credential_secret = _secret }, token);
            authentication.EnsureSuccessStatusCode();
            using var document = await JsonDocument.ParseAsync(await authentication.Content.ReadAsStreamAsync(token), cancellationToken: token);
            _token = document.RootElement.GetProperty("access_token").GetString() ?? throw new InvalidDataException("Missing updater token");
            _tokenExpiry = DateTimeOffset.UtcNow.AddSeconds(Math.Max(1, document.RootElement.GetProperty("expires_in").GetInt32() - 30));
        }
        using var request = new HttpRequestMessage(method, new Uri(_backend, "/api/v1/client-updates" + path));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        if (body is not null) request.Content = JsonContent.Create(body, options: Json);
        var response = await _http.SendAsync(request, token);
        if (response.StatusCode == HttpStatusCode.Unauthorized) _token = null;
        try { response.EnsureSuccessStatusCode(); return response; }
        catch { response.Dispose(); throw; }
    }

    private async Task<byte[]> DownloadAsync(string path, int limit, CancellationToken token)
    {
        using var response = await _http.GetAsync(new Uri(_backend, path), HttpCompletionOption.ResponseHeadersRead, token);
        response.EnsureSuccessStatusCode();
        await using var input = await response.Content.ReadAsStreamAsync(token);
        using var output = new MemoryStream();
        var buffer = new byte[4096];
        int count;
        while ((count = await input.ReadAsync(buffer, token)) != 0)
        {
            if (output.Length + count > limit) throw new InvalidDataException("Release metadata exceeds limit");
            output.Write(buffer, 0, count);
        }
        return output.ToArray();
    }
}
