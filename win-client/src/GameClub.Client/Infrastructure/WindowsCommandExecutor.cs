using System.Text.Json;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;

namespace GameClub.Client.Infrastructure;

public sealed class WindowsCommandExecutor : IWorkstationCommandExecutor
{
    private static readonly IReadOnlySet<string> AllowedThemes = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
    {
        "standard",
        "vip",
        "neon",
        "minimal",
        "Обычный зал",
        "VIP-зона",
        "Неон",
        "Минимал",
    };
    private readonly string? _deviceId;
    private readonly IWorkstationSessionGateway? _sessionGateway;
    private readonly IWorkstationPowerController _powerController;
    private readonly Action<string>? _themeConsumer;
    private readonly Action<SessionSnapshot>? _sessionStarted;
    private readonly Action<SessionSnapshot>? _sessionStopped;
    private readonly Action? _displayLockConsumer;

    public WindowsCommandExecutor(
        string? deviceId = null,
        IWorkstationSessionGateway? sessionGateway = null,
        Action<string>? themeConsumer = null,
        IWorkstationPowerController? powerController = null,
        Action<SessionSnapshot>? sessionStarted = null,
        Action<SessionSnapshot>? sessionStopped = null,
        Action? displayLockConsumer = null)
    {
        _deviceId = deviceId;
        _sessionGateway = sessionGateway;
        _powerController = powerController ?? new WindowsWorkstationPowerController();
        _themeConsumer = themeConsumer;
        _sessionStarted = sessionStarted;
        _sessionStopped = sessionStopped;
        _displayLockConsumer = displayLockConsumer;
    }

    public async Task<CommandExecutionResult> ExecuteAsync(
        WorkstationCommandSnapshot command,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        switch (command.CommandType)
        {
            case "display.lock":
                return LockClientShell();
            case "theme.apply":
                return ApplyTheme(command.PayloadJson);
            case "session.start":
                return await StartSessionAsync(command, cancellationToken);
            case "session.stop":
                return await StopSessionAsync(command, cancellationToken);
            case "system.restart":
                return RestartWorkstation();
            default:
                return new CommandExecutionResult(false, "Команда не поддерживается клиентом");
        }
    }

    private CommandExecutionResult LockClientShell()
    {
        if (_displayLockConsumer is null)
        {
            return new CommandExecutionResult(false, "Блокировка клиентской оболочки не подключена");
        }

        // Do not call LockWorkStation here. It opens the Windows logon screen and
        // bypasses the GameClub access-gate. SmartShell-like behavior is an
        // application-shell lock; the OS kiosk policy is configured separately.
        _displayLockConsumer();
        return new CommandExecutionResult(true, "Клиентская оболочка заблокирована");
    }

    private CommandExecutionResult ApplyTheme(string payloadJson)
    {
        try
        {
            using var payload = JsonDocument.Parse(payloadJson);
            if (!payload.RootElement.TryGetProperty("theme", out var themeElement)
                || themeElement.ValueKind != JsonValueKind.String)
            {
                return new CommandExecutionResult(false, "Для theme.apply нужна строка theme");
            }

            var theme = themeElement.GetString()?.Trim();
            if (string.IsNullOrWhiteSpace(theme) || theme.Length > 64 || !AllowedThemes.Contains(theme))
            {
                return new CommandExecutionResult(false, "Тема имеет недопустимое имя");
            }

            if (_themeConsumer is null)
            {
                return new CommandExecutionResult(false, "Применение темы не подключено к UI");
            }

            _themeConsumer(theme);
            return new CommandExecutionResult(true, $"Тема {theme} применена");
        }
        catch (JsonException)
        {
            return new CommandExecutionResult(false, "Payload команды имеет неверный JSON");
        }
    }

