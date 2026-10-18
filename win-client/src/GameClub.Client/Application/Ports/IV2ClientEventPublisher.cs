using GameClub.Client.Domain;

namespace GameClub.Client.Application.Ports;

/// <summary>
/// Транспорт V2-фактов. Реализация может быть Kafka-клиентом или device gateway,
/// но не меняет event id, sequence, hash и payload.
/// </summary>
public interface IV2ClientEventPublisher
{
    Task PublishAsync(
        V2LocalFact fact,
        CancellationToken cancellationToken = default);
}
