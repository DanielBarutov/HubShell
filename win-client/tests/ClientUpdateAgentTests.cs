using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientUpdateAgentTests
{
    [Fact]
    public async Task ActiveSessionIsReportedButNeverClosedOrReplaced()
    {
        using var fixture = new Fixture();
        fixture.Gui.Active = true;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.DoesNotContain("begin", fixture.Events);
        Assert.DoesNotContain("pause", fixture.Events);
        Assert.True(fixture.Reports.Last().GetProperty("active_session").GetBoolean());
    }

    [Fact]
    public async Task InstallRequiresServerPermissionBeforeCloseAndReportsVerifiedHash()
    {
        using var fixture = new Fixture();
        await fixture.Agent.TickAsync(default);
        Assert.Equal("new", File.ReadAllText(fixture.Executable));
        Assert.Equal(new[] { "begin", "pause", "close", "exit", "start", "resume" }, fixture.Events);
        Assert.Equal("installed", fixture.State.Read()!.Stage);
        Assert.Equal(fixture.Manifest.ExecutableSha256,
            fixture.Reports.Last().GetProperty("installed_sha256").GetString());
        Assert.True(fixture.State.Read()!.Blocked);
    }

    [Fact]
    public async Task LostBeginResponseDoesNotCloseOrReplaceGui()
    {
        using var fixture = new Fixture();
        fixture.LoseBegin = true;
        await Assert.ThrowsAsync<HttpRequestException>(() => fixture.Agent.TickAsync(default));
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.Equal(new[] { "begin" }, fixture.Events);
    }

    [Fact]
    public async Task DeniedInstallPermissionOnlyStagesPackage()
    {
        using var fixture = new Fixture();
        fixture.MayInstall = false;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.Empty(fixture.Events);
        Assert.True(fixture.State.Read()!.Blocked);
    }

    [Fact]
    public async Task SessionAppearingDuringClosePreventsReplacement()
    {
        using var fixture = new Fixture();
        fixture.Gui.ActiveAtClose = true;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.DoesNotContain("exit", fixture.Events);
        Assert.Equal("failed", fixture.State.Read()!.Stage);
        Assert.True(fixture.State.Read()!.Blocked);
    }

    [Fact]
    public async Task LostInstalledReportKeepsHealthyExecutableForRetry()
    {
        using var fixture = new Fixture();
        fixture.LoseInstalledReport = true;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("new", File.ReadAllText(fixture.Executable));
        Assert.Equal("installed", fixture.State.Read()!.Stage);
        fixture.LoseInstalledReport = false;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("installed", fixture.Reports.Last().GetProperty("stage").GetString());
        Assert.Equal(1, fixture.Events.Count(value => value == "close"));
    }

    [Fact]
    public async Task FailedHealthCheckRestoresOldExecutableAndKeepsBlock()
    {
        using var fixture = new Fixture();
        fixture.Gui.Healthy = false;
        fixture.Agent.HealthTimeout = TimeSpan.FromMilliseconds(20);
        await fixture.Agent.TickAsync(default);
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.Equal("rolled_back", fixture.State.Read()!.Stage);
        Assert.True(fixture.State.Read()!.Blocked);
        Assert.Equal("rolled_back", fixture.Reports.Last().GetProperty("stage").GetString());
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task FailedFleetPollPreservesAcceptedInstallOrRollbackResult(bool unhealthy)
    {
        using var fixture = new Fixture();
        fixture.Gui.Healthy = !unhealthy;
        fixture.Agent.HealthTimeout = TimeSpan.FromMilliseconds(20);
        await fixture.Agent.TickAsync(default);
        var accepted = fixture.Reports.Count;
        fixture.Phase = "failed";
        await fixture.Agent.TickAsync(default);
        Assert.Equal(accepted, fixture.Reports.Count);
        Assert.Equal(unhealthy ? "rolled_back" : "installed", fixture.State.Read()!.Stage);
        Assert.True(fixture.State.Read()!.Blocked);
    }

    [Fact]
    public async Task UntrustedPackageCannotObtainInstallPermission()
    {
        using var fixture = new Fixture();
        fixture.Signature[0] ^= 1;
        await fixture.Agent.TickAsync(default);
        Assert.Equal("old", File.ReadAllText(fixture.Executable));
        Assert.Empty(fixture.Events);
        Assert.Equal("package_unavailable", fixture.Reports.Last().GetProperty("error_code").GetString());
        Assert.False(fixture.Reports.Last().GetProperty("ready").GetBoolean());
    }

    [Fact]
    public async Task RecoveryWithoutVerifiedBackupNeverLaunchesCorruptExecutable()
    {
        using var fixture = new Fixture();
        fixture.State.Write(new(fixture.Id, fixture.Round, "v-test", fixture.Manifest.ExecutableSha256,
            "replace_pending", true, new string('b', 64)));
        File.WriteAllText(fixture.Executable, "corrupt");
        await Assert.ThrowsAsync<InvalidDataException>(() =>
            ClientUpdateAgent.RecoverLocalAsync(fixture.Directory, fixture.Gui, default));
        Assert.Equal(new[] { "pause", "stop" }, fixture.Events);
    }

    private sealed class Fixture : HttpMessageHandler
    {
        public string Directory { get; } = Path.Combine(Path.GetTempPath(), "hubshell-agent-" + Guid.NewGuid().ToString("N"));
        public string Executable => Path.Combine(Directory, "HubShell.exe");
        public Guid Id { get; } = Guid.NewGuid();
        public Guid Round { get; } = Guid.NewGuid();
        public List<string> Events { get; } = new();
        public List<JsonElement> Reports { get; } = new();
        public FakeGui Gui { get; }
        public ClientUpdateAgent Agent { get; }
        public ClientUpdateStateStore State { get; }
        public ClientReleaseManifest Manifest { get; }
        public byte[] Signature { get; }
        public bool LoseBegin { get; set; }
        public bool MayInstall { get; set; } = true;
        public string Phase { get; set; } = "authorized";
        public bool LoseInstalledReport { get; set; }
        private readonly byte[] _archive, _manifest;
        private readonly HttpClient _client;
        private long _sequence;
        private string _stage = "ready";
        private static readonly JsonSerializerOptions SnakeJson = new(JsonSerializerDefaults.Web)
            { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

        public Fixture()
        {
            System.IO.Directory.CreateDirectory(Directory);
            File.WriteAllText(Executable, "old");
            var executable = Encoding.UTF8.GetBytes("new");
            using var memory = new MemoryStream();
            using (var archive = new ZipArchive(memory, ZipArchiveMode.Create, true))
            using (var output = archive.CreateEntry("HubShell.exe").Open()) output.Write(executable);
            _archive = memory.ToArray();
            Manifest = new(1, "v-test", new string('a', 40), "win-x64", "HubShell.exe",
                Hash(executable), executable.Length, Hash(_archive), _archive.Length, 1, 1, 1, 1);
            _manifest = JsonSerializer.SerializeToUtf8Bytes(Manifest, UpdateIpcProtocol.Json);
            using var key = RSA.Create(2048);
            Signature = key.SignData(_manifest, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            Gui = new FakeGui(this);
            State = new(Directory);
            _client = new HttpClient(this, false);
            Agent = new(_client, new Uri("http://127.0.0.1:8000"), "pc-1", "install-1",
                "individual-credential", key.ExportSubjectPublicKeyInfoPem(), Directory, Gui);
        }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            var path = request.RequestUri!.AbsolutePath;
            if (path.EndsWith("/agent-token")) return Json(new { access_token = "limited-token", expires_in = 900 });
            if (path.Contains("/releases/"))
                return new(HttpStatusCode.OK) { Content = new ByteArrayContent(path.EndsWith(".sig") ? Signature
                    : path.EndsWith(".json") ? _manifest : _archive) };
            Assert.Equal("Bearer", request.Headers.Authorization?.Scheme);
            if (path.EndsWith("/current"))
                return Json(new AgentCommand(new(Id, Round, "v-test", Manifest.ExecutableSha256,
                    Phase, true, MayInstall, _sequence, _stage, false), 1));
            using var body = JsonDocument.Parse(await request.Content!.ReadAsStringAsync(token));
            var report = body.RootElement.Clone();
            if (path.EndsWith("/begin-install"))
            {
                Events.Add("begin");
                if (LoseBegin) throw new HttpRequestException("Lost response");
            }
            else if (report.GetProperty("stage").GetString() == "installed" && LoseInstalledReport)
                throw new HttpRequestException("Lost report");
            _sequence = report.GetProperty("sequence").GetInt64();
            _stage = report.GetProperty("stage").GetString()!;
            Reports.Add(report);
            return Json(new { });
        }

        private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        private static HttpResponseMessage Json(object value) => new(HttpStatusCode.OK)
            { Content = JsonContent.Create(value, options: SnakeJson) };
        protected override void Dispose(bool disposing)
        {
            if (disposing) { _client.Dispose(); System.IO.Directory.Delete(Directory, true); }
            base.Dispose(disposing);
        }
    }

    private sealed class FakeGui(Fixture fixture) : IUpdateGuiPlatform
    {
        public bool Active { get; set; }
        public bool ActiveAtClose { get; set; }
        public bool Healthy { get; set; } = true;
        public Task PauseRecoveryAsync(CancellationToken token) { fixture.Events.Add("pause"); return Task.CompletedTask; }
        public Task ResumeRecoveryAsync(CancellationToken token) { fixture.Events.Add("resume"); return Task.CompletedTask; }
        public Task WaitForExitAsync(CancellationToken token) { fixture.Events.Add("exit"); return Task.CompletedTask; }
        public Task StartGuiAsync(CancellationToken token) { fixture.Events.Add("start"); return Task.CompletedTask; }
        public Task StopFailedGuiAsync(CancellationToken token) { fixture.Events.Add("stop"); return Task.CompletedTask; }
        public Task<UpdateIpcStatus> QueryAsync(UpdateIpcRequest request, CancellationToken token)
        {
            if (request.Command == "close") fixture.Events.Add("close");
            var active = Active || request.Command == "close" && ActiveAtClose;
            return Task.FromResult(new UpdateIpcStatus("pc-1", "install-1",
                File.ReadAllText(fixture.Executable) == "new" && Healthy ? "v-test" : "old",
                active, 0, !active, true, Closing: request.Command == "close"));
        }
    }
}
