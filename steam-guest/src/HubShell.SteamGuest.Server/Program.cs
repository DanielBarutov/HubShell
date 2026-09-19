using HubShell.SteamGuest.Core;
using HubShell.SteamGuest.Server;
using System.Text.Json.Serialization;

var builder = WebApplication.CreateBuilder(args);
var configuration = builder.Configuration;
var postgresDsn = Required(configuration, "STEAM_GUEST_POSTGRES_DSN");
var masterKey = Required(configuration, "STEAM_GUEST_MASTER_KEY");
var adminKey = Required(configuration, "STEAM_GUEST_ADMIN_KEY");
var stationKeyPepper = Required(configuration, "STEAM_GUEST_STATION_KEY_PEPPER");

builder.Services.AddSingleton(new SecretProtector(masterKey));
builder.Services.ConfigureHttpJsonOptions(options =>
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter()));
builder.Services.AddSingleton(services => new PostgresGuestAccountStore(
    postgresDsn,
    services.GetRequiredService<SecretProtector>(),
    stationKeyPepper));
builder.Services.AddSingleton<IGuestAccountStore>(services =>
    services.GetRequiredService<PostgresGuestAccountStore>());
builder.Services.AddHostedService<ExpiredLeaseWorker>();

var app = builder.Build();
var store = app.Services.GetRequiredService<PostgresGuestAccountStore>();
await store.InitializeAsync();

app.MapGet("/health/live", () => Results.Ok(new { status = "ok" }));

app.MapPost("/v1/stations", async (StationRequest request, HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    if (!HasKey(http, "X-Steam-Guest-Admin-Key", adminKey))
    {
        return Results.Unauthorized();
    }
    await accounts.RegisterStationAsync(request.StationId, request.StationKey, cancellationToken);
    return Results.NoContent();
});

app.MapPost("/v1/accounts", async (AccountRequest request, HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    if (!HasKey(http, "X-Steam-Guest-Admin-Key", adminKey))
    {
        return Results.Unauthorized();
    }
    var accountId = await accounts.AddAccountAsync(new SteamCredentials(request.Login, request.Password), cancellationToken);
    return Results.Created($"/v1/accounts/{accountId}", new { accountId });
});

app.MapGet("/v1/accounts", async (HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    if (!HasKey(http, "X-Steam-Guest-Admin-Key", adminKey))
    {
        return Results.Unauthorized();
    }
    return Results.Ok(await accounts.ListAsync(cancellationToken));
});

app.MapPost("/v1/leases/claim", async (LeaseClaimRequest request, HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    try
    {
        var lease = await accounts.ClaimAsync(
            request.StationId,
            Header(http, "X-Steam-Guest-Station-Key"),
            DateTimeOffset.UtcNow,
            cancellationToken);
        return Results.Ok(new LeaseResponse(lease.LeaseId, lease.Credentials.Login, lease.Credentials.Password));
    }
    catch (StationAccessDeniedException)
    {
        return Results.Unauthorized();
    }
    catch (GuestAccountUnavailableException)
    {
        return Results.Conflict(new { code = "no_available_account", message = "Нет свободного гостевого Steam-аккаунта." });
    }
});

app.MapPost("/v1/leases/{leaseId:guid}/release", async (Guid leaseId, LeaseReleaseRequest request, HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    try
    {
        var released = await accounts.ReleaseAsync(
            request.StationId,
            Header(http, "X-Steam-Guest-Station-Key"),
            leaseId,
            DateTimeOffset.UtcNow,
            cancellationToken);
        return released ? Results.NoContent() : Results.Conflict(new { code = "lease_not_active" });
    }
    catch (StationAccessDeniedException)
    {
        return Results.Unauthorized();
    }
});

app.MapPost("/v1/leases/{leaseId:guid}/confirm", async (Guid leaseId, LeaseConfirmationRequest request, HttpRequest http, IGuestAccountStore accounts, CancellationToken cancellationToken) =>
{
    try
    {
        var renewed = await accounts.RenewAsync(
            request.StationId,
            Header(http, "X-Steam-Guest-Station-Key"),
            leaseId,
            DateTimeOffset.UtcNow,
            cancellationToken);
        return renewed ? Results.NoContent() : Results.Conflict(new { code = "lease_not_active" });
    }
    catch (StationAccessDeniedException)
    {
        return Results.Unauthorized();
    }
});

app.Run();

static string Required(IConfiguration configuration, string name) =>
    configuration[name] is { Length: > 0 } value
        ? value
        : throw new InvalidOperationException($"Не задана обязательная переменная {name}.");

static bool HasKey(HttpRequest request, string name, string expected) =>
    string.Equals(Header(request, name), expected, StringComparison.Ordinal);

static string Header(HttpRequest request, string name) => request.Headers[name].ToString();

public sealed record StationRequest(string StationId, string StationKey);
public sealed record AccountRequest(string Login, string Password);
public sealed record LeaseClaimRequest(string StationId);
public sealed record LeaseReleaseRequest(string StationId);
public sealed record LeaseConfirmationRequest(string StationId);
public sealed record LeaseResponse(Guid LeaseId, string Login, string Password);
