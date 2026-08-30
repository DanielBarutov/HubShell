using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class AccessGateCoordinatorTests
{
    [Fact]
    public void StartsLockedAndUnlocksOnlyWithValidUserCode()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var now = DateTimeOffset.UtcNow;
        var gate = new AccessGateCoordinator(credentials, now: now);

        Assert.Equal(AccessMode.Locked, gate.Snapshot.Mode);
        Assert.False(gate.TryUnlockUser("0000", now));
        Assert.Equal(AccessMode.Locked, gate.Snapshot.Mode);
        Assert.True(gate.TryUnlockUser("4826", now));
        Assert.Equal(AccessMode.User, gate.Snapshot.Mode);
    }

    [Fact]
    public void ManagerModeRequiresSeparateCredentialAndCanBeClosed()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var gate = new AccessGateCoordinator(credentials);

        Assert.False(gate.TryEnterMaintenance("4826"));
        Assert.True(gate.TryEnterMaintenance("manager-secret"));
        Assert.True(gate.IsMaintenance);
        Assert.False(gate.TryUnlockUser("4826"));

        gate.Lock();

        Assert.True(gate.IsLocked);
    }

    [Fact]
    public void ReauthenticationFlowCanStartOnlyAfterTheGateIsLocked()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var gate = new AccessGateCoordinator(credentials);

        Assert.True(gate.TryUnlockUser("4826"));
        Assert.False(gate.TryEnterMaintenance("manager-secret"));

        gate.Lock("Требуется повторная авторизация устройства");

        Assert.True(gate.TryUnlockUser("4826"));
        Assert.Equal(AccessMode.User, gate.Snapshot.Mode);
    }

    [Fact]
    public void IdleTimeoutLocksUserAndTouchExtendsActivity()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var start = DateTimeOffset.UtcNow;
        var gate = new AccessGateCoordinator(credentials, TimeSpan.FromMinutes(10), start);

        Assert.True(gate.TryUnlockUser("4826", start));
        Assert.False(gate.LockIfIdle(start.AddMinutes(9).AddSeconds(59)));
        gate.Touch(start.AddMinutes(9));
        Assert.False(gate.LockIfIdle(start.AddMinutes(10)));
        Assert.True(gate.LockIfIdle(start.AddMinutes(19).AddSeconds(1)));
        Assert.True(gate.IsLocked);
    }

    [Fact]
    public void SessionLockRemainsLockedButAllowsReauthentication()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var gate = new AccessGateCoordinator(credentials);

        Assert.True(gate.TryUnlockUser("4826"));
        gate.LockSession("Сессия завершена");

        Assert.True(gate.IsLocked);
        Assert.True(gate.IsSessionLocked);
        Assert.True(gate.TryUnlockUser("4826"));
        Assert.Equal(AccessMode.User, gate.Snapshot.Mode);
    }

    [Fact]
    public void RepeatedFailuresTemporarilyThrottleFurtherAttempts()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");
        var start = DateTimeOffset.UtcNow;
        var gate = new AccessGateCoordinator(credentials, now: start);

        for (var attempt = 0; attempt < 5; attempt++)
        {
            Assert.False(gate.TryUnlockUser("wrong", start.AddSeconds(attempt)));
        }

        Assert.False(gate.TryUnlockUser("4826", start.AddSeconds(5)));
        Assert.True(gate.TryUnlockUser("4826", start.AddSeconds(36)));
    }

    [Fact]
    public void RejectsNonPositiveIdleTimeout()
    {
        var credentials = new StubCredentials(userCode: "4826", managerPassword: "manager-secret");

        Assert.Throws<ArgumentOutOfRangeException>(
            () => new AccessGateCoordinator(credentials, TimeSpan.Zero));
    }

    private sealed class StubCredentials(string userCode, string managerPassword) : IAccessCredentialVerifier
    {
        public bool IsUserAccessConfigured => true;

        public bool IsManagerAccessConfigured => true;

        public bool VerifyUserAccess(string accessCode) => accessCode == userCode;

        public bool VerifyManagerPassword(string password) => password == managerPassword;

        public void UpdateManagerPasswordVerifier(string verifier)
        {
        }
    }
}
