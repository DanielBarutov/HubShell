using GameClub.Client.Avalonia.Development;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class LocalAvaloniaBackendIntegrationTests
{
    [Fact]
    public async Task RegistersThroughTheLocalBackendAndOpensThePortal()
    {
        if (!string.Equals(
                Environment.GetEnvironmentVariable("GAMECLUB_RUN_LOCAL_INTEGRATION"),
                "1",
                StringComparison.Ordinal))
        {
            return;
        }

        await using var host = new LocalBackendClientHost();
        await host.StartAsync();

        var viewModel = host.ViewModel;
        var deadline = DateTimeOffset.UtcNow.AddSeconds(15);
        while (string.IsNullOrWhiteSpace(viewModel.DeviceId) && DateTimeOffset.UtcNow < deadline)
        {
            await Task.Delay(100);
        }

        Assert.False(string.IsNullOrWhiteSpace(viewModel.DeviceId));

        var suffix = Guid.NewGuid().ToString("N")[..10];
        viewModel.PortalNickname = $"avalonia_{suffix}";
        viewModel.PortalPhone = $"+7999{Random.Shared.Next(1000000, 9999999)}";
        viewModel.PortalRegistrationPassword = $"smoke-{suffix}";

        Assert.True(await viewModel.RegisterPortalAsync());
        Assert.True(viewModel.IsPortalContentVisible);
        Assert.True(viewModel.IsActiveSessionVisible);

        await viewModel.LogoutAsync();
    }
}
