using System.Net.Http.Headers;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Domain;
using Google.Protobuf;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Передаёт неизменяемый V2 envelope на backend ingress. Kafka credentials и
/// broker address не покидают backend; повтор безопасен за счёт event id,
/// operation id и server-side inbox.
/// </summary>
public sealed class V2HttpClientEventPublisher : IV2ClientEventPublisher
{
    private readonly HttpClient _httpClient;
    private readonly Uri _endpoint;
    private readonly ITokenProvider _tokenProvider;

    public V2HttpClientEventPublisher(
        HttpClient httpClient,
        Uri endpoint,
        ITokenProvider tokenProvider)
    {
        _httpClient = httpClient;
        _endpoint = endpoint;
        _tokenProvider = tokenProvider;
    }

    public async Task PublishAsync(
        V2LocalFact fact,
        CancellationToken cancellationToken = default)
    {
        var token = await _tokenProvider.GetAccessTokenAsync(cancellationToken);
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("Device enrollment has not issued an access token."));
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, _endpoint)
        {
            Content = new ByteArrayContent(V2EventProtobufSerializer.Serialize(fact).ToByteArray()),
        };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/protobuf");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        var detail = await response.Content.ReadAsStringAsync(cancellationToken);
        throw new HttpRequestException(
            $"V2 event ingress returned {(int)response.StatusCode}: {detail}",
            inner: null,
            response.StatusCode);
    }
}
