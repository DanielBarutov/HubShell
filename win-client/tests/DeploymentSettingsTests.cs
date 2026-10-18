using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class DeploymentSettingsTests
{
    [Fact]
    public void ReadsAddressesAndPublicKeyWithoutSplittingBase64OrCommentCharacters()
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, "; club server\nGrpcAddress=http://192.168.1.10:50051\nV2EventsHttpAddress=http://192.168.1.10:8100\nV2SnapshotPublicKeys=club=YWJjZA==;other=ZQ==\n");
            var settings = DeploymentSettings.LoadConfiguration(path);
            Assert.Equal("http://192.168.1.10:50051", settings["GrpcAddress"]);
            Assert.Equal("http://192.168.1.10:8100", settings["V2EventsHttpAddress"]);
            Assert.Equal("club=YWJjZA==;other=ZQ==", settings["V2SnapshotPublicKeys"]);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void RuntimeReadsIniBesideExecutableAndAllowsExistingEnvironmentOverride()
    {
        var path = Path.Combine(AppContext.BaseDirectory, "server.ini");
        var oldGrpc = Environment.GetEnvironmentVariable("GAMECLUB_GRPC_ADDRESS");
        var oldEvents = Environment.GetEnvironmentVariable("GAMECLUB_V2_EVENTS_HTTP_ADDRESS");
        Assert.False(File.Exists(path));
        try
        {
            Environment.SetEnvironmentVariable("GAMECLUB_GRPC_ADDRESS", null);
            Environment.SetEnvironmentVariable("GAMECLUB_V2_EVENTS_HTTP_ADDRESS", null);
            File.WriteAllText(path, "GrpcAddress=http://192.168.1.10:51051\nV2EventsHttpAddress=http://192.168.1.10:8100");
            Assert.Equal("192.168.1.10", DeploymentSettings.GrpcAddress.Host);
            Assert.Equal(8100, DeploymentSettings.V2EventsHttpAddress!.Port);
            Environment.SetEnvironmentVariable("GAMECLUB_GRPC_ADDRESS", "http://10.0.0.2:51051");
            Assert.Equal("10.0.0.2", DeploymentSettings.GrpcAddress.Host);
        }
        finally
        {
            File.Delete(path);
            Environment.SetEnvironmentVariable("GAMECLUB_GRPC_ADDRESS", oldGrpc);
            Environment.SetEnvironmentVariable("GAMECLUB_V2_EVENTS_HTTP_ADDRESS", oldEvents);
        }
    }

    [Theory]
    [InlineData("GrpcAddress=garbage")]
    [InlineData("GrpcAddress=http://203.0.113.10:50051")]
    [InlineData("GrpcAddress=")]
    [InlineData("Secret=anything")]
    [InlineData("GrpcAddress=https://club.local\ngrpcaddress=https://other.local")]
    [InlineData("broken line")]
    [InlineData("; empty configuration")]
    public void RejectsInvalidConfiguration(string content)
    {
        var path = Path.GetTempFileName();
        try
        {
            File.WriteAllText(path, content);
            Assert.Throws<InvalidOperationException>(() => DeploymentSettings.LoadConfiguration(path));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void MissingFileKeepsExistingDeploymentConfiguration()
    {
        Assert.Empty(DeploymentSettings.LoadConfiguration(Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".ini")));
    }
}
