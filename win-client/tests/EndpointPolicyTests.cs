using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class EndpointPolicyTests
{
    [Theory]
    [InlineData("http://127.0.0.1:8100")]
    [InlineData("http://10.20.30.40:8100")]
    [InlineData("http://172.16.10.20:8100")]
    [InlineData("http://192.168.0.47:8100")]
    public void AllowsHttpForLoopbackAndPrivateLan(string value)
    {
        var endpoint = EndpointPolicy.Validate(
            new Uri(value),
            "GAMECLUB_AUTH_ADDRESS",
            "production");

        Assert.Equal(value, endpoint.AbsoluteUri.TrimEnd('/'));
    }

    [Fact]
    public void RejectsHttpForPublicAddress()
    {
        var exception = Assert.Throws<InvalidOperationException>(() => EndpointPolicy.Validate(
            new Uri("http://203.0.113.10:8100"),
            "GAMECLUB_AUTH_ADDRESS",
            "production"));

        Assert.Contains("HTTPS", exception.Message);
    }
}
