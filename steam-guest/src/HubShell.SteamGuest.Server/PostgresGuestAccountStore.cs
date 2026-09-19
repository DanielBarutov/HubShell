using System.Security.Cryptography;
using System.Text;
using HubShell.SteamGuest.Core;
using Npgsql;

namespace HubShell.SteamGuest.Server;

public sealed class PostgresGuestAccountStore : IGuestAccountStore
{
    private readonly string _connectionString;
    private readonly SecretProtector _protector;
    private readonly string _stationKeyPepper;

    public PostgresGuestAccountStore(
        string connectionString,
        SecretProtector protector,
        string stationKeyPepper)
    {
        _connectionString = connectionString;
        _protector = protector;
        _stationKeyPepper = stationKeyPepper;
    }

    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        const string sql = """
            CREATE TABLE IF NOT EXISTS steam_guest_stations (
                station_id text PRIMARY KEY,
                key_hash text NOT NULL,
                created_at timestamptz NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steam_guest_accounts (
                account_id uuid PRIMARY KEY,
                login_ciphertext text NOT NULL,
                password_ciphertext text NOT NULL,
                state text NOT NULL,
                lease_id uuid NULL UNIQUE,
                station_id text NULL,
                leased_at timestamptz NULL,
                released_at timestamptz NULL,
                CHECK (state IN ('available', 'leased', 'blocked', 'needs_review'))
            );
            CREATE INDEX IF NOT EXISTS steam_guest_accounts_available_idx
                ON steam_guest_accounts (state, account_id);
            """;
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task RegisterStationAsync(string stationId, string stationKey, CancellationToken cancellationToken = default)
    {
        ValidateStation(stationId, stationKey);
        const string sql = """
            INSERT INTO steam_guest_stations (station_id, key_hash, created_at)
            VALUES (@station_id, @key_hash, NOW())
            ON CONFLICT (station_id) DO UPDATE SET key_hash = EXCLUDED.key_hash;
            """;
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("station_id", stationId.Trim());
        command.Parameters.AddWithValue("key_hash", HashStationKey(stationKey));
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<Guid> AddAccountAsync(SteamCredentials credentials, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(credentials.Login) || string.IsNullOrWhiteSpace(credentials.Password))
        {
            throw new ArgumentException("Логин и пароль Steam обязательны.");
        }

        var accountId = Guid.NewGuid();
        const string sql = """
            INSERT INTO steam_guest_accounts
                (account_id, login_ciphertext, password_ciphertext, state)
            VALUES (@account_id, @login_ciphertext, @password_ciphertext, 'available');
            """;
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("account_id", accountId);
        command.Parameters.AddWithValue("login_ciphertext", _protector.Protect(credentials.Login.Trim()));
        command.Parameters.AddWithValue("password_ciphertext", _protector.Protect(credentials.Password));
        await command.ExecuteNonQueryAsync(cancellationToken);
        return accountId;
    }

    public async Task<GuestAccountLease> ClaimAsync(
        string stationId,
        string stationKey,
        DateTimeOffset now,
        CancellationToken cancellationToken = default)
    {
        await EnsureStationAsync(stationId, stationKey, cancellationToken);
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        var existing = await ReadLeaseForStationAsync(connection, transaction, stationId, cancellationToken);
        if (existing is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return existing;
        }

        var leaseId = Guid.NewGuid();
        const string claimSql = """
            WITH candidate AS (
                SELECT account_id
                FROM steam_guest_accounts
                WHERE state = 'available'
                ORDER BY account_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE steam_guest_accounts account
            SET state = 'leased', lease_id = @lease_id, station_id = @station_id,
                leased_at = @leased_at, released_at = NULL
            FROM candidate
            WHERE account.account_id = candidate.account_id
            RETURNING account.account_id, account.login_ciphertext, account.password_ciphertext,
                account.station_id, account.leased_at;
            """;
        await using var command = new NpgsqlCommand(claimSql, connection, transaction);
        command.Parameters.AddWithValue("lease_id", leaseId);
        command.Parameters.AddWithValue("station_id", stationId.Trim());
        command.Parameters.AddWithValue("leased_at", now.UtcDateTime);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            await transaction.RollbackAsync(cancellationToken);
            throw new GuestAccountUnavailableException();
        }

