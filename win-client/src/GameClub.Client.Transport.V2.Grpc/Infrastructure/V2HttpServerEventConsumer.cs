using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using GameClub.Client.Application;
using GameClub.Client.Application.Ports;
using GameClub.Client.Contracts.Events.V2;
using Google.Protobuf;

namespace GameClub.Client.Infrastructure;

/// <summary>
/// Polls addressable server events and acknowledges them only after the local
/// processor has committed ClientInbox and ledger state.
/// </summary>
public sealed class V2HttpServerEventConsumer
{
    private readonly HttpClient _httpClient;
    private readonly Uri _endpoint;
    private readonly ITokenProvider _tokenProvider;
    private readonly V2ServerEventProcessor _processor;

    public V2HttpServerEventConsumer(
        HttpClient httpClient,
        Uri endpoint,
        ITokenProvider tokenProvider,
        V2ServerEventProcessor processor)
    {
        _httpClient = httpClient;
        _endpoint = endpoint;
        _tokenProvider = tokenProvider;
        _processor = processor;
    }

    public async Task<V2ServerEventPollResult> PollOnceAsync(
        CancellationToken cancellationToken = default)
    {
        var token = await RequireTokenAsync(cancellationToken);
        using var request = new HttpRequestMessage(HttpMethod.Get, AddLimit(_endpoint));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        var payload = await response.Content.ReadFromJsonAsync<ServerEventPollResponse>(
            cancellationToken);
        if (payload is null)
        {
            throw new HttpRequestException("V2 server event endpoint returned an empty response.");
        }

        var acknowledged = 0;
        var rejected = 0;
        foreach (var item in payload.Events)
        {
            EventEnvelope envelope;
            try
            {
                envelope = EventEnvelope.Parser.ParseFrom(
                    Convert.FromBase64String(item.PayloadBase64));
            }
            catch (Exception error) when (error is FormatException or InvalidProtocolBufferException)
            {
                rejected++;
                continue;
            }

            if (!string.Equals(item.EventId, envelope.EventId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(item.OperationId, envelope.OperationId, StringComparison.OrdinalIgnoreCase))
            {
                rejected++;
                continue;
            }

            var result = await _processor.ProcessAsync(envelope, cancellationToken);
            if (result.Status is not (
                V2EventProcessingStatus.Accepted
                or V2EventProcessingStatus.Duplicate))
            {
                rejected++;
                continue;
            }

            await AcknowledgeAsync(item.EventId, token, cancellationToken);
            acknowledged++;
        }

        return new V2ServerEventPollResult(payload.Events.Count, acknowledged, rejected);
    }

    private async Task AcknowledgeAsync(
        string eventId,
        string token,
        CancellationToken cancellationToken)
    {
        if (!Guid.TryParse(eventId, out var parsed) || parsed == Guid.Empty)
        {
            throw new HttpRequestException("V2 server event returned an invalid event id.");
        }

        var endpoint = new Uri(
            _endpoint.ToString().TrimEnd('/') + $"/{parsed:D}/acknowledge",
            UriKind.Absolute);
        using var request = new HttpRequestMessage(HttpMethod.Post, endpoint);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        using var response = await _httpClient.SendAsync(request, cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
    }

    private async ValueTask<string> RequireTokenAsync(CancellationToken cancellationToken)
    {
        var token = await _tokenProvider.GetAccessTokenAsync(cancellationToken);
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new DeviceAuthenticationRequiredException(
                new InvalidOperationException("Device enrollment has not issued an access token."));
        }

        return token;
    }

    private static Uri AddLimit(Uri endpoint)
    {
        var builder = new UriBuilder(endpoint)
        {
            Query = "limit=100",
        };
        return builder.Uri;
    }

    private static async Task EnsureSuccessAsync(
        HttpResponseMessage response,
        CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        var detail = await response.Content.ReadAsStringAsync(cancellationToken);
        throw new HttpRequestException(
            $"V2 server event endpoint returned {(int)response.StatusCode}: {detail}",
            inner: null,
            response.StatusCode);
    }

    private sealed class ServerEventPollResponse
    {
        [JsonPropertyName("events")]
        public List<ServerEventItem> Events { get; init; } = [];
    }

    private sealed class ServerEventItem
    {
        [JsonPropertyName("event_id")]
        public string EventId { get; init; } = string.Empty;

        [JsonPropertyName("payload_base64")]
        public string PayloadBase64 { get; init; } = string.Empty;

        [JsonPropertyName("operation_id")]
        public string OperationId { get; init; } = string.Empty;
    }
}

public sealed record V2ServerEventPollResult(int ReceivedCount, int AcknowledgedCount, int RejectedCount);
