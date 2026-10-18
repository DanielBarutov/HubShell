using GameClub.Client.Application;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2SnapshotPublicKeyRingTests
{
    [Fact]
    public void ParsesDeploymentPublicKeysWithoutChangingTheirValues()
    {
        var keys = V2SnapshotPublicKeyRing.Parse(
            "club-2026-a=11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=;club-2026-b=another-key");

        Assert.Equal("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=", keys["club-2026-a"]);
        Assert.Equal("another-key", keys["club-2026-b"]);
    }

    [Theory]
    [InlineData("")]
    [InlineData("broken-entry")]
    [InlineData("club-a=key;club-a=another-key")]
    public void RejectsMissingMalformedOrDuplicateKeyIds(string configuredKeyring)
    {
        Assert.Throws<InvalidOperationException>(() => V2SnapshotPublicKeyRing.Parse(configuredKeyring));
    }
}