    private async Task<CommandExecutionResult> StartSessionAsync(
        WorkstationCommandSnapshot command,
        CancellationToken cancellationToken)
    {
        var deviceId = _deviceId;
        if (_sessionGateway is null || string.IsNullOrWhiteSpace(deviceId))
        {
            return new CommandExecutionResult(false, "Session gateway не настроен");
        }

        try
        {
            using var payload = JsonDocument.Parse(command.PayloadJson);
            var clientId = ReadOptionalString(payload.RootElement, "client_id");
            var guestName = ReadOptionalString(payload.RootElement, "guest_name");
            var reservationId = ReadOptionalString(payload.RootElement, "reservation_id");
            if (string.IsNullOrWhiteSpace(clientId))
            {
                guestName ??= "Гость";
            }
            var tariffId = ReadOptionalString(payload.RootElement, "tariff_id");
            var tariffQuantity = ReadPositiveInt(payload.RootElement, "tariff_quantity") ?? 1;

            var entry = await _sessionGateway.CheckEntryAsync(
                command.WorkstationId,
                clientId,
                ReadOptionalString(payload.RootElement, "guest_id"),
                cancellationToken);
            if (!entry.Allowed)
            {
                return new CommandExecutionResult(false, $"Вход отклонён: {entry.Reason}");
            }

            var session = await _sessionGateway.StartSessionAsync(
                command.WorkstationId,
                deviceId,
                clientId,
                guestName,
                reservationId,
                command.IdempotencyKey,
                cancellationToken,
                tariffId,
                tariffQuantity);
            try
            {
                session = await _sessionGateway.GetSessionSnapshotAsync(
                    session.Id,
                    deviceId,
                    cancellationToken);
            }
            catch (Exception)
            {
                // The start result remains usable if the follow-up snapshot is
                // temporarily unavailable; the next heartbeat can refresh it.
            }
            _sessionStarted?.Invoke(session);
            return new CommandExecutionResult(true, $"Сессия {session.Id} открыта");
        }
        catch (JsonException)
        {
            return new CommandExecutionResult(false, "Payload команды имеет неверный JSON");
        }
    }

    private async Task<CommandExecutionResult> StopSessionAsync(
        WorkstationCommandSnapshot command,
        CancellationToken cancellationToken)
    {
        var deviceId = _deviceId;
        if (_sessionGateway is null || string.IsNullOrWhiteSpace(deviceId))
        {
            return new CommandExecutionResult(false, "Session gateway не настроен");
        }

        try
        {
            using var payload = JsonDocument.Parse(command.PayloadJson);
            var sessionId = ReadOptionalString(payload.RootElement, "session_id");
            if (string.IsNullOrWhiteSpace(sessionId))
            {
                return new CommandExecutionResult(false, "Для session.stop нужен session_id");
            }

            var session = await _sessionGateway.StopSessionAsync(
                sessionId,
                deviceId,
                cancellationToken);
            try
            {
                session = await _sessionGateway.GetSessionSnapshotAsync(
                    session.Id,
                    deviceId,
                    cancellationToken);
            }
            catch (Exception)
            {
                // Keep the confirmed stop result when snapshot refresh is down.
            }
            _sessionStopped?.Invoke(session);
            return new CommandExecutionResult(true, $"Сессия {session.Id} завершена");
        }
        catch (JsonException)
        {
            return new CommandExecutionResult(false, "Payload команды имеет неверный JSON");
        }
    }

    private CommandExecutionResult RestartWorkstation() => _powerController.ScheduleRestart();

    private static string? ReadOptionalString(JsonElement payload, string propertyName)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            return null;
        }
        if (!payload.TryGetProperty(propertyName, out var value)
            || value.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        var result = value.GetString()?.Trim();
        return string.IsNullOrWhiteSpace(result) ? null : result;
    }

    private static int? ReadPositiveInt(JsonElement payload, string propertyName)
    {
        if (payload.ValueKind != JsonValueKind.Object
            || !payload.TryGetProperty(propertyName, out var value)
            || value.ValueKind != JsonValueKind.Number
            || !value.TryGetInt32(out var result)
            || result <= 0)
        {
            return null;
        }

        return Math.Min(result, 100);
    }

}
