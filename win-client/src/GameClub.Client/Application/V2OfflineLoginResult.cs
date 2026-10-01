using GameClub.Client.Domain;

namespace GameClub.Client.Application;

public sealed record V2OfflineLoginResult(
    V2LocalSessionLedger? Ledger,
    bool PasswordResetRequired,
    string? PasswordResetToken);
