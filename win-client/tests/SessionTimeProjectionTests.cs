using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class SessionTimeProjectionTests
{
    [Fact]
    /// <summary>
    /// Проверяет, что повторный snapshot того же источника не увеличивает
    /// отображаемый остаток из-за запаздывающего server polling.
    /// </summary>
    public void SameSourceSnapshotDoesNotIncreaseProjectedTime()
    {
        var projection = new SessionTimeProjection();
        var receivedAt = new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

        projection.Apply(
            Snapshot(3, balanceCents: 1_000),
            receivedAt);
        Assert.Equal(3, projection.GetRemainingMinutes(receivedAt));

        var nextAt = receivedAt.AddMinutes(1);
        projection.Apply(
            Snapshot(3, balanceCents: 1_000),
            nextAt);

        Assert.Equal(2, projection.GetRemainingMinutes(nextAt));
    }

    [Fact]
    /// <summary>
    /// Проверяет, что частые одинаковые ответы сервера не перезапускают
    /// локальный отсчёт трёхминутного пакета между списаниями сервера.
    /// </summary>
    public void RepeatedHeartbeatSnapshotsDoNotRestartPackageCountdown()
    {
        var projection = new SessionTimeProjection();
        var startedAt = new DateTimeOffset(2026, 1, 1, 12, 5, 0, TimeSpan.Zero);

        projection.Apply(Snapshot(3, balanceCents: 0, packageId: "package-1"), startedAt);

        projection.Apply(
            Snapshot(3, balanceCents: 0, packageId: "package-1"),
            startedAt.AddSeconds(5));
        Assert.Equal(3, projection.GetRemainingMinutes(startedAt.AddSeconds(5)));

        projection.Apply(
            Snapshot(3, balanceCents: 0, packageId: "package-1"),
            startedAt.AddMinutes(1));
        Assert.Equal(2, projection.GetRemainingMinutes(startedAt.AddMinutes(1)));

        projection.Apply(
            Snapshot(3, balanceCents: 0, packageId: "package-1"),
            startedAt.AddMinutes(1).AddSeconds(5));
        Assert.Equal(2, projection.GetRemainingMinutes(startedAt.AddMinutes(1).AddSeconds(5)));

        projection.Apply(
            Snapshot(3, balanceCents: 0, packageId: "package-1"),
            startedAt.AddMinutes(2));
        Assert.Equal(1, projection.GetRemainingMinutes(startedAt.AddMinutes(2)));

        projection.Apply(
            Snapshot(2, balanceCents: 0, packageId: "package-1"),
            startedAt.AddMinutes(2).AddSeconds(5));
        Assert.Equal(1, projection.GetRemainingMinutes(startedAt.AddMinutes(2).AddSeconds(5)));

        Assert.Equal(0, projection.GetRemainingMinutes(startedAt.AddMinutes(3)));
    }

    [Fact]
    /// <summary>
    /// Проверяет, что подтверждённое изменение баланса разрешает обновить
    /// доступное поминутное время после пополнения депозита.
    /// </summary>
    public void BalanceChangeAcceptsAuthoritativePerMinuteIncrease()
    {
        var projection = new SessionTimeProjection();
        var receivedAt = new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

        projection.Apply(
            Snapshot(2, balanceCents: 1_000),
            receivedAt);
        var nextAt = receivedAt.AddMinutes(1);

        projection.Apply(
            Snapshot(10, balanceCents: 2_000),
            nextAt);

        Assert.Equal(10, projection.GetRemainingMinutes(nextAt));
    }

    [Fact]
    /// <summary>
    /// Проверяет, что смена server-backed источника времени начинает новый
    /// countdown и не смешивает остаток пакета с поминутным остатком.
    /// </summary>
    public void SourceChangeStartsNewCountdown()
    {
        var projection = new SessionTimeProjection();
        var receivedAt = new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

        projection.Apply(
            Snapshot(1, balanceCents: 1_000, packageId: "package-1"),
            receivedAt);
        var nextAt = receivedAt.AddMinutes(1);
        projection.Apply(
            Snapshot(8, balanceCents: 1_000),
            nextAt);

        Assert.Equal(8, projection.GetRemainingMinutes(nextAt));
    }

    private static SessionSnapshot Snapshot(
        int remainingMinutes,
        long balanceCents,
        string? packageId = null) =>
        new(
            "session-1",
            "workstation-1",
            "client-1",
            null,
            "active",
            "2026-01-01T12:00:00Z",
            null,
            "device",
            string.Empty,
            BalanceCents: balanceCents,
            ActivePackage: packageId is null
                ? null
                : new SessionPackageSnapshot(
                    packageId,
                    "tariff-package",
                    "vip",
                    60,
                    remainingMinutes,
                    1,
                    "active",
                    0,
                    0,
                    null),
            BalanceRemainingMinutes: packageId is null ? remainingMinutes : null);
}
