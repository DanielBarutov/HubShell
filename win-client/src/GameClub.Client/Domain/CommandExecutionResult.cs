namespace GameClub.Client.Domain;

public sealed record CommandExecutionResult(bool Success, string Message);
