using GameClub.Client.Presentation;
using Avalonia.Controls;

namespace GameClub.Client.Avalonia.Hosting;

/// <summary>
/// Владеет одной сборкой клиента. Окно Avalonia остаётся независимым от платформы,
/// host разработки и production-host передают собственные транспорты и адаптеры.
/// </summary>
public interface IClientHost : IAsyncDisposable
{
    MainViewModel ViewModel { get; }

    string WindowTitle { get; }

    string HostDisclaimer { get; }

    /// <summary>
    /// Необязательное нативное поведение рабочего стола, за которое отвечает выбранный host.
    /// Linux developer-host намеренно оставляет это свойство пустым.
    /// </summary>
    IClientWindowAdapter? WindowAdapter { get; }

    Task StartAsync();
}

/// <summary>
/// Изолирует платформенное поведение окна и трея от общего представления
/// access-gate и личного кабинета. Реализация подключается только после того,
/// как Avalonia создаст нативный дескриптор окна.
/// </summary>
public interface IClientWindowAdapter : IDisposable
{
    /// <summary>
    /// Запрашивает прозрачную нативную поверхность до открытия окна. Это нужно
    /// только адаптерам, которые рисуют скруглённые внешние углы.
    /// </summary>
    bool UsesTransparentWindow { get; }

    void Attach(Window window);

    void ApplyWindowMode(ClientWindowMode mode);

    void HideToTray();
}
