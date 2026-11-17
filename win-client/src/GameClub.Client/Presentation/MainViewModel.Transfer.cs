using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Grpc.Core;

namespace GameClub.Client.Presentation;

public sealed partial class MainViewModel
{
    private readonly IV2SessionTransferGateway? _v2TransferGateway;
    private Guid? _awaitedTargetTransfer;
    private string? _transferFailure;

    public bool IsV2TransferPending => _isV2TransferPending;
    public bool UsesV2Transfer => _v2TransferGateway is not null;
    public bool CanOpenTransfer => !UsesV2Transfer || CanStartV2Transfer;

    public void ReportV2TransferProblem(string message) => ShowSessionNotification(message);

    public bool CanStartV2Transfer => _v2TransferGateway is not null && IsOnline
        && !_deploymentBlocked && !_isV2TransferPending && !IsAccessLocked && !IsMaintenanceMode
        && _activeV2Ledger is { Status: V2LocalSessionStatus.Active };

    public async Task<IReadOnlyList<V2TransferTarget>> ListV2TransferTargetsAsync()
    {
        if (!CanStartV2Transfer || DeviceId is null || _activeV2Ledger is null)
            return [];
        return await _v2TransferGateway!.ListTransferTargetsAsync(
            DeviceId, _activeV2Ledger.SessionId, _lifetime.Token);
    }

    public async Task<V2TransferQuote?> QuoteV2TransferAsync(Guid targetWorkstationId)
    {
        if (!CanStartV2Transfer || DeviceId is null || _activeV2Ledger is null)
            return null;
        return await _v2TransferGateway!.QuoteTransferAsync(
            DeviceId, _activeV2Ledger.SessionId, targetWorkstationId, _lifetime.Token);
    }

    public async Task BeginV2TransferAsync(Guid targetWorkstationId, V2TransferQuote quote)
    {
        if (!CanStartV2Transfer || _activeV2Ledger is not { } ledger)
            return;
        await _v2Ledger!.BeginSourceTransferAsync(
            ledger.SessionId, new V2PendingSourceTransfer(Guid.NewGuid(), targetWorkstationId, quote.Token),
            _lifetime.Token);
        ShowTransferWait();
    }

