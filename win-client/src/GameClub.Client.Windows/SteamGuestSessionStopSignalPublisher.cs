using System.IO.Pipes;
using System.Text;

namespace GameClub.Client.Windows;

/// <summary>
/// Сообщает отдельному агенту Steam только о подтверждённой сервером остановке
/// сессии. Не читает и не подтверждает команды HubShell.
/// </summary>
internal static class SteamGuestSessionStopSignalPublisher
{
    private const string PipeName = "HubShell.SteamGuest.SessionStopped";

    public static async Task PublishAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            using var client = new NamedPipeClientStream(
                ".", PipeName, PipeDirection.Out, PipeOptions.Asynchronous);
            await client.ConnectAsync(500, cancellationToken);
            await using var writer = new StreamWriter(client, new UTF8Encoding(false), leaveOpen: false);
            await writer.WriteLineAsync("session-stopped");
        }
        catch (TimeoutException)
        {
            // Гостевой Steam-агент не запущен. Завершение основной сессии не
            // должно из-за этого считаться ошибкой.
        }
        catch (IOException)
        {
            // Агент завершился между подключением и отправкой; он самостоятельно
            // оставит аренду занятой для ручной проверки.
        }
    }
}
