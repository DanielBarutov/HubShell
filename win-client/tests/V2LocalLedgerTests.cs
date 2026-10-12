using GameClub.Client.Domain;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts.Events.V2;
using GameClub.Client.Infrastructure;
using Google.Protobuf;
using Google.Protobuf.WellKnownTypes;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2LocalLedgerTests
{
    [Fact]
    public async Task SignedPurchaseAddsNewTariffAtNegativeBalanceWithoutReplacingLedger()
    {
        var original = CreateLedger(balanceCents: -500, loginGrantMinutes: 0) with { DebtLimitCents = 1_000 };
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(original);
        var pending = await coordinator.BeginPortalPackagePurchaseAsync("new-tariff");
        var packageId = Guid.NewGuid().ToString();
        var receipt = original with
        {
            SnapshotId = Guid.NewGuid(), BalanceCents = 99_999,
            Packages = [new(packageId, "new-tariff", null, 2, V2LocalPackageStatus.Active)],
            Tariffs = [new("new-tariff", "New 2 minutes", null, 2, 100, 0, true)],
        };
        await Assert.ThrowsAsync<InvalidOperationException>(() => coordinator.CompletePortalPackagePurchaseAsync(
            "new-tariff", DateTimeOffset.UtcNow, purchasedPackage: receipt with { SessionId = Guid.NewGuid() }));
        Assert.Equal(original, await coordinator.ReadLedgerAsync());
        var purchase = await coordinator.CompletePortalPackagePurchaseAsync(
            "new-tariff", DateTimeOffset.UtcNow, purchasedPackage: receipt);
        Assert.Equal(-600, purchase.Ledger.BalanceCents);
        Assert.Equal(original.SnapshotId, purchase.Ledger.SnapshotId);
        Assert.Equal(1_000, purchase.Ledger.DebtLimitCents);
        Assert.Equal(packageId, Assert.Single(purchase.Ledger.Packages).Id);
        using var payload = System.Text.Json.JsonDocument.Parse(Assert.Single(purchase.OutboxFacts).PayloadJson);
        Assert.Equal(pending.IdempotencyKey, payload.RootElement.GetProperty("purchase_idempotency_key").GetString());
        var minute = await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        Assert.Equal(1, Assert.Single(minute.Ledger.Packages).RemainingMinutes);
        Assert.Equal(-600, minute.Ledger.BalanceCents);
        Assert.Null(await coordinator.ReadPendingPortalPackagePurchaseAsync());
    }

    [Fact]
    public void ConsumesLoginGrantBeforePackageAndBalance()
    {
        var ledger = CreateLedger(loginGrantMinutes: 2);

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.Parse("2026-09-27T12:00:00Z"));

        Assert.Equal(1, transition.Ledger.LoginGrantRemainingMinutes);
        Assert.Equal(1_000, transition.Ledger.BalanceCents);
        var fact = Assert.Single(transition.OutboxFacts);
        Assert.Equal("login_grant_consumed", fact.EventType);
        Assert.Equal(1, fact.Sequence);
        Assert.Null(fact.PreviousHash);
    }

    [Fact]
    public void GuestLedgerConsumesLocallyWithoutClientProfileFacts()
    {
        var ledger = CreateLedger(
            balanceCents: 0,
            packages: [new V2LocalPackage("guest-package", "guest", null, 1, V2LocalPackageStatus.Active)])
            with
        {
            ClientId = Guid.Empty,
            GuestName = "Гость",
            GuestPaymentId = Guid.NewGuid(),
        };

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        Assert.Empty(transition.OutboxFacts);
        Assert.Equal(0, Assert.Single(transition.Ledger.Packages).RemainingMinutes);
        Assert.Equal(V2LocalSessionStatus.Active, transition.Ledger.Status);
    }

    [Fact]
    public void ActivatesQueuedPackageAndConsumesItBeforePerMinuteDebit()
    {
        var ledger = CreateLedger(
            packages:
            [
                new V2LocalPackage("package-1", "package", null, 1, V2LocalPackageStatus.Queued),
            ]);

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        var package = Assert.Single(transition.Ledger.Packages);
        Assert.Equal(V2LocalPackageStatus.Exhausted, package.Status);
        Assert.Equal(0, package.RemainingMinutes);
        Assert.Equal("package_consumed", Assert.Single(transition.OutboxFacts).EventType);
        Assert.Equal(1_000, transition.Ledger.BalanceCents);
    }

    [Fact]
    public void DebitsPerMinuteOnlyInsideKnownDebtLimit()
    {
        var ledger = CreateLedger(balanceCents: 20, debtLimitCents: 50);

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        Assert.Equal(-40, transition.Ledger.BalanceCents);
        Assert.Equal("per_minute_debit", Assert.Single(transition.OutboxFacts).EventType);

        var exhausted = V2LocalLedgerEngine.ConsumeOneMinute(
            transition.Ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        Assert.Equal(V2LocalSessionStatus.Exhausted, exhausted.Ledger.Status);
        Assert.True(exhausted.LockWorkstation);
        Assert.Equal("session_stopped", Assert.Single(exhausted.OutboxFacts).EventType);
    }

    [Fact]
    public void PurchasesKnownPackageLocallyAndAddsItToQueue()
    {
        var ledger = CreateLedger(balanceCents: 1_000);

        var transition = V2LocalLedgerEngine.PurchasePackage(
            ledger,
            Guid.NewGuid(),
            "package",
            DateTimeOffset.UtcNow);

        Assert.Equal(700, transition.Ledger.BalanceCents);
        var package = Assert.Single(transition.Ledger.Packages);
        Assert.Equal("package", package.TariffId);
        Assert.Equal(30, package.RemainingMinutes);
        Assert.Equal(V2LocalPackageStatus.Queued, package.Status);
        Assert.Equal("package_purchased", Assert.Single(transition.OutboxFacts).EventType);
    }

    [Fact]
    public void ServerStopStopsBillingAndBurnsTheActivePackageWithoutClientStopFact()
    {
        var ledger = CreateLedger(
            packages:
            [
                new V2LocalPackage("active", "package", null, 12, V2LocalPackageStatus.Active),
                new V2LocalPackage("queued", "package", null, 30, V2LocalPackageStatus.Queued),
            ]);

        var transition = V2LocalLedgerEngine.ApplyServerStop(ledger);
        var repeated = V2LocalLedgerEngine.ApplyServerStop(transition.Ledger);

        Assert.Equal(V2LocalSessionStatus.Stopped, transition.Ledger.Status);
        Assert.True(transition.LockWorkstation);
        Assert.Empty(transition.OutboxFacts);
        Assert.Equal(V2LocalPackageStatus.Burned,
            transition.Ledger.Packages.Single(item => item.Id == "active").Status);
        Assert.Equal(V2LocalPackageStatus.Queued,
            transition.Ledger.Packages.Single(item => item.Id == "queued").Status);
        Assert.True(repeated.IsDuplicate);
        Assert.Equal(transition.Ledger, repeated.Ledger);
    }

    [Fact]
    public async Task NextSessionPreservesPendingFactsFromTheCompletedSession()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        var previous = CreateLedger();
        var next = CreateLedger() with
        {
            SnapshotId = Guid.NewGuid(),
            SessionId = Guid.NewGuid(),
        };
        await coordinator.InitializeAsync(previous);
        await coordinator.StopEarlyAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var pending = await coordinator.ReadPendingOutboxAsync();

        await coordinator.InitializeNextSessionAsync(next);

        var snapshot = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());
        Assert.Equal(next.SessionId, snapshot.Ledger.SessionId);
        Assert.Equal(pending, snapshot.PendingOutbox);
    }

    [Fact]
    public async Task PortalPackagePurchaseKeepsOneIdempotencyKeyUntilLocalCompletion()
    {
        var store = new InMemoryLedgerStore();
        var ledger = new V2LocalLedgerCoordinator(store);
        await ledger.InitializeAsync(CreateLedger(balanceCents: 310));

        var pending = await ledger.BeginPortalPackagePurchaseAsync("package");
        await ledger.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var recoveredCoordinator = new V2LocalLedgerCoordinator(store);
        var retried = await recoveredCoordinator.BeginPortalPackagePurchaseAsync("package");
        Assert.Equal(pending, retried);

        var transition = await recoveredCoordinator.CompletePortalPackagePurchaseAsync(
            "package",
            DateTimeOffset.UtcNow);
        var snapshot = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(-50, transition.Ledger.BalanceCents);
        Assert.Equal(-50, snapshot.Ledger.BalanceCents);
        Assert.Single(snapshot.Ledger.Packages);
        Assert.Equal(
            ["per_minute_debit", "package_purchased"],
            snapshot.PendingOutbox.Select(fact => fact.EventType));
        Assert.Null(snapshot.PendingPortalPackagePurchase);
    }

    [Fact]
    public void EarlyExitBurnsOnlyActivePackageAndKeepsQueuedPackages()
    {
        var ledger = CreateLedger(
            packages:
            [
                new V2LocalPackage("active", "package", null, 12, V2LocalPackageStatus.Active),
                new V2LocalPackage("queued", "package", null, 30, V2LocalPackageStatus.Queued),
            ]);

        var transition = V2LocalLedgerEngine.StopEarly(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        Assert.Equal(V2LocalSessionStatus.Stopped, transition.Ledger.Status);
        Assert.True(transition.LockWorkstation);
        Assert.Equal(
            ["package_burned", "session_stopped"],
            transition.OutboxFacts.Select(item => item.EventType));
        Assert.Equal(
            V2LocalPackageStatus.Burned,
            transition.Ledger.Packages.Single(item => item.Id == "active").Status);
        var queued = transition.Ledger.Packages.Single(item => item.Id == "queued");
        Assert.Equal(V2LocalPackageStatus.Queued, queued.Status);
        Assert.Equal(30, queued.RemainingMinutes);
    }

    [Fact]
    public void EarlyExitBurnsActiveLoginGrantWithDedicatedFact()
    {
        var ledger = CreateLedger(loginGrantMinutes: 5);

        var transition = V2LocalLedgerEngine.StopEarly(
            ledger,
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);

        Assert.Equal(0, transition.Ledger.LoginGrantRemainingMinutes);
        Assert.Equal(
            ["login_grant_burned", "session_stopped"],
            transition.OutboxFacts.Select(item => item.EventType));
    }

    [Fact]
    public void RepeatedLocalActionDoesNotCreateSecondDebit()
    {
        var actionId = Guid.NewGuid();
        var first = V2LocalLedgerEngine.ConsumeOneMinute(
            CreateLedger(), actionId, DateTimeOffset.UtcNow);

        var duplicate = V2LocalLedgerEngine.ConsumeOneMinute(
            first.Ledger, actionId, DateTimeOffset.UtcNow);

        Assert.True(duplicate.IsDuplicate);
        Assert.Equal(first.Ledger, duplicate.Ledger);
        Assert.Empty(duplicate.OutboxFacts);
    }

    [Fact]
    public void AppliesServerBalanceDeltaOnceWithoutReplacingPendingLocalBalance()
    {
        var afterDebit = V2LocalLedgerEngine.ConsumeOneMinute(
            CreateLedger(balanceCents: 100), Guid.NewGuid(), DateTimeOffset.UtcNow).Ledger;
        var depositOperation = Guid.NewGuid();

        var credited = V2LocalLedgerEngine.ApplyBalanceCredit(afterDebit, depositOperation, 500);
        var duplicate = V2LocalLedgerEngine.ApplyBalanceCredit(credited.Ledger, depositOperation, 500);

        Assert.Equal(540, credited.Ledger.BalanceCents);
        Assert.True(duplicate.IsDuplicate);
        Assert.Equal(540, duplicate.Ledger.BalanceCents);
    }

    [Fact]
    public async Task CoordinatorPersistsDebitAndOutboxAsOneLogicalChange()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger());

        var transition = await coordinator.ConsumeOneMinuteAsync(
            Guid.NewGuid(),
            DateTimeOffset.UtcNow);
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(940, persisted.Ledger.BalanceCents);
        Assert.Equal(transition.OutboxFacts, persisted.PendingOutbox);

        await coordinator.AcknowledgeOutboxAsync([transition.OutboxFacts[0].EventId]);

        Assert.Empty(await coordinator.ReadPendingOutboxAsync());
    }

    [Fact]
    public async Task CoordinatorPersistsServerCreditWithoutAddingItToClientOutbox()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(balanceCents: 100));

        var transition = await coordinator.ApplyBalanceCreditAsync(
            Guid.NewGuid(),
            Guid.NewGuid(),
            500);
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(600, transition.Ledger.BalanceCents);
        Assert.Equal(600, persisted.Ledger.BalanceCents);
        Assert.Empty(persisted.PendingOutbox);
        Assert.Single(persisted.ClientInbox);
    }

    [Fact]
    public async Task CoordinatorAcceptsSameServerCreditOnlyOnceThroughClientInbox()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(balanceCents: 100));
        var eventId = Guid.NewGuid();
        var operationId = Guid.NewGuid();

        var first = await coordinator.ApplyBalanceCreditAsync(eventId, operationId, 500);
        var duplicate = await coordinator.ApplyBalanceCreditAsync(eventId, operationId, 500);

        Assert.Equal(600, first.Ledger.BalanceCents);
        Assert.True(duplicate.IsDuplicate);
        Assert.Equal(600, duplicate.Ledger.BalanceCents);
        Assert.Empty(await coordinator.ReadPendingOutboxAsync());
    }

    [Fact]
    public async Task ServerEventProcessorChecksTargetAndPersistsBalanceCreditBeforeAcknowledgement()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(balanceCents: 100));
        var processor = new V2ServerEventProcessor(coordinator);
        var message = CreateServerBalanceCredit();

        var accepted = await processor.ProcessAsync(message);
        var duplicate = await processor.ProcessAsync(message);
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(V2EventProcessingStatus.Accepted, accepted.Status);
        Assert.Equal(V2EventProcessingStatus.Duplicate, duplicate.Status);
        Assert.Equal(600, persisted.Ledger.BalanceCents);
        Assert.Single(persisted.ClientInbox);
    }

    [Fact]
    public async Task ServerEventProcessorRejectsAnotherSessionWithoutChangingLedger()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(balanceCents: 100));
        var processor = new V2ServerEventProcessor(coordinator);
        var message = CreateServerBalanceCredit();
        message.SessionId = "00000000-0000-0000-0000-000000000099";

        var rejected = await processor.ProcessAsync(message);
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(V2EventProcessingStatus.Rejected, rejected.Status);
        Assert.Equal("target_mismatch", rejected.ReasonCode);
        Assert.Equal(100, persisted.Ledger.BalanceCents);
        Assert.Empty(persisted.ClientInbox);
        Assert.NotNull(persisted.ServerEventIssues);
        var issue = Assert.Single(persisted.ServerEventIssues!);
        Assert.Equal("target_mismatch", issue.ReasonCode);
        Assert.Equal(1, issue.Attempts);
    }

    [Fact]
    public async Task ServerEventProcessorRejectsChangedPayloadEvenWhenTargetMatches()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(balanceCents: 100));
        var processor = new V2ServerEventProcessor(coordinator);
        var message = CreateServerBalanceCredit();
        message.PayloadJson = "{\"amount_delta_cents\":900,\"currency\":\"RUB\",\"deposit_operation_id\":\"00000000-0000-0000-0000-000000000301\",\"payment_method_types\":[\"cash\"]}";

        var rejected = await processor.ProcessAsync(message);
        var persisted = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());

        Assert.Equal(V2EventProcessingStatus.Rejected, rejected.Status);
        Assert.Equal("invalid_server_event", rejected.ReasonCode);
        Assert.Equal(100, persisted.Ledger.BalanceCents);
        Assert.Empty(persisted.ClientInbox);
    }

    [Fact]
    public async Task OutboxPublisherAcknowledgesOnlyFactsConfirmedByTransportInOrder()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(loginGrantMinutes: 2));
        await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var transport = new RecordingClientPublisher(failOnCall: 2);
        var publisher = new V2ClientOutboxPublisher(coordinator, transport);

        var published = await publisher.PublishPendingAsync();

        Assert.Equal(1, published);
        Assert.Equal(2, transport.Facts.Count);
        var pending = await coordinator.ReadPendingOutboxAsync();
        Assert.Single(pending);
        Assert.Equal(transport.Facts[1].EventId, pending[0].EventId);
    }

    [Fact]
    public async Task OutboxPublisherReportsTransportFailureWithoutDroppingTheFact()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(loginGrantMinutes: 1));
        await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var transport = new RecordingClientPublisher(failOnCall: 1);

        var result = await new V2ClientOutboxPublisher(coordinator, transport)
            .TryPublishPendingAsync();

        Assert.False(result.IsSuccessful);
        Assert.Equal(0, result.PublishedCount);
        Assert.Equal(1, result.PendingCount);
        Assert.Single(await coordinator.ReadPendingOutboxAsync());
    }

    [Fact]
    public async Task OutboxWorkerBacksOffAndRetriesTheSameFactInOrder()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(loginGrantMinutes: 1));
        await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var transport = new FlakyClientPublisher(failuresBeforeSuccess: 2);
        var publisher = new V2ClientOutboxPublisher(coordinator, transport);
        var delays = new List<TimeSpan>();
        using var cancellation = new CancellationTokenSource();
        var worker = new V2ClientOutboxWorker(
            publisher,
            pollInterval: TimeSpan.FromSeconds(5),
            initialRetryDelay: TimeSpan.FromSeconds(1),
            maximumRetryDelay: TimeSpan.FromSeconds(4),
            delay: (delay, _) =>
            {
                delays.Add(delay);
                if (delays.Count == 3)
                {
                    cancellation.Cancel();
                }
                return Task.CompletedTask;
            });

        await worker.RunAsync(cancellation.Token);

        Assert.Equal(
            [TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2), TimeSpan.FromSeconds(5)],
            delays);
        Assert.Equal(3, transport.Attempts);
        Assert.Empty(await coordinator.ReadPendingOutboxAsync());
    }

    [Fact]
    public async Task RecoveryReadsLedgerAndOutboxTogetherAndRejectsAnotherDevice()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        var ledger = CreateLedger(loginGrantMinutes: 1);
        await coordinator.InitializeAsync(ledger);
        await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), DateTimeOffset.UtcNow);
        var recovery = new V2LocalLedgerRecoveryCoordinator(coordinator);

        var result = await recovery.RecoverAsync("device-01");

        Assert.Equal(V2LedgerRecoveryState.Active, result.State);
        Assert.Equal(1, result.PendingOutboxCount);
        Assert.Equal(ledger.SessionId, result.Ledger!.SessionId);
        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            recovery.RecoverAsync("other-device"));
    }

    [Fact]
    public async Task RecoveryClearsOnlyKnownServerEventsThatHaveNoClientHandler()
    {
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(CreateLedger(loginGrantMinutes: 1));
        var snapshot = Assert.IsType<V2LocalLedgerStorageSnapshot>(await store.ReadAsync());
        await store.WriteAsync(snapshot with
        {
            ServerEventIssues =
            [
                new(
                    Guid.NewGuid().ToString(),
                    Guid.NewGuid().ToString(),
                    "invalid_server_event",
                    "Для локального баланса разрешён только BalanceCreditApplied.",
                    DateTimeOffset.UtcNow,
                    DateTimeOffset.UtcNow,
                    1),
                new(
                    Guid.NewGuid().ToString(),
                    Guid.NewGuid().ToString(),
                    "target_mismatch",
                    "Сообщение предназначено другой V2-сессии.",
                    DateTimeOffset.UtcNow,
                    DateTimeOffset.UtcNow,
                    1),
            ],
        });

        var recovery = await new V2LocalLedgerRecoveryCoordinator(coordinator)
            .RecoverAsync("device-01");
        var remainingIssues = (await coordinator.ReadSnapshotAsync())!.ServerEventIssues!;

        Assert.Equal(1, recovery.ServerEventIssueCount);
        Assert.Equal("target_mismatch", Assert.Single(remainingIssues).ReasonCode);
    }

    [Fact]
    public void SerializerPreservesFullImmutableV2Envelope()
    {
        var fact = Assert.Single(V2LocalLedgerEngine.ConsumeOneMinute(
            CreateLedger(), Guid.NewGuid(), DateTimeOffset.UtcNow).OutboxFacts);

        var message = V2EventProtobufSerializer.Serialize(fact);

        Assert.Equal(fact.EventId.ToString(), message.EventId);
        Assert.Equal(fact.OperationId.ToString(), message.OperationId);
        Assert.Equal(V2EventType.PerMinuteDebit, message.EventType);
        Assert.Equal(fact.Sequence, checked((long)message.Sequence));
        Assert.Equal(fact.PayloadJson, message.PayloadJson);
        Assert.Equal(fact.PayloadHash, message.PayloadHash);
        Assert.Equal(fact.Traceparent, message.Traceparent);
        Assert.True(message.HasCausationId);
        Assert.False(message.HasPreviousHash);
    }

    [Fact]
    public void SignedSnapshotMustPassVerificationBeforeCreatingLedger()
    {
        var payload = new OfflineSessionSnapshotPayload
        {
            SnapshotId = Guid.NewGuid().ToString(),
            SchemaVersion = 1,
            SnapshotVersion = 1,
            IssuedAt = Timestamp.FromDateTime(DateTime.UtcNow),
            ClientId = Guid.NewGuid().ToString(),
            SessionId = Guid.NewGuid().ToString(),
            DeviceId = "device-01",
            BalanceCents = 1_000,
            DebtLimitCents = 0,
            LoginGrantRemainingMinutes = 5,
            PolicyVersion = "2026-09-27",
        };
        var signingBytes = V2OfflineSessionSnapshotReader.SerializeDeterministic(payload);
        var signed = new SignedOfflineSessionSnapshot
        {
            Payload = payload,
            SigningKeyId = "club-key-1",
            Signature = ByteString.CopyFrom([1, 2, 3]),
        };
        var verifier = new SnapshotVerifier(signingBytes, accepts: true);

        var ledger = V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(signed, verifier);

        Assert.Equal(payload.SnapshotId, ledger.SnapshotId.ToString());
        Assert.Equal(5, ledger.LoginGrantRemainingMinutes);
        Assert.Equal(signingBytes, verifier.Payload.ToArray());
    }

    [Fact]
    public void InvalidSnapshotSignatureDoesNotCreateLedger()
    {
        var signed = new SignedOfflineSessionSnapshot
        {
            Payload = new OfflineSessionSnapshotPayload(),
            SigningKeyId = "club-key-1",
            Signature = ByteString.CopyFrom([1]),
        };

        Assert.Throws<InvalidOperationException>(() =>
            V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(
                signed,
                new SnapshotVerifier(Array.Empty<byte>(), accepts: false)));
    }

    [Fact]
    public void GuestAccessSnapshotCreatesGuestLedgerWithoutClientBalance()
    {
        var payload = new GuestSessionAccessPayload
        {
            GrantId = Guid.NewGuid().ToString(),
            SchemaVersion = 1,
            IssuedAt = Timestamp.FromDateTime(DateTime.UtcNow),
            ExpiresAt = Timestamp.FromDateTime(DateTime.UtcNow.AddMinutes(10)),
            PaymentId = Guid.NewGuid().ToString(),
            SessionId = Guid.NewGuid().ToString(),
            DeviceId = "guest-device",
            GuestName = "Гость",
            TariffId = Guid.NewGuid().ToString(),
            DurationMinutes = 60,
            TariffQuantity = 2,
        };
        var signingBytes = V2OfflineSessionSnapshotReader.SerializeDeterministic(payload);
        var signed = new SignedGuestSessionAccess
        {
            Payload = payload,
            SigningKeyId = "club-key-1",
            Signature = ByteString.CopyFrom([1, 2, 3]),
        };

        var ledger = V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(
            signed,
            new SnapshotVerifier(signingBytes, accepts: true),
            "guest-device");

        Assert.True(ledger.IsGuest);
        Assert.Equal(Guid.Parse(payload.PaymentId), ledger.GuestPaymentId);
        Assert.Equal(120, Assert.Single(ledger.Packages).RemainingMinutes);
        Assert.Equal(0, ledger.BalanceCents);
    }

    [Fact]
    public void GuestAdditionSignatureIsBoundToActiveSession()
    {
        var sessionId = Guid.NewGuid();
        var payload = new GuestSessionAccessPayload
        {
            GrantId = Guid.NewGuid().ToString(), SchemaVersion = 2,
            IssuedAt = Timestamp.FromDateTime(DateTime.UtcNow),
            ExpiresAt = Timestamp.FromDateTime(DateTime.UtcNow.AddMinutes(10)),
            PaymentId = Guid.NewGuid().ToString(), SessionId = sessionId.ToString(),
            DeviceId = "guest-device", GuestName = "Гость", TariffId = "second",
            TariffName = "Второй пакет", DurationMinutes = 30, TariffQuantity = 1,
        };
        var bytes = V2OfflineSessionSnapshotReader.SerializeDeterministic(payload);
        var signed = new SignedGuestSessionAccess
        {
            Payload = payload, SigningKeyId = "club-key-1",
            Signature = ByteString.CopyFrom([1, 2, 3]),
        };
        var verifier = new SnapshotVerifier(bytes, accepts: true);
        var addition = V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(
            signed, verifier, "guest-device", sessionId);
        Assert.Equal(30, Assert.Single(addition.Packages).RemainingMinutes);
        Assert.Equal("Второй пакет", Assert.Single(addition.Tariffs).Name);
        Assert.Throws<InvalidOperationException>(() =>
            V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(signed, verifier, "guest-device"));
        Assert.Throws<InvalidOperationException>(() =>
            V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(
                signed, verifier, "guest-device", Guid.NewGuid()));
        Assert.Throws<InvalidOperationException>(() =>
            V2OfflineSessionSnapshotReader.VerifyAndCreateGuestLedger(
                signed, new SnapshotVerifier(bytes, accepts: false), "guest-device", sessionId));
    }

    [Fact]
    public void Ed25519VerifierAcceptsKnownClubKeyAndRejectsUnknownOrChangedData()
    {
        var verifier = new V2Ed25519OfflineSnapshotSignatureVerifier(
            new Dictionary<string, string>
            {
                ["club-key-1"] = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
            });
        var signature = Convert.FromHexString(
            "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
            + "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b");

        Assert.True(verifier.Verify("club-key-1", Array.Empty<byte>(), signature));
        Assert.False(verifier.Verify("club-key-2", Array.Empty<byte>(), signature));
        Assert.False(verifier.Verify("club-key-1", new byte[] { 1 }, signature));
    }

    [Fact]
    public void Ed25519VerifierAcceptsDeterministicSnapshotSignedByPythonServer()
    {
        var payload = new OfflineSessionSnapshotPayload
        {
            SnapshotId = "00000000-0000-0000-0000-000000000010",
            SchemaVersion = 1,
            SnapshotVersion = 7,
            IssuedAt = Timestamp.FromDateTime(DateTime.Parse("2026-09-27T12:00:00Z").ToUniversalTime()),
            ClientId = "00000000-0000-0000-0000-000000000001",
            SessionId = "00000000-0000-0000-0000-000000000002",
            DeviceId = "device-01",
            WorkstationZoneId = "vip",
            BalanceCents = 1_000,
            DebtLimitCents = 50,
            LoginGrantRemainingMinutes = 5,
            PolicyVersion = "policy-2026-09",
        };
        payload.Packages.Add(new OfflinePackageSnapshot
        {
            PackageId = "package-01",
            TariffId = "block",
            ZoneId = "vip",
            RemainingMinutes = 45,
            Status = OfflinePackageStatus.Active,
        });
        payload.Tariffs.Add(new OfflineTariffSnapshot
        {
            TariffId = "minute",
            Name = "Поминутный",
            PerMinutePriceCents = 60,
        });
        var signature = Convert.FromBase64String(
            "yeGZhZjunhzh3O7U5tUv2ZDdXfdZLb0J8fPn7cBKM7IhiiAYatnUeiCQ0cHTzuvIbCNGPFcNXEpVF/mYLj5cCQ==");
        var verifier = new V2Ed25519OfflineSnapshotSignatureVerifier(
            new Dictionary<string, string>
            {
                ["club-key-1"] = "11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=",
            });

        var ledger = V2OfflineSessionSnapshotReader.VerifyAndCreateLedger(
            new SignedOfflineSessionSnapshot
            {
                Payload = payload,
                SigningKeyId = "club-key-1",
                Signature = ByteString.CopyFrom(signature),
            },
            verifier);

        Assert.Equal(Guid.Parse(payload.SnapshotId), ledger.SnapshotId);
        Assert.Equal(50, ledger.DebtLimitCents);
        Assert.Equal(45, ledger.Packages.Single().RemainingMinutes);
    }

    [Fact]
    public void SnapshotPayloadUsesTheSameDeterministicBytesAsPythonServer()
    {
        var payload = new OfflineSessionSnapshotPayload
        {
            SnapshotId = "00000000-0000-0000-0000-000000000010",
            SchemaVersion = 1,
            SnapshotVersion = 7,
            IssuedAt = Timestamp.FromDateTime(DateTime.Parse("2026-09-27T12:00:00Z").ToUniversalTime()),
            ClientId = "00000000-0000-0000-0000-000000000001",
            SessionId = "00000000-0000-0000-0000-000000000002",
            DeviceId = "device-01",
            BalanceCents = 1_000,
            DebtLimitCents = 50,
            LoginGrantRemainingMinutes = 5,
            PolicyVersion = "policy-2026-09",
        };
        payload.Tariffs.Add(new OfflineTariffSnapshot
        {
            TariffId = "minute",
            Name = "Поминутный",
            PerMinutePriceCents = 60,
        });

        var encoded = Convert.ToBase64String(
            V2OfflineSessionSnapshotReader.SerializeDeterministic(payload));

        Assert.Equal(
            "CiQwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMTAQARgHIgYIwIrk1QYq"
            + "JDAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMTIkMDAwMDAwMDAtMDAw"
            + "MC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAyOglkZXZpY2UtMDFI0A9QZFgFaiAKBm1pbnV0"
            + "ZRIU0J/QvtC80LjQvdGD0YLQvdGL0LkweHIOcG9saWN5LTIwMjYtMDk=",
            encoded);
    }

    private static V2LocalSessionLedger CreateLedger(
        long balanceCents = 1_000,
        long debtLimitCents = 0,
        int loginGrantMinutes = 0,
        IReadOnlyList<V2LocalPackage>? packages = null) =>
        V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: "device-01",
            zoneId: null,
            balanceCents,
            debtLimitCents,
            loginGrantMinutes,
            packages ?? Array.Empty<V2LocalPackage>(),
            [
                new V2LocalTariff("package", "30 минут", null, 30, 300, 0, true),
                new V2LocalTariff("minute", "Поминутный", null, 0, 0, 60, false),
            ]);

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

    private sealed class RecordingClientPublisher : IV2ClientEventPublisher
    {
        private readonly int? _failOnCall;

        public RecordingClientPublisher(int? failOnCall = null) => _failOnCall = failOnCall;

        public List<V2LocalFact> Facts { get; } = [];

        public Task PublishAsync(V2LocalFact fact, CancellationToken cancellationToken = default)
        {
            Facts.Add(fact);
            if (_failOnCall == Facts.Count)
            {
                throw new InvalidOperationException("transport is unavailable");
            }
            return Task.CompletedTask;
        }
    }

    private sealed class FlakyClientPublisher : IV2ClientEventPublisher
    {
        private int _failuresRemaining;

        public FlakyClientPublisher(int failuresBeforeSuccess) => _failuresRemaining = failuresBeforeSuccess;

        public int Attempts { get; private set; }

        public Task PublishAsync(V2LocalFact fact, CancellationToken cancellationToken = default)
        {
            Attempts++;
            if (_failuresRemaining-- > 0)
            {
                throw new InvalidOperationException("transport is unavailable");
            }
            return Task.CompletedTask;
        }
    }

    private sealed class SnapshotVerifier : IOfflineSnapshotSignatureVerifier
    {
        private readonly byte[] _expectedPayload;
        private readonly bool _accepts;

        public SnapshotVerifier(byte[] expectedPayload, bool accepts)
        {
            _expectedPayload = expectedPayload;
            _accepts = accepts;
        }

        public ReadOnlyMemory<byte> Payload { get; private set; }

        public bool Verify(
            string signingKeyId,
            ReadOnlyMemory<byte> payload,
            ReadOnlyMemory<byte> signature)
        {
            Payload = payload;
            return _accepts && payload.Span.SequenceEqual(_expectedPayload);
        }
    }
}
