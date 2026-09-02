using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class WindowsCommandExecutorTests
{
    [Fact]
    public async Task DisplayLockLocksClientShellWithoutInvokingWindowsLogon()
    {
        var lockCalls = 0;
        var executor = new WindowsCommandExecutor(
            displayLockConsumer: () => lockCalls++);
        var command = new WorkstationCommandSnapshot(
            "command-1",
            "workstation-1",
            "display.lock",
            "{}",
            "lock-1",
            string.Empty,
            string.Empty,
            string.Empty);

        var result = await executor.ExecuteAsync(command);

        Assert.True(result.Success);
        Assert.Equal(1, lockCalls);
        Assert.Contains("оболочка", result.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task DisplayLockFailsClosedWhenClientShellIsNotConnected()
    {
        var executor = new WindowsCommandExecutor();
        var command = new WorkstationCommandSnapshot(
            "command-1",
            "workstation-1",
            "display.lock",
            "{}",
            "lock-1",
            string.Empty,
            string.Empty,
            string.Empty);

        var result = await executor.ExecuteAsync(command);

        Assert.False(result.Success);
        Assert.Contains("не подключена", result.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task StartSessionRequiresAuthoritativeEntryDecision()
    {
        var gateway = new EntryDecisionGateway(new EntryDecisionSnapshot(
            false,
            "reservation_client_mismatch",
            "reservation-1",
            "client-1",
            null,
            null));
        var executor = new WindowsCommandExecutor("device-1", gateway);
        var command = new WorkstationCommandSnapshot(
            "command-1",
            "workstation-1",
            "session.start",
            "{\"client_id\":\"client-1\"}",
            "start-1",
            string.Empty,
            string.Empty,
            string.Empty);

        var result = await executor.ExecuteAsync(command);

        Assert.False(result.Success);
        Assert.Contains("reservation_client_mismatch", result.Message);
        Assert.Equal(0, gateway.StartCalls);
    }

    private sealed class EntryDecisionGateway : IWorkstationSessionGateway
    {
        private readonly EntryDecisionSnapshot _decision;

        public EntryDecisionGateway(EntryDecisionSnapshot decision) => _decision = decision;

        public int StartCalls { get; private set; }

        public Task<EntryDecisionSnapshot> CheckEntryAsync(
            string workstationId,
            string? clientId,
            string? guestId,
            CancellationToken cancellationToken = default) => Task.FromResult(_decision);

        public Task<SessionSnapshot> StartSessionAsync(
            string workstationId,
            string deviceId,
            string? clientId,
            string? guestName,
            string? reservationId,
            string idempotencyKey,
            CancellationToken cancellationToken = default,
            string? tariffId = null,
            int tariffQuantity = 1)
        {
            StartCalls++;
            return Task.FromResult(EmptySession(workstationId, deviceId));
        }

        public Task<SessionSnapshot> StopSessionAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(EmptySession(string.Empty, deviceId));

        public Task<SessionSnapshot> GetSessionSnapshotAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            Task.FromResult(EmptySession(string.Empty, deviceId));

        public Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(
            string sessionId,
            string targetWorkstationId,
            string deviceId,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<SessionTransferOfferSnapshot> GetTransferOfferAsync(
            string offerId,
            string deviceId,
            string token,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<SessionTransferResultSnapshot> ConfirmTransferAsync(
            string offerId,
            string deviceId,
            string token,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(
            string sessionId,
            string deviceId,
            IReadOnlyCollection<OfflineOperationSnapshot> operations,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        private static SessionSnapshot EmptySession(string workstationId, string deviceId) =>
            new(
                string.Empty,
                workstationId,
                null,
                null,
                string.Empty,
                string.Empty,
                null,
                string.Empty,
                string.Empty,
                DeviceId: deviceId);
    }
}
