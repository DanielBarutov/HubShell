using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class V2BillingLogicTests
{
    [Theory]
    [InlineData(0, true)]
    [InlineData(20, false)]
    public void PackageSnapshotRateControlsGrantToPerMinuteTransition(long packageRate, bool validSnapshot)
    {
        var ledger = CreateLedger(1, 7_918, 100, tariffs:
        [
            new("hour", "Час", "vip", 60, 600, packageRate, true),
            new("rate", "Поминутный", "vip", 0, 0, 100, false),
        ]);
        var grant = V2LocalLedgerEngine.ConsumeOneMinute(ledger, Guid.NewGuid(), Activation);
        Assert.Equal(0, grant.Ledger.LoginGrantRemainingMinutes);
        Assert.Equal(7_918, grant.Ledger.BalanceCents);
        if (!validSnapshot)
        {
            Assert.Throws<InvalidOperationException>(() => V2LocalLedgerEngine.ConsumeOneMinute(
                grant.Ledger, Guid.NewGuid(), Activation.AddMinutes(1)));
            Assert.Equal(V2LocalSessionStatus.Active, grant.Ledger.Status);
            return;
        }
        var debit = V2LocalLedgerEngine.ConsumeOneMinute(grant.Ledger, Guid.NewGuid(), Activation.AddMinutes(1));
        Assert.Equal(7_818, debit.Ledger.BalanceCents);
        Assert.Equal("per_minute_debit", debit.OutboxFacts.Single().EventType);
        Assert.False(debit.LockWorkstation);
    }

    [Fact]
    public void RemainingTimeIncludesActiveQueuedPackagesAndBalance()
    {
        var ledger = CreateLedger(0, 3_600, 100,
            packages: [new("active", "test", "vip", 3, V2LocalPackageStatus.Active)]);
        Assert.Equal(39, V2LocalLedgerEngine.RemainingMinutes(ledger));
        ledger = ledger with { Packages = ledger.Packages.Append(
            new V2LocalPackage("queued", "hour", "vip", 60, V2LocalPackageStatus.Queued)).ToArray() };
        Assert.Equal(99, V2LocalLedgerEngine.RemainingMinutes(ledger));
        var next = V2LocalLedgerEngine.ConsumeOneMinute(ledger, Guid.NewGuid(), Activation);
        Assert.Equal(98, V2LocalLedgerEngine.RemainingMinutes(next.Ledger));
        Assert.Equal(3_600, next.Ledger.BalanceCents);
    }

    [Fact]
    public async Task GuestAdditionsAreDurableOrderedAndBurnOnExit()
    {
        var guest = CreateLedger(0, 0, 0,
            packages: [new("initial", "first", "vip", 1, V2LocalPackageStatus.Active)])
            with { GuestPaymentId = Guid.NewGuid(), GuestName = "Гость" };
        var addition = guest with
        {
            SnapshotId = Guid.NewGuid(), GuestPaymentId = Guid.NewGuid(),
            Packages = [new(Guid.NewGuid().ToString(), "second", "vip", 2, V2LocalPackageStatus.Active)],
        };
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(guest);
        await coordinator.ApplyGuestPackageAsync(addition);
        // Reopening the coordinator simulates a client restart after a lost RPC reply.
        coordinator = new V2LocalLedgerCoordinator(store);
        Assert.True((await coordinator.ApplyGuestPackageAsync(addition)).IsDuplicate);
        var ledger = await coordinator.ReadLedgerAsync();
        Assert.Equal(2, ledger.Packages.Count);
        Assert.Equal(V2LocalPackageStatus.Queued, ledger.Packages[1].Status);
        Assert.Equal(guest.ActivatedAtUtc, ledger.ActivatedAtUtc);
        Assert.Equal(guest.GuestPaymentId, ledger.GuestPaymentId);
        var next = await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), Activation);
        Assert.Equal(2, next.Ledger.Packages[1].RemainingMinutes);
        next = await coordinator.ConsumeOneMinuteAsync(Guid.NewGuid(), Activation.AddMinutes(1));
        Assert.Equal(1, next.Ledger.Packages[1].RemainingMinutes);
        Assert.Equal(V2LocalPackageStatus.Active, next.Ledger.Packages[1].Status);
        var third = addition with { SnapshotId = Guid.NewGuid(),
            Packages = [new("third", "third", "vip", 10, V2LocalPackageStatus.Active)] };
        await coordinator.ApplyGuestPackageAsync(third);
        var stopped = await coordinator.StopEarlyAsync(Guid.NewGuid(), Activation.AddMinutes(2));
        Assert.All(stopped.Ledger.Packages, package => Assert.Equal(0, package.RemainingMinutes));
        Assert.All(stopped.Ledger.Packages.Skip(1),
            package => Assert.Equal(V2LocalPackageStatus.Burned, package.Status));
        Assert.Empty(stopped.OutboxFacts);
        Assert.Throws<InvalidOperationException>(() =>
            V2LocalLedgerEngine.ApplyGuestPackage(stopped.Ledger, addition));
        var serverStopped = V2LocalLedgerEngine.ApplyServerStop(ledger);
        Assert.All(serverStopped.Ledger.Packages,
            package => Assert.Equal(V2LocalPackageStatus.Burned, package.Status));
    }

    [Fact]
    public void GuestAdditionRejectsAnotherSession()
    {
        var guest = CreateLedger(0, 0, 0) with { GuestPaymentId = Guid.NewGuid() };
        Assert.Throws<InvalidOperationException>(() => V2LocalLedgerEngine.ApplyGuestPackage(
            guest, guest with { SessionId = Guid.NewGuid() }));
    }

    private static readonly DateTimeOffset Activation =
        DateTimeOffset.Parse("2026-09-30T10:00:20Z");

    [Fact]
    public async Task RunnerSwitchesFromFreeGrantToPerMinuteAndDebitsEachDueMinute()
    {
        /// Проверяет переход после пяти бесплатных минут на поминутный тариф и списание цены каждой минуты.
        var coordinator = await CreateCoordinatorAsync(
            grantMinutes: 5,
            balanceCents: 95_000,
            perMinutePriceCents: 100);

        var transitions = await new V2MinuteLedgerRunner(coordinator, () => Guid.NewGuid())
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:08:05Z"));
        var ledger = await coordinator.ReadLedgerAsync();

        Assert.Equal(8, transitions.Count);
        Assert.Equal(95_000 - 3 * 100, ledger.BalanceCents);
        Assert.Equal(0, ledger.LoginGrantRemainingMinutes);
        Assert.Equal(3, transitions.SelectMany(item => item.OutboxFacts)
            .Count(item => item.EventType == "per_minute_debit"));
        Assert.Equal(DateTimeOffset.Parse("2026-09-30T10:08:00Z"), ledger.LastConsumedMinuteUtc);
    }

    [Fact]
    public async Task RunnerKeepsBalanceAtExactFreeBoundary()
    {
        /// Проверяет, что ровно пять минут используют только бесплатный grant и не уменьшают баланс.
        var coordinator = await CreateCoordinatorAsync(5, 95_000, 100);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:05:00Z"));

        Assert.Equal(5, transitions.Count);
        Assert.Equal(95_000, (await coordinator.ReadLedgerAsync()).BalanceCents);
        Assert.DoesNotContain(
            transitions.SelectMany(item => item.OutboxFacts),
            item => item.EventType == "per_minute_debit");
    }

    [Fact]
    public async Task DepositDuringFreeMinutesExtendsThePaidTimeAndEachMinuteCreatesADebitFact()
    {
        var coordinator = await CreateCoordinatorAsync(
            grantMinutes: 5,
            balanceCents: 200,
            perMinutePriceCents: 100);
        await coordinator.ApplyBalanceCreditAsync(Guid.NewGuid(), Guid.NewGuid(), 200);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(Activation.AddMinutes(9));
        var ledger = await coordinator.ReadLedgerAsync();
        var debitFacts = transitions
            .SelectMany(item => item.OutboxFacts)
            .Where(item => item.EventType == "per_minute_debit")
            .ToArray();

        Assert.Equal(9, transitions.Count);
        Assert.Equal(0, ledger.BalanceCents);
        Assert.Equal(4, debitFacts.Length);
        Assert.Equal(4, debitFacts.Select(item => item.OperationId).Distinct().Count());
        Assert.Equal(
            DateTimeOffset.Parse("2026-09-30T10:09:00Z"),
            ledger.LastConsumedMinuteUtc);
    }

    [Fact]
    public async Task RunnerCatchesUpDelayedBoundariesWithoutLosingPaidMinutes()
    {
        /// Проверяет, что после задержки таймера списываются все пропущенные платные минутные границы.
        var coordinator = await CreateCoordinatorAsync(0, 1_000, 100);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:04:59Z"));

        Assert.Equal(4, transitions.Count);
        Assert.Equal(600, (await coordinator.ReadLedgerAsync()).BalanceCents);
    }

    [Fact]
    public async Task RunnerDoesNotRepeatAProcessedMinuteOnTheNextPoll()
    {
        /// Проверяет идемпотентность повторного опроса внутри уже обработанной минуты.
        var coordinator = await CreateCoordinatorAsync(0, 1_000, 100);
        var runner = new V2MinuteLedgerRunner(coordinator);

        await runner.ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:03:10Z"));
        var repeated = await runner.ConsumeDueMinutesAsync(
            DateTimeOffset.Parse("2026-09-30T10:03:55Z"));

        Assert.Empty(repeated);
        Assert.Equal(700, (await coordinator.ReadLedgerAsync()).BalanceCents);
    }

    [Fact]
    public async Task RunnerDoesNotDebitWhenClockMovesBackward()
    {
        /// Проверяет, что возврат системных часов не создаёт повторное списание.
        var coordinator = await CreateCoordinatorAsync(0, 1_000, 100);
        var runner = new V2MinuteLedgerRunner(coordinator);

        await runner.ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:03:10Z"));
        var rollback = await runner.ConsumeDueMinutesAsync(
            DateTimeOffset.Parse("2026-09-30T10:02:10Z"));

        Assert.Empty(rollback);
        Assert.Equal(700, (await coordinator.ReadLedgerAsync()).BalanceCents);
    }

    [Fact]
    public async Task RunnerStopsAndLocksWhenTheNextMinuteIsUnaffordable()
    {
        /// Проверяет остановку сессии после последней доступной минуты без ухода баланса ниже разрешённого лимита.
        var coordinator = await CreateCoordinatorAsync(0, 200, 100);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:03:05Z"));
        var ledger = await coordinator.ReadLedgerAsync();

        Assert.Equal(3, transitions.Count);
        Assert.Equal(0, ledger.BalanceCents);
        Assert.Equal(V2LocalSessionStatus.Exhausted, ledger.Status);
        Assert.True(transitions[^1].LockWorkstation);
        Assert.Equal("session_stopped", transitions[^1].OutboxFacts.Single().EventType);
    }

    [Fact]
    public async Task RunnerAllowsDebtUntilTheConfiguredLimit()
    {
        /// Проверяет, что поминутная игра использует разрешённый лимит долга и останавливается перед его превышением.
        var coordinator = await CreateCoordinatorAsync(0, 0, 100, debtLimitCents: 100);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:02:05Z"));
        var ledger = await coordinator.ReadLedgerAsync();

        Assert.Equal(2, transitions.Count);
        Assert.Equal(-100, ledger.BalanceCents);
        Assert.Equal(V2LocalSessionStatus.Exhausted, ledger.Status);
        Assert.True(transitions[^1].LockWorkstation);
    }

    [Fact]
    public async Task RunnerDoesNothingForAStoppedLedger()
    {
        /// Проверяет, что завершённая локальная сессия не продолжает списывать деньги по таймеру.
        var coordinator = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await coordinator.InitializeAsync(
            CreateLedger(0, 1_000, 100) with { Status = V2LocalSessionStatus.Stopped });

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(DateTimeOffset.Parse("2026-09-30T10:10:00Z"));

        Assert.Empty(transitions);
        Assert.Equal(1_000, (await coordinator.ReadLedgerAsync()).BalanceCents);
    }

    [Fact]
    public async Task RunnerRequiresSignedActivationTime()
    {
        /// Проверяет отказ запуска расчёта времени без времени активации из подписанного снимка.
        var store = new InMemoryLedgerStore();
        var coordinator = new V2LocalLedgerCoordinator(store);
        await coordinator.InitializeAsync(
            CreateLedger(0, 1_000, 100) with { ActivatedAtUtc = null });

        await Assert.ThrowsAsync<InvalidOperationException>(() =>
            new V2MinuteLedgerRunner(coordinator).ConsumeDueMinutesAsync(Activation.AddMinutes(1)));
    }

    [Fact]
    public async Task RunnerStopsWhenTheSnapshotHasNoPositivePerMinuteRate()
    {
        /// Проверяет, что нулевая ставка не считается бесплатным бесконечным временем и закрывает доступ.
        var coordinator = await CreateCoordinatorAsync(0, 1_000, 0);

        var transitions = await new V2MinuteLedgerRunner(coordinator)
            .ConsumeDueMinutesAsync(Activation.AddMinutes(1));
        var ledger = await coordinator.ReadLedgerAsync();

        Assert.Single(transitions);
        Assert.Equal(1_000, ledger.BalanceCents);
        Assert.Equal(V2LocalSessionStatus.Exhausted, ledger.Status);
        Assert.True(transitions[0].LockWorkstation);
    }

    [Fact]
    public void EngineConsumesActivePackageBeforeBalance()
    {
        /// Проверяет приоритет уже активного пакетного времени над поминутным списанием.
        var ledger = CreateLedger(
            0,
            1_000,
            100,
            packages: [new("active", "package", "vip", 2, V2LocalPackageStatus.Active)]);

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(ledger, Guid.NewGuid(), Activation);

        Assert.Equal(1_000, transition.Ledger.BalanceCents);
        Assert.Equal(1, transition.Ledger.Packages.Single().RemainingMinutes);
        Assert.Equal("package_consumed", transition.OutboxFacts.Single().EventType);
    }

    [Fact]
    public void EngineActivatesACompatibleQueuedPackageBeforePerMinute()
    {
        /// Проверяет запуск совместимого пакета из очереди до обращения к балансу.
        var ledger = CreateLedger(
            0,
            1_000,
            100,
            packages: [new("queued", "package", "vip", 2, V2LocalPackageStatus.Queued)]);

        var transition = V2LocalLedgerEngine.ConsumeOneMinute(ledger, Guid.NewGuid(), Activation);

        Assert.Equal(1_000, transition.Ledger.BalanceCents);
        Assert.Equal(V2LocalPackageStatus.Active, transition.Ledger.Packages.Single().Status);
        Assert.Equal("package_consumed", transition.OutboxFacts.Single().EventType);
    }

    [Fact]
    public void SnapshotRejectsAnIncompatibleQueuedPackage()
    {
        /// Проверяет, что подписанный snapshot не может содержать пакет другой зоны игрового места.
        Assert.Throws<ArgumentException>(() => CreateLedger(
            0,
            1_000,
            100,
            packages: [new("queued", "package", "standard", 2, V2LocalPackageStatus.Queued)]));
    }

    [Fact]
    public void EngineSwitchesToPerMinuteAfterPackageIsExhausted()
    {
        /// Проверяет переход от последней минуты пакета к поминутному списанию на следующей границе.
        var ledger = CreateLedger(
            0,
            1_000,
            100,
            packages: [new("active", "package", "vip", 1, V2LocalPackageStatus.Active)]);

        var packageTransition = V2LocalLedgerEngine.ConsumeOneMinute(
            ledger,
            Guid.NewGuid(),
            Activation);
        var minuteTransition = V2LocalLedgerEngine.ConsumeOneMinute(
            packageTransition.Ledger,
            Guid.NewGuid(),
            Activation.AddMinutes(1));

        Assert.Equal(1_000, packageTransition.Ledger.BalanceCents);
        Assert.Equal(900, minuteTransition.Ledger.BalanceCents);
        Assert.Equal("per_minute_debit", minuteTransition.OutboxFacts.Single().EventType);
    }

    [Fact]
    public void EnginePurchasesPackageByDebitingItsSnapshotPrice()
    {
        /// Проверяет списание цены известного пакета и добавление права времени в очередь.
        var ledger = CreateLedger(
            0,
            1_000,
            0,
            tariffs: [new("package", "Пакет", "vip", 3, 300, 0, true)]);

        var transition = V2LocalLedgerEngine.PurchasePackage(
            ledger,
            Guid.NewGuid(),
            "package",
            Activation);

        Assert.Equal(700, transition.Ledger.BalanceCents);
        var package = Assert.Single(transition.Ledger.Packages);
        Assert.Equal(V2LocalPackageStatus.Queued, package.Status);
        Assert.Equal(3, package.RemainingMinutes);
        Assert.Equal("package_purchased", transition.OutboxFacts.Single().EventType);
    }

    [Fact]
    public void EngineRejectsPackagePurchaseBelowDebtLimit()
    {
        /// Проверяет отказ покупки пакета, если цена превысит доступный баланс и лимит долга.
        var ledger = CreateLedger(
            0,
            100,
            0,
            tariffs: [new("package", "Пакет", "vip", 3, 200, 0, true)]);

        Assert.Throws<InvalidOperationException>(() =>
            V2LocalLedgerEngine.PurchasePackage(ledger, Guid.NewGuid(), "package", Activation));
    }

    [Fact]
    public void EngineRejectsNonPurchasableTariff()
    {
        /// Проверяет отказ покупки тарифа, который присутствует в снимке только для отображения.
        var ledger = CreateLedger(
            0,
            1_000,
            0,
            tariffs: [new("package", "Пакет", "vip", 3, 200, 0, false)]);

        Assert.Throws<InvalidOperationException>(() =>
            V2LocalLedgerEngine.PurchasePackage(ledger, Guid.NewGuid(), "package", Activation));
    }

    [Fact]
    public void EngineRejectsPackageFromAnotherZone()
    {
        /// Проверяет отказ покупки пакета, несовместимого с зоной игрового места.
        var ledger = CreateLedger(
            0,
            1_000,
            0,
            tariffs: [new("package", "Пакет", "standard", 3, 200, 0, true)]);

        Assert.Throws<InvalidOperationException>(() =>
            V2LocalLedgerEngine.PurchasePackage(ledger, Guid.NewGuid(), "package", Activation));
    }

    [Fact]
    public void EngineDoesNotDebitTwiceForTheSameClientAction()
    {
        /// Проверяет идемпотентность повторной доставки одного действия поминутного списания.
        var actionId = Guid.NewGuid();
        var ledger = CreateLedger(0, 1_000, 100);

        var first = V2LocalLedgerEngine.ConsumeOneMinute(ledger, actionId, Activation);
        var repeated = V2LocalLedgerEngine.ConsumeOneMinute(first.Ledger, actionId, Activation);

        Assert.Equal(900, first.Ledger.BalanceCents);
        Assert.True(repeated.IsDuplicate);
        Assert.Equal(900, repeated.Ledger.BalanceCents);
        Assert.Empty(repeated.OutboxFacts);
    }

    [Fact]
    public void EngineAppliesTheSameServerCreditOnlyOnceAfterLocalDebit()
    {
        /// Проверяет применение пополнения поверх локального остатка без возврата к старому snapshot-балансу.
        var ledger = CreateLedger(0, 1_000, 100);
        var debit = V2LocalLedgerEngine.ConsumeOneMinute(ledger, Guid.NewGuid(), Activation);
        var operationId = Guid.NewGuid();

        var credited = V2LocalLedgerEngine.ApplyBalanceCredit(debit.Ledger, operationId, 300);
        var repeated = V2LocalLedgerEngine.ApplyBalanceCredit(credited.Ledger, operationId, 300);

        Assert.Equal(1_200, credited.Ledger.BalanceCents);
        Assert.True(repeated.IsDuplicate);
        Assert.Equal(1_200, repeated.Ledger.BalanceCents);
    }

    [Fact]
    public void EngineStopEarlyBurnsGrantAndLocksTheSession()
    {
        /// Проверяет отдельное сжигание неиспользованного бесплатного времени при ручном завершении.
        var ledger = CreateLedger(3, 1_000, 100);

        var transition = V2LocalLedgerEngine.StopEarly(ledger, Guid.NewGuid(), Activation);

        Assert.Equal(V2LocalSessionStatus.Stopped, transition.Ledger.Status);
        Assert.Equal(0, transition.Ledger.LoginGrantRemainingMinutes);
        Assert.True(transition.LockWorkstation);
        Assert.Equal(
            ["login_grant_burned", "session_stopped"],
            transition.OutboxFacts.Select(item => item.EventType));
    }

    [Fact]
    public void EngineStopEarlyBurnsActivePackageAndKeepsQueuedPackage()
    {
        /// Проверяет сжигание только активного пакета при выходе и сохранение ещё не начатой очереди.
        var ledger = CreateLedger(
            0,
            1_000,
            100,
            packages:
            [
                new("active", "package", "vip", 4, V2LocalPackageStatus.Active),
                new("queued", "package", "vip", 5, V2LocalPackageStatus.Queued),
            ]);

        var transition = V2LocalLedgerEngine.StopEarly(ledger, Guid.NewGuid(), Activation);

        Assert.Equal(V2LocalPackageStatus.Burned, transition.Ledger.Packages[0].Status);
        Assert.Equal(0, transition.Ledger.Packages[0].RemainingMinutes);
        Assert.Equal(V2LocalPackageStatus.Queued, transition.Ledger.Packages[1].Status);
        Assert.Equal(5, transition.Ledger.Packages[1].RemainingMinutes);
        Assert.True(transition.LockWorkstation);
    }

    private static async Task<V2LocalLedgerCoordinator> CreateCoordinatorAsync(
        int grantMinutes,
        long balanceCents,
        long perMinutePriceCents,
        long debtLimitCents = 0)
    {
        var coordinator = new V2LocalLedgerCoordinator(new InMemoryLedgerStore());
        await coordinator.InitializeAsync(
            CreateLedger(
                grantMinutes,
                balanceCents,
                perMinutePriceCents,
                debtLimitCents: debtLimitCents));
        return coordinator;
    }

    private static V2LocalSessionLedger CreateLedger(
        int grantMinutes,
        long balanceCents,
        long perMinutePriceCents,
        long debtLimitCents = 0,
        string? zoneId = "vip",
        IReadOnlyList<V2LocalPackage>? packages = null,
        IReadOnlyList<V2LocalTariff>? tariffs = null,
        DateTimeOffset? activatedAt = null)
    {
        tariffs ??=
        [new("per-minute", "Поминутный тариф", zoneId, 0, 0, perMinutePriceCents, false)];
        return V2LocalSessionLedger.Create(
            snapshotVersion: 1,
            clientId: Guid.Parse("00000000-0000-0000-0000-000000000001"),
            sessionId: Guid.Parse("00000000-0000-0000-0000-000000000002"),
            deviceId: "device-01",
            zoneId: zoneId,
            balanceCents: balanceCents,
            debtLimitCents: debtLimitCents,
            loginGrantRemainingMinutes: grantMinutes,
            packages: packages ?? Array.Empty<V2LocalPackage>(),
            tariffs: tariffs,
            snapshotId: Guid.Parse("00000000-0000-0000-0000-000000000003"),
            activatedAtUtc: activatedAt ?? Activation);
    }

    private sealed class InMemoryLedgerStore : IV2LocalLedgerStore
    {
        private V2LocalLedgerStorageSnapshot? _snapshot;

        public Task<V2LocalLedgerStorageSnapshot?> ReadAsync(
            CancellationToken cancellationToken = default) => Task.FromResult(_snapshot);

        public Task WriteAsync(
            V2LocalLedgerStorageSnapshot snapshot,
            CancellationToken cancellationToken = default)
        {
            _snapshot = snapshot;
            return Task.CompletedTask;
        }
    }
}
