using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientSessionCoordinatorTests
{
    [Fact]
    public async Task ConvertsDeviceAuthenticationFailureToAuthenticationRequiredState()
    {
        await using var coordinator = new ClientSessionCoordinator(new AuthenticationFailingBackend());

        var snapshot = await coordinator.CheckConnectionAsync();

        Assert.Equal(ClientConnectionState.AuthenticationRequired, snapshot.State);
        Assert.Contains("авторизация", snapshot.Message, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class AuthenticationFailingBackend : IBackendClient
    {
        public Task<ClientConnectionSnapshot> CheckConnectionAsync(
            CancellationToken cancellationToken = default) =>
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("test authentication failure"));

        public Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
            string deviceId,
            string clientVersion,
            IReadOnlyCollection<string> capabilities,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new WorkstationHeartbeatSnapshot(deviceId, string.Empty, string.Empty));

        public Task<EntryDecisionSnapshot> CheckEntryAsync(
            string workstationId,
            string? clientId,
            string? guestId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new EntryDecisionSnapshot(
                true,
                "allowed",
                null,
                clientId,
                null,
                null));

        public async IAsyncEnumerable<WorkstationCommandSnapshot> WatchCommandsAsync(
            string deviceId,
            CancellationToken cancellationToken = default)
        {
            await Task.CompletedTask;
            yield break;
        }

        public Task<WorkstationCommandSnapshot> AcknowledgeCommandAsync(
            string commandId,
            string deviceId,
            bool success,
            string message,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new WorkstationCommandSnapshot(
                commandId,
                string.Empty,
                string.Empty,
                "{}",
                string.Empty,
                string.Empty,
                message,
                string.Empty));

        public Task<SessionSnapshot> StartSessionAsync(
            string workstationId,
            string deviceId,
            string? clientId,
            string? guestName,
            string? reservationId,
            string idempotencyKey,
            CancellationToken cancellationToken = default,
            string? tariffId = null,
            int tariffQuantity = 1) =>
            Task.FromResult(new SessionSnapshot(
                string.Empty,
                workstationId,
                clientId,
                guestName,
                string.Empty,
                string.Empty,
                null,
                string.Empty,
                reservationId ?? string.Empty));

        public Task<SessionSnapshot> StopSessionAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new SessionSnapshot(
                sessionId,
                string.Empty,
                null,
                null,
                string.Empty,
                string.Empty,
                null,
                string.Empty,
                string.Empty));

        public Task<SessionSnapshot> GetSessionSnapshotAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new SessionSnapshot(
                sessionId,
                string.Empty,
                null,
                null,
                string.Empty,
                string.Empty,
                null,
                string.Empty,
                string.Empty,
                DeviceId: deviceId));

        public Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(
            string sessionId,
            string targetWorkstationId,
            string deviceId,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new SessionTransferOfferSnapshot(
                string.Empty,
                sessionId,
                string.Empty,
                deviceId,
                targetWorkstationId,
                string.Empty,
                "pending",
                false,
                null,
                string.Empty,
                string.Empty,
                null));

        public Task<SessionTransferOfferSnapshot> GetTransferOfferAsync(
            string offerId,
            string deviceId,
            string token,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new SessionTransferOfferSnapshot(
                offerId,
                string.Empty,
                string.Empty,
                string.Empty,
                deviceId,
                token,
                "pending",
                false,
                null,
                string.Empty,
                string.Empty,
                null));

        public Task<SessionTransferResultSnapshot> ConfirmTransferAsync(
            string offerId,
            string deviceId,
            string token,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new SessionTransferResultSnapshot(
                new SessionTransferOfferSnapshot(
                    offerId,
                    string.Empty,
                    string.Empty,
                    string.Empty,
                    deviceId,
                    token,
                    "confirmed",
                    false,
                    null,
                    string.Empty,
                    string.Empty,
                    string.Empty),
                new SessionSnapshot(
                    string.Empty,
                    string.Empty,
                    null,
                    null,
                    string.Empty,
                    string.Empty,
                    null,
                    string.Empty,
                    string.Empty,
                    DeviceId: deviceId)));

        public Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(
            string sessionId,
            string deviceId,
            IReadOnlyCollection<OfflineOperationSnapshot> operations,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(new OfflineBatchResultSnapshot(sessionId, Array.Empty<OfflineOperationResultSnapshot>(), null));

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
