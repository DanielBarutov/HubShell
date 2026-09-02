using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using GameClub.Client.Infrastructure;

namespace GameClub.Client.Application;

public sealed class ClientSessionCoordinator
{
    private readonly IBackendClient _backendClient;
    private readonly IOfflineJournal? _offlineJournal;
    private readonly Dictionary<string, CommandExecutionResult> _pendingAcknowledgements = new();
    private const int MaxPendingAcknowledgements = 128;

    public ClientSessionCoordinator(
        IBackendClient backendClient,
        IOfflineJournal? offlineJournal = null)
    {
        _backendClient = backendClient;
        _offlineJournal = offlineJournal;
    }

    public IWorkstationSessionGateway BackendClient => _backendClient;

    public IClientPortalGateway ClientPortal => _backendClient;

    public async Task QueueOfflineOperationAsync(
        SessionSnapshot session,
        OfflineOperationSnapshot operation,
        CancellationToken cancellationToken = default)
    {
        if (_offlineJournal is null)
        {
            throw new InvalidOperationException("Offline journal is not configured");
        }
        if (!session.Id.Equals(operation.SessionId, StringComparison.Ordinal)
            || !session.Status.Contains("ACTIVE", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Offline operations require an active server session");
        }
        await _offlineJournal.AppendAsync(operation, cancellationToken);
    }

    public async Task<OfflineBatchResultSnapshot?> ReplayOfflineOperationsAsync(
        SessionSnapshot session,
        string deviceId,
        CancellationToken cancellationToken = default)
    {
        if (_offlineJournal is null
            || !session.Status.Contains("ACTIVE", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }
        var pending = await _offlineJournal.ReadPendingAsync(session.Id, cancellationToken);
        if (pending.Count == 0)
        {
            return null;
        }

        var result = await _backendClient.ReplayOfflineBatchAsync(
            session.Id,
            deviceId,
            pending,
            cancellationToken);
        var acknowledged = result.Results
            .Where(item => item.Status is "applied" or "duplicate")
            .Select(item => item.OperationId)
            .ToArray();
        await _offlineJournal.AcknowledgeAsync(acknowledged, cancellationToken);
        return result;
    }

    public async Task<ClientConnectionSnapshot> CheckConnectionAsync(
        CancellationToken cancellationToken = default)
    {
        try
        {
            return await _backendClient.CheckConnectionAsync(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (DeviceAuthenticationRequiredException)
        {
            return AuthenticationRequiredSnapshot();
        }
        catch (DeviceEnrollmentPendingException)
        {
            return WaitingForAssignmentSnapshot();
        }
        catch (DeviceEnrollmentDisabledException)
        {
            return new ClientConnectionSnapshot(
                ClientConnectionState.Offline,
                "Место отключено администратором",
                null,
                "—");
        }
        catch (DeviceEnrollmentRejectedException)
        {
            return new ClientConnectionSnapshot(
                ClientConnectionState.Offline,
                "Эта установка уже привязана к другому месту",
                null,
                "—");
        }
        catch (Exception)
        {
            return new ClientConnectionSnapshot(
                ClientConnectionState.Offline,
                "Нет связи с сервером",
                null,
                "—");
        }
    }

    private static ClientConnectionSnapshot AuthenticationRequiredSnapshot() =>
        new(
            ClientConnectionState.AuthenticationRequired,
            "Требуется повторная авторизация устройства",
            null,
            "—");

    private static ClientConnectionSnapshot WaitingForAssignmentSnapshot() =>
        new(
            ClientConnectionState.WaitingForAssignment,
            "Ожидаем привязку этого ПК администратором",
            null,
            "—");

    public async Task RunWorkstationHeartbeatLoopAsync(
        string deviceId,
        string clientVersion,
        IReadOnlyCollection<string> capabilities,
        Action<string>? onThemeReceived = null,
        Action<string>? onManagerPasswordVerifierReceived = null,
        Action<WorkstationLockdownPolicySnapshot>? onLockdownPolicyReceived = null,
        Func<Task>? refreshSessionSnapshot = null,
        CancellationToken cancellationToken = default)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(15));
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                var heartbeat = await _backendClient.SendHeartbeatAsync(
                    deviceId,
                    clientVersion,
                    capabilities,
                    cancellationToken);
                if (!string.IsNullOrWhiteSpace(heartbeat.Theme))
                {
                    onThemeReceived?.Invoke(heartbeat.Theme);
                }
                if (!string.IsNullOrWhiteSpace(heartbeat.ManagerPasswordVerifier))
                {
                    onManagerPasswordVerifierReceived?.Invoke(heartbeat.ManagerPasswordVerifier);
                }
                if (heartbeat.LockdownPolicy is not null)
                {
                    onLockdownPolicyReceived?.Invoke(heartbeat.LockdownPolicy);
                }
                if (refreshSessionSnapshot is not null)
                {
                    await refreshSessionSnapshot();
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception)
            {
                // Следующая итерация повторит heartbeat после короткого интервала.
            }

            if (!await timer.WaitForNextTickAsync(cancellationToken))
            {
                return;
            }
        }
    }

    public async Task RunCommandLoopAsync(
        string deviceId,
        IWorkstationCommandExecutor executor,
        CancellationToken cancellationToken = default)
    {
        var reconnectAttempt = 0;
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                await foreach (var command in _backendClient.WatchCommandsAsync(
                    deviceId,
                    cancellationToken))
                {
                    if (command.IsExpired(DateTimeOffset.UtcNow))
                    {
                        await _backendClient.AcknowledgeCommandAsync(
                            command.Id,
                            deviceId,
                            success: false,
                            message: "Команда просрочена и не исполнена",
                            cancellationToken: cancellationToken);
                        continue;
                    }

                    if (!_pendingAcknowledgements.TryGetValue(command.Id, out var result))
                    {
                        try
                        {
                            result = await executor.ExecuteAsync(command, cancellationToken);
                        }
                        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                        {
                            throw;
                        }
                        catch (Exception)
                        {
                            result = new CommandExecutionResult(false, "Выполнение команды завершилось ошибкой");
                        }

                        // If the acknowledgement response is lost, the server may redeliver
                        // this command after reconnect. Reuse the result instead of running
                        // a side effect twice; the server still remains authoritative.
                        RememberPendingAcknowledgement(command.Id, result);
                    }

                    await _backendClient.AcknowledgeCommandAsync(
                        command.Id,
                        deviceId,
                        result.Success,
                        result.Message,
                        cancellationToken);
                    _pendingAcknowledgements.Remove(command.Id);
                    reconnectAttempt = 0;
                }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception)
            {
                var delaySeconds = Math.Min(30, 1 << Math.Min(reconnectAttempt, 5));
                reconnectAttempt = Math.Min(reconnectAttempt + 1, 5);
                await Task.Delay(TimeSpan.FromSeconds(delaySeconds), cancellationToken);
            }
        }
    }

    private void RememberPendingAcknowledgement(string commandId, CommandExecutionResult result)
    {
        if (_pendingAcknowledgements.Count >= MaxPendingAcknowledgements)
        {
            var oldestCommandId = _pendingAcknowledgements.Keys.First();
            _pendingAcknowledgements.Remove(oldestCommandId);
        }

        _pendingAcknowledgements[commandId] = result;
    }

    public ValueTask DisposeAsync() => _backendClient.DisposeAsync();
}
