using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class DeviceEnrollmentTokenProviderTests
{
    /// <summary>
    /// Проверяет, что при большом числе активных сетевых интерфейсов клиент
    /// отправляет в регистрацию не больше допустимых сервером 16 MAC-адресов.
    /// </summary>
    [Fact]
    public async Task EnrollmentSendsNoMoreThanServerMacAddressLimit()
    {
        var gateway = new CapturingEnrollmentGateway();
        using var provider = new DeviceEnrollmentTokenProvider(
            new Uri("http://127.0.0.1:51051"),
            "dev",
            gateway,
            Enumerable.Range(1, 17).Select(index => $"00:00:00:00:00:{index:X2}").ToArray(),
            "test-installation");

        await Assert.ThrowsAsync<DeviceEnrollmentPendingException>(
            async () => await provider.GetAccessTokenAsync().AsTask());

        Assert.NotNull(gateway.MacAddresses);
        Assert.Equal(16, gateway.MacAddresses.Count);
        Assert.Equal("00:00:00:00:00:01", gateway.MacAddresses[0]);
        Assert.Equal("00:00:00:00:00:10", gateway.MacAddresses[15]);
    }

    private sealed class CapturingEnrollmentGateway : IDeviceEnrollmentGateway
    {
        public IReadOnlyList<string>? MacAddresses { get; private set; }

        public ValueTask<DeviceEnrollmentSnapshot> EnrollAsync(
            IReadOnlyList<string> macAddresses,
            string installationId,
            CancellationToken cancellationToken = default)
        {
            MacAddresses = macAddresses;
            return ValueTask.FromResult(new DeviceEnrollmentSnapshot(
                "pending",
                DeviceId: null,
                WorkstationId: null,
                WorkstationName: null,
                AccessToken: null,
                ExpiresIn: 0));
        }
    }
}