    public async Task RunV2TransferLoopAsync()
    {
        if (_v2TransferGateway is null || _v2Ledger is null || _v2SignatureVerifier is null)
            return;

        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(1));
        while (await timer.WaitForNextTickAsync(_lifetime.Token))
        {
            try
            {
                if (DeviceId is not { Length: > 0 } deviceId)
                    continue;
                var local = await _v2Ledger.ReadSnapshotAsync(_lifetime.Token);
                if (local?.PendingSourceTransfer is { } request)
                {
                    await AdvanceSourceTransferAsync(deviceId, local.Ledger, request);
                }
                else if (!_deploymentBlocked && IsAccessLocked && !IsMaintenanceMode
                    && (!_isV2TransferPending || _awaitedTargetTransfer is not null)
                    && local?.Ledger.Status is not (V2LocalSessionStatus.Active or V2LocalSessionStatus.NeedsReview))
                {
                    await AdvanceTargetTransferAsync(deviceId);
                }
                _transferFailure = null;
            }
            catch (OperationCanceledException) when (_lifetime.IsCancellationRequested)
            {
                return;
            }
            catch (Exception error)
            {
                // Unknown outcome keeps the access gate closed and retries the same operation.
                if (_transferFailure != error.Message)
                {
                    _transferFailure = error.Message;
                    ClientLog.Exception("v2.transfer", error, "transfer status poll");
                }
            }
        }
    }

    private async Task AdvanceSourceTransferAsync(
        string deviceId, V2LocalSessionLedger ledger, V2PendingSourceTransfer request)
    {
        if (!_isV2TransferPending)
            ShowTransferWait();
        var token = _lifetime.Token;
        if (request.RestartPending)
        {
            await CompleteSourceRestartAsync(request.OperationId);
            return;
        }

        V2TransferOperation operation;
        try
        {
            operation = await _v2TransferGateway!.BeginTransferAsync(deviceId, ledger.SessionId, request, token);
        }
        catch (RpcException error) when (error.StatusCode is StatusCode.AlreadyExists or StatusCode.InvalidArgument
            or StatusCode.PermissionDenied or StatusCode.NotFound)
        {
            try
            {
                operation = await _v2TransferGateway!.GetTransferOperationAsync(deviceId, request.OperationId, token);
            }
            catch (RpcException absent) when (absent.StatusCode == StatusCode.NotFound && !request.Frozen)
            {
                await ResolveV2SourceAsync(request.OperationId, V2TransferStatus.Cancelled);
                ShowSessionNotification("Не удалось начать перенос. Проверьте доступность места.");
                return;
            }
        }

        if (operation.OperationId != request.OperationId || operation.SessionId != ledger.SessionId
            || operation.TargetWorkstationId != request.TargetWorkstationId)
            throw new InvalidOperationException("Transfer response does not match the local journal");

        if (operation.Status == V2TransferStatus.Preparing)
        {
            if (ledger.Status != V2LocalSessionStatus.Active)
            {
                operation = await _v2TransferGateway!.CancelTransferAsync(deviceId, request.OperationId, token);
            }
            else
            {
                if (!operation.TargetReady)
                    return;
                var checkpoint = await _v2Ledger!.FreezeSourceTransferAsync(request.OperationId, _clock(), token);
                if (checkpoint is null)
                    return;
                if (operation.SourceCheckpoint is null)
                {
                    try
                    {
                        operation = await _v2TransferGateway!.ConfirmTransferSourceAsync(
                            deviceId, request.OperationId, checkpoint, token);
                    }
                    catch (RpcException error) when (error.StatusCode == StatusCode.AlreadyExists)
                    {
                        return; // Kafka may still be confirming the last published fact.
                    }
                }
                if (operation.Status == V2TransferStatus.Preparing)
                {
                    if (operation.SourceCheckpoint != checkpoint)
                        throw new InvalidOperationException("Server transfer checkpoint differs from the local journal");
                    try
                    {
                        operation = await _v2TransferGateway!.CommitTransferAsync(deviceId, request.OperationId, token);
                    }
                    catch (RpcException error) when (error.StatusCode == StatusCode.AlreadyExists)
                    {
                        operation = await _v2TransferGateway!.CancelTransferAsync(deviceId, request.OperationId, token);
                    }
                }
            }
        }
        if (operation.Status != V2TransferStatus.Preparing)
            await ResolveV2SourceAsync(request.OperationId, operation.Status);
    }

    private async Task ResolveV2SourceAsync(Guid operationId, V2TransferStatus status)
    {
        var ledger = await _v2Ledger!.ResolveSourceTransferAsync(
            operationId, status, _lifetime.Token, keepRestartPending: status == V2TransferStatus.Committed);
        if (status == V2TransferStatus.Committed)
        {
            await CompleteSourceRestartAsync(operationId);
            return;
        }

        _isV2TransferPending = false;
        _activeV2Ledger = ledger.Status == V2LocalSessionStatus.Active ? ledger : null;
        if (_activeV2Ledger is not null)
        {
            await ConsumeV2DueMinutesAsync();
            if (_activeV2Ledger is { Status: V2LocalSessionStatus.Active } current && !_isV2MinuteBillingPaused)
                OpenV2Session(current, "Перенос не выполнен. Сессия на этом ПК восстановлена.");
        }
        PublishAccessState();
    }

    private async Task CompleteSourceRestartAsync(Guid operationId)
    {
        LockClient("Сессия перенесена. Перезапуск ПК.");
        if (_powerController?.ScheduleRestart() is { Success: false } failure)
        {
            throw new InvalidOperationException(failure.Message);
        }
        await _v2Ledger!.ResolveSourceTransferAsync(operationId, V2TransferStatus.Committed, _lifetime.Token);
        if (_powerController is null)
        {
            _isV2TransferPending = false;
            PublishAccessState();
        }
    }

    private async Task AdvanceTargetTransferAsync(string deviceId)
    {
        var token = _lifetime.Token;
        var operation = await _v2TransferGateway!.GetPendingTransferAsync(deviceId, token);
        if (operation is null)
        {
            if (_awaitedTargetTransfer is not null)
            {
                _awaitedTargetTransfer = null;
                _isV2TransferPending = false;
                LockClient();
            }
            return;
        }
        if (!Guid.TryParse(WorkstationId, out var workstationId) || operation.TargetWorkstationId != workstationId)
            throw new InvalidOperationException("Transfer target does not match this workstation");

        _awaitedTargetTransfer = operation.OperationId;
        if (!_isV2TransferPending)
            ShowTransferWait();
        if (operation.Status == V2TransferStatus.Preparing && !operation.TargetReady)
            operation = await _v2TransferGateway.ReadyTransferTargetAsync(deviceId, operation.OperationId, token);
        if (operation.Status != V2TransferStatus.Committed)
            return;

        var ledger = await _v2TransferGateway.GetTransferredLedgerAsync(
            deviceId, operation, _v2SignatureVerifier!, token);
        var previous = await _v2Ledger!.ReadSnapshotAsync(token);
        if (previous?.Ledger is { } consumed
            && consumed.SnapshotId == ledger.SnapshotId
            && consumed.Status != V2LocalSessionStatus.Active)
        {
            await StopV2OnServerAsync(consumed, token);
            return;
        }

        await _v2Ledger.InitializeNextSessionAsync(ledger, token);
        _activeV2Ledger = ledger;
        _isV2MinuteBillingPaused = false;
        if (!await CanOpenTransferredLedgerAsync(ledger, token))
            return;

        _awaitedTargetTransfer = null;
        _isV2TransferPending = false;
        OpenV2Session(_activeV2Ledger!, "Сессия перенесена на этот ПК");
    }

    private async Task<bool> CanOpenTransferredLedgerAsync(
        V2LocalSessionLedger ledger, CancellationToken token)
    {
        if (ledger.LastConsumedMinuteUtc is null
            && V2LocalLedgerEngine.CurrentSource(ledger, _clock()) == V2TimeSource.Exhausted)
        {
            var ended = await _v2Ledger!.StopEarlyAsync(Guid.NewGuid(), _clock(), token);
            _activeV2Ledger = null;
            _accessGate.LockSession("Время перенесённой сессии закончилось");
            PublishSessionState();
            PublishAccessState();
            await StopV2OnServerAsync(ended.Ledger, token);
            return false;
        }

        await ConsumeV2DueMinutesAsync();
        return _activeV2Ledger is { Status: V2LocalSessionStatus.Active }
            && !_isV2MinuteBillingPaused;
    }

    private void ShowTransferWait()
    {
        _isV2TransferPending = true;
        _accessGate.Lock("Ожидаем подтверждение переноса сессии");
        _portalMessage = string.Empty;
        PublishSessionState();
        PublishAccessState();
    }
}
