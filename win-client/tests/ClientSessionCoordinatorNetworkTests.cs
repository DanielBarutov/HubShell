using System.Runtime.CompilerServices;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientSessionCoordinatorNetworkTests
{
    [Fact]
    public async Task HeartbeatNetworkFailureOnlyMarksReconnectingAndDoesNotStopSession()
    {
        using var cancellation = new CancellationTokenSource();
        var states = new List<ClientConnectionState>();
        var backend = new NetworkBoundaryBackend
        {
            SendHeartbeat = _ =>
            {
                cancellation.Cancel();
                throw new InvalidOperationException("network is unavailable");
            },
        };
        await using var coordinator = new ClientSessionCoordinator(backend);

        try
        {
            await coordinator.RunWorkstationHeartbeatLoopAsync(
                "device-1",
                "test",
                Array.Empty<string>(),
                onConnectionStateChanged: states.Add,
                cancellationToken: cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            // The test cancels the reconnect loop after observing the network failure.
        }

        Assert.Equal(new[] { ClientConnectionState.Reconnecting }, states);
        Assert.Equal(0, backend.StopSessionCalls);
    }

    [Fact]
    public async Task ServerStopCommandIsExecutedAndAcknowledgedAfterReconnect()
    {
        using var cancellation = new CancellationTokenSource();
        var command = new WorkstationCommandSnapshot(
            "command-stop-1",
            "workstation-1",
            "session.stop",
            "{\"session_id\":\"session-1\",\"reason\":\"balance_exhausted\"}",
            "auto-meter:session-1:session.stop",
            "queued",
            string.Empty,
            DateTimeOffset.UtcNow.AddMinutes(1).ToString("O"));
        var backend = new NetworkBoundaryBackend
        {
            Commands = new[] { command },
            OnAcknowledged = () => cancellation.Cancel(),
        };
        var executor = new RecordingCommandExecutor();
        await using var coordinator = new ClientSessionCoordinator(backend);

        await coordinator.RunCommandLoopAsync("device-1", executor, cancellation.Token);

        Assert.Equal(new[] { command.Id }, executor.ExecutedCommandIds);
        Assert.Single(backend.Acknowledgements);
        Assert.Equal(command.Id, backend.Acknowledgements[0].CommandId);
        Assert.True(backend.Acknowledgements[0].Success);
        Assert.Equal(1, executor.ExecutionCount);
    }

    private sealed class RecordingCommandExecutor : IWorkstationCommandExecutor
    {
        public List<string> ExecutedCommandIds { get; } = [];

        public int ExecutionCount { get; private set; }

        public Task<CommandExecutionResult> ExecuteAsync(
            WorkstationCommandSnapshot command,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            ExecutedCommandIds.Add(command.Id);
            ExecutionCount++;
            return Task.FromResult(new CommandExecutionResult(true, "Команда выполнена"));
        }
    }

    private sealed class NetworkBoundaryBackend : IBackendClient
    {
        public Func<CancellationToken, Task<WorkstationHeartbeatSnapshot>>? SendHeartbeat { get; init; }

        public IReadOnlyList<WorkstationCommandSnapshot> Commands { get; init; } = [];

        public Action? OnAcknowledged { get; init; }

        public int StopSessionCalls { get; private set; }

        public List<CommandAcknowledgement> Acknowledgements { get; } = [];

        public Task<ClientConnectionSnapshot> CheckConnectionAsync(
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<WorkstationHeartbeatSnapshot> SendHeartbeatAsync(
            string deviceId,
            string clientVersion,
            IReadOnlyCollection<string> capabilities,
            CancellationToken cancellationToken = default) =>
            SendHeartbeat is not null
                ? SendHeartbeat(cancellationToken)
                : throw new NotSupportedException();

        public async IAsyncEnumerable<WorkstationCommandSnapshot> WatchCommandsAsync(
            string deviceId,
            [EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            foreach (var command in Commands)
            {
                yield return command;
            }

            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
        }

        public Task<WorkstationCommandSnapshot> AcknowledgeCommandAsync(
            string commandId,
            string deviceId,
            bool success,
            string message,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Acknowledgements.Add(new CommandAcknowledgement(commandId, success, message));
            OnAcknowledged?.Invoke();
            return Task.FromResult(new WorkstationCommandSnapshot(
                commandId,
                string.Empty,
                string.Empty,
                "{}",
                string.Empty,
                success ? "acknowledged" : "failed",
                message,
                string.Empty));
        }

        public Task<ClientPortalAuthenticationSnapshot> RegisterAsync(
            string nickname,
            string phone,
            string password,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalAuthenticationSnapshot> LoginAsync(
            string identifier,
            string password,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalAuthenticationSnapshot?> ResumeAsync(
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalAuthenticationSnapshot> ChangePasswordAsync(
            string newPassword,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalSnapshot> RefreshAsync(
            string deviceId,
            int limit = 50,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalSnapshot> ActivateEntitlementAsync(
            string deviceId,
            string entitlementId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<ClientPortalSnapshot> PurchaseEntitlementAsync(
            string deviceId,
            string tariffId,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public void Logout() => throw new NotSupportedException();

        public Task<EntryDecisionSnapshot> CheckEntryAsync(
            string workstationId,
            string? clientId,
            string? guestId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

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
            throw new NotSupportedException();

        public Task<SessionSnapshot> StopSessionAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default)
        {
            StopSessionCalls++;
            throw new InvalidOperationException("StopSession must not be called for a network failure");
        }

        public Task<SessionSnapshot> GetSessionSnapshotAsync(
            string sessionId,
            string deviceId,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<SessionTransferOfferSnapshot> CreateTransferOfferAsync(
            string sessionId,
            string? targetWorkstationId,
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

        public Task<SessionTransferResultSnapshot> ClaimPendingTransferAsync(
            string clientId,
            string workstationId,
            string deviceId,
            string idempotencyKey,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public Task<OfflineBatchResultSnapshot> ReplayOfflineBatchAsync(
            string sessionId,
            string deviceId,
            IReadOnlyCollection<OfflineOperationSnapshot> operations,
            CancellationToken cancellationToken = default) =>
            throw new NotSupportedException();

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed record CommandAcknowledgement(string CommandId, bool Success, string Message);
}
