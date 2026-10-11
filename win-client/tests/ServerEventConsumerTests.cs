using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts.Events.V2;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;
using Google.Protobuf;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ServerEventConsumerTests
{
    [Fact]
    public async Task ProcessesBalanceCreditBeforeAcknowledgingServerEvent()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger());
        var envelope = CreateServerBalanceCredit();
        var handler = new RecordingHttpHandler(envelope);
        var consumer = CreateConsumer(handler, coordinator);

        var result = await consumer.PollOnceAsync();
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(new V2ServerEventPollResult(1, 1, 0), result);
        Assert.Equal(600, persisted.Ledger.BalanceCents);
        Assert.Single(persisted.ClientInbox);
        Assert.Equal(1, handler.AcknowledgementCount);
        Assert.EndsWith("/api/events/server/00000000-0000-0000-0000-000000000302/acknowledge", handler.LastPostPath);
    }

    [Fact]
    public async Task DoesNotAcknowledgeEventForAnotherLocalSession()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger());
        var envelope = CreateServerBalanceCredit();
        envelope.SessionId = "00000000-0000-0000-0000-000000000099";
        var handler = new RecordingHttpHandler(envelope);
        var consumer = CreateConsumer(handler, coordinator);

        var result = await consumer.PollOnceAsync();
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(new V2ServerEventPollResult(1, 0, 1), result);
        Assert.Equal(100, persisted.Ledger.BalanceCents);
        Assert.Empty(persisted.ClientInbox);
        Assert.Equal(0, handler.AcknowledgementCount);
    }

    private static V2HttpServerEventConsumer CreateConsumer(
        RecordingHttpHandler handler,
        V2LocalLedgerCoordinator coordinator) =>
        new(
            new HttpClient(handler),
            new Uri("https://api.test/api/events/server"),
            new StaticTokenProvider(),
            new V2ServerEventProcessor(coordinator));

    private static V2LocalSessionLedger CreateLedger() =>
        V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: "device-01",
            zoneId: null,
            balanceCents: 100,
            debtLimitCents: 0,
            loginGrantRemainingMinutes: 0,
            packages: [],
            tariffs: []);

    private static EventEnvelope CreateServerBalanceCredit() => new()
    {
        EventId = "00000000-0000-0000-0000-000000000302",
        OperationId = "00000000-0000-0000-0000-000000000301",
        EventType = V2EventType.BalanceCreditApplied,
        SchemaVersion = 1,
        ProducerId = "server:deposit",
        ClientId = "00000000-0000-0000-0000-000000000001",
        SessionId = "00000000-0000-0000-0000-000000000002",
        DeviceId = "device-01",
        PayloadJson = "{\"amount_delta_cents\":500,\"currency\":\"RUB\",\"deposit_operation_id\":\"00000000-0000-0000-0000-000000000301\",\"payment_method_types\":[\"cash\"]}",
        PayloadHash = "993c7c3f88ebc77775035ec49b71aadb2fdad29e883d40804b0b347001d3767b",
    };

    private sealed class StaticTokenProvider : ITokenProvider
    {
        public ValueTask<string?> GetAccessTokenAsync(CancellationToken cancellationToken = default) =>
            ValueTask.FromResult<string?>("device-token");
    }

    private sealed class RecordingHttpHandler : HttpMessageHandler
    {
        private readonly byte[] _payload;

        public RecordingHttpHandler(EventEnvelope envelope) => _payload = envelope.ToByteArray();

        public int AcknowledgementCount { get; private set; }
        public string LastPostPath { get; private set; } = string.Empty;

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            if (request.Method == HttpMethod.Get)
            {
                var body = new
                {
                    events = new[]
                    {
                        new
                        {
                            event_id = "00000000-0000-0000-0000-000000000302",
                            operation_id = "00000000-0000-0000-0000-000000000301",
                            topic = "v2.server-events",
                            payload_base64 = Convert.ToBase64String(_payload),
                        },
                    },
                };
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = JsonContent.Create(body),
                });
            }

            AcknowledgementCount++;
            LastPostPath = request.RequestUri?.AbsolutePath ?? string.Empty;
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        }
    }

    private sealed class InMemoryLedgerStore : IV2LocalLedgerStore
    {
        private V2LocalLedgerStorageSnapshot? _snapshot;

        public Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
            CancellationToken cancellationToken = default) =>
            Task.FromResult(_snapshot);

        public Task WriteAsync(
            V2LocalLedgerStorageSnapshot snapshot,
            CancellationToken cancellationToken = default)
        {
            _snapshot = snapshot;
            return Task.CompletedTask;
        }
    }
}
