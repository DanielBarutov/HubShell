using Avalonia.Controls;
using GameClub.Client.Avalonia.Development;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia;

public partial class MainWindow : Window
{
    private readonly LocalBackendClientHost _clientHost = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _clientHost.ViewModel;
        Opened += MainWindowOpened;
        Closed += MainWindowClosed;
    }

    private MainViewModel ViewModel => _clientHost.ViewModel;

    private async void MainWindowOpened(object? sender, EventArgs args) =>
        await _clientHost.StartAsync();

    private async void MainWindowClosed(object? sender, EventArgs args) =>
        await _clientHost.DisposeAsync();

    private void PortalIdentifierChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalIdentifier = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPassword = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalNicknameChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalNickname = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPhoneChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPhone = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalRegistrationPasswordChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalRegistrationPassword = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordSetupChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPasswordSetup = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordSetupConfirmationChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPasswordSetupConfirmation = ((TextBox)sender!).Text ?? string.Empty;

    private async void RefreshConnection(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        await ViewModel.RefreshConnectionAsync();

    private void OpenPortalRegistration(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        ViewModel.ShowPortalRegistration();

    private void CancelPortalRegistration(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        ViewModel.CancelPortalRegistration();

    private async void LoginPortal(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        await ViewModel.LoginPortalAsync();

    private async void RegisterPortal(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        await ViewModel.RegisterPortalAsync();

    private async void SetPortalPassword(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        await ViewModel.SetPortalPasswordAsync();

    private async void Logout(object? sender, global::Avalonia.Interactivity.RoutedEventArgs args) =>
        await ViewModel.LogoutAsync();
}