        var lease = new GuestAccountLease(
            leaseId,
            reader.GetGuid(0),
            reader.GetString(3),
            new SteamCredentials(_protector.Unprotect(reader.GetString(1)), _protector.Unprotect(reader.GetString(2))),
            new DateTimeOffset(reader.GetDateTime(4), TimeSpan.Zero));
        await reader.CloseAsync();
        await transaction.CommitAsync(cancellationToken);
        return lease;
    }

    public async Task<bool> ReleaseAsync(
        string stationId,
        string stationKey,
        Guid leaseId,
        DateTimeOffset now,
        CancellationToken cancellationToken = default)
    {
        await EnsureStationAsync(stationId, stationKey, cancellationToken);
        const string sql = """
            UPDATE steam_guest_accounts
            SET state = 'available', lease_id = NULL, station_id = NULL, released_at = @released_at
            WHERE lease_id = @lease_id AND station_id = @station_id AND state = 'leased';
            """;
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("lease_id", leaseId);
        command.Parameters.AddWithValue("station_id", stationId.Trim());
        command.Parameters.AddWithValue("released_at", now.UtcDateTime);
        return await command.ExecuteNonQueryAsync(cancellationToken) == 1;
    }

    public async Task<IReadOnlyCollection<GuestAccountSummary>> ListAsync(CancellationToken cancellationToken = default)
    {
        const string sql = """
            SELECT account_id, login_ciphertext, state, station_id, leased_at
            FROM steam_guest_accounts ORDER BY account_id;
            """;
        var result = new List<GuestAccountSummary>();
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(new GuestAccountSummary(
                reader.GetGuid(0),
                _protector.Unprotect(reader.GetString(1)),
                ParseState(reader.GetString(2)),
                reader.IsDBNull(3) ? null : reader.GetString(3),
                reader.IsDBNull(4) ? null : new DateTimeOffset(reader.GetDateTime(4), TimeSpan.Zero)));
        }
        return result;
    }

    private async Task<GuestAccountLease?> ReadLeaseForStationAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, string stationId, CancellationToken cancellationToken)
    {
        const string sql = """
            SELECT lease_id, account_id, station_id, login_ciphertext, password_ciphertext, leased_at
            FROM steam_guest_accounts
            WHERE station_id = @station_id AND state = 'leased'
            FOR UPDATE;
            """;
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue("station_id", stationId.Trim());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }
        return new GuestAccountLease(
            reader.GetGuid(0), reader.GetGuid(1), reader.GetString(2),
            new SteamCredentials(_protector.Unprotect(reader.GetString(3)), _protector.Unprotect(reader.GetString(4))),
            new DateTimeOffset(reader.GetDateTime(5), TimeSpan.Zero));
    }

    private async Task EnsureStationAsync(string stationId, string stationKey, CancellationToken cancellationToken)
    {
        ValidateStation(stationId, stationKey);
        const string sql = "SELECT key_hash FROM steam_guest_stations WHERE station_id = @station_id;";
        await using var connection = new NpgsqlConnection(_connectionString);
        await connection.OpenAsync(cancellationToken);
        await using var command = new NpgsqlCommand(sql, connection);
        command.Parameters.AddWithValue("station_id", stationId.Trim());
        var storedHash = await command.ExecuteScalarAsync(cancellationToken) as string;
        if (storedHash is null || !CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(storedHash), Convert.FromHexString(HashStationKey(stationKey))))
        {
            throw new StationAccessDeniedException();
        }
    }

    private string HashStationKey(string stationKey) => Convert.ToHexString(
        SHA256.HashData(Encoding.UTF8.GetBytes($"{_stationKeyPepper}:{stationKey}")));

    private static void ValidateStation(string stationId, string stationKey)
    {
        if (string.IsNullOrWhiteSpace(stationId) || stationId.Length > 128 || string.IsNullOrWhiteSpace(stationKey))
        {
            throw new ArgumentException("Нужны корректные идентификатор и ключ станции.");
        }
    }

    private static GuestAccountState ParseState(string state) => state switch
    {
        "available" => GuestAccountState.Available,
        "leased" => GuestAccountState.Leased,
        "blocked" => GuestAccountState.Blocked,
        _ => GuestAccountState.NeedsReview,
    };
}
