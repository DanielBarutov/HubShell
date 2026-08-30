namespace GameClub.Client.Application.Ports;

public interface ITokenProvider
{
    ValueTask<string?> GetAccessTokenAsync(CancellationToken cancellationToken = default);
}
