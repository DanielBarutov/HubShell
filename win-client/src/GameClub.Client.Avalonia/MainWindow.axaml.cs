using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using GameClub.Client.Avalonia.Development;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia;

public partial class MainWindow : Window
{
    private readonly IClientHost _clientHost;
    private bool _normalizingPhone;

    public MainWindow()
        : this(new LocalBackendClientHost())
    {
    }

    public MainWindow(IClientHost clientHost)
    {
        _clientHost = clientHost;
        InitializeComponent();
        Title = clientHost.WindowTitle;
        this.FindControl<TextBlock>("HostDisclaimer")!.Text = clientHost.HostDisclaimer;
        this.FindControl<Button>("HideToTrayButton")!.IsVisible = clientHost.WindowAdapter is not null;
        DataContext = _clientHost.ViewModel;
        ViewModel.PropertyChanged += ViewModelPropertyChanged;
        Opened += MainWindowOpened;
        Closed += MainWindowClosed;
    }

    private MainViewModel ViewModel => _clientHost.ViewModel;

    private async void MainWindowOpened(object? sender, EventArgs args)
    {
        _clientHost.WindowAdapter?.Attach(this);
        ApplyHostWindowMode();
        await _clientHost.StartAsync();
    }

    private async void MainWindowClosed(object? sender, EventArgs args)
    {
        ViewModel.PropertyChanged -= ViewModelPropertyChanged;
        _clientHost.WindowAdapter?.Dispose();
        await _clientHost.DisposeAsync();
    }

    private void ViewModelPropertyChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName == nameof(MainViewModel.ThemeName))
        {
            Dispatcher.UIThread.Post(() =>
            {
                if (global::Avalonia.Application.Current is App application)
                {
                    application.ApplyWorkstationTheme(ViewModel.ThemeName);
                }
            });
        }

        if (args.PropertyName is nameof(MainViewModel.IsAccessLocked)
            or nameof(MainViewModel.IsMaintenanceMode))
        {
            Dispatcher.UIThread.Post(ApplyHostWindowMode);
        }
    }

    private void RecordKeyActivity(object? sender, KeyEventArgs args) =>
        ViewModel.TouchAccessActivity();

    private void RecordPointerActivity(object? sender, PointerPressedEventArgs args) =>
        ViewModel.TouchAccessActivity();

    private void PortalIdentifierChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalIdentifier = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPassword = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalNicknameChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalNickname = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPhoneChanged(object? sender, TextChangedEventArgs args)
    {
        if (sender is not TextBox textBox || _normalizingPhone)
        {
            return;
        }

        var formatted = FormatRussianPhone(textBox.Text ?? string.Empty);
        if (!string.Equals(textBox.Text, formatted, StringComparison.Ordinal))
        {
            _normalizingPhone = true;
            textBox.Text = formatted;
            textBox.CaretIndex = formatted.Length;
            _normalizingPhone = false;
        }

        ViewModel.PortalPhone = formatted;
    }

    private void PortalRegistrationPasswordChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalRegistrationPassword = ((TextBox)sender!).Text ?? string.Empty;

    private void ManagerPasswordChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.ManagerPassword = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordSetupChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPasswordSetup = ((TextBox)sender!).Text ?? string.Empty;

    private void PortalPasswordSetupConfirmationChanged(object? sender, TextChangedEventArgs args) =>
        ViewModel.PortalPasswordSetupConfirmation = ((TextBox)sender!).Text ?? string.Empty;

    private async void RefreshConnection(object? sender, RoutedEventArgs args) =>
        await ViewModel.RefreshConnectionAsync();

    private void OpenPortalRegistration(object? sender, RoutedEventArgs args) =>
        ViewModel.ShowPortalRegistration();

    private void CancelPortalRegistration(object? sender, RoutedEventArgs args)
    {
        ClearTextBox("PortalRegistrationPasswordBox");
        ViewModel.CancelPortalRegistration();
    }

    private async void LoginPortal(object? sender, RoutedEventArgs args)
    {
        await ViewModel.LoginPortalAsync();
        ClearTextBox("PortalPasswordBox");
    }

    private async void RegisterPortal(object? sender, RoutedEventArgs args)
    {
        await ViewModel.RegisterPortalAsync();
        ClearTextBox("PortalRegistrationPasswordBox");
    }

    private async void SetPortalPassword(object? sender, RoutedEventArgs args)
    {
        await ViewModel.SetPortalPasswordAsync();
        ClearTextBox("PortalPasswordSetupBox");
        ClearTextBox("PortalPasswordSetupConfirmationBox");
    }

    private void OpenManagerLogin(object? sender, RoutedEventArgs args) =>
        ViewModel.ShowManagerLogin();

    private void CancelManagerLogin(object? sender, RoutedEventArgs args)
    {
        ClearTextBox("ManagerPasswordBox");
        ViewModel.CancelManagerLogin();
    }

    private void EnterMaintenance(object? sender, RoutedEventArgs args)
    {
        var entered = ViewModel.TryEnterMaintenance();
        ClearTextBox("ManagerPasswordBox");
        if (!entered)
        {
            this.FindControl<TextBox>("ManagerPasswordBox")?.Focus();
        }
    }

    private async void LockClient(object? sender, RoutedEventArgs args) =>
        await ViewModel.LogoutAsync();

    private async void Logout(object? sender, RoutedEventArgs args) =>
        await ViewModel.LogoutAsync();

    private void HideToTray(object? sender, RoutedEventArgs args) =>
        _clientHost.WindowAdapter?.HideToTray();

    private async void StopCurrentSession(object? sender, RoutedEventArgs args) =>
        await ViewModel.StopActiveSessionAsync();

    private async void ActivateFirstPortalEntitlement(object? sender, RoutedEventArgs args) =>
        await ViewModel.ActivateFirstPortalEntitlementAsync();

    private void ToggleTransferPanel(object? sender, RoutedEventArgs args) =>
        ViewModel.ToggleTransferPanel();

    private async void CreateTransferOffer(object? sender, RoutedEventArgs args) =>
        await ViewModel.CreateTransferOfferAsync();

    private async void ConfirmTransfer(object? sender, RoutedEventArgs args) =>
        await ViewModel.ConfirmTransferAsync();

    private void DismissSessionNotification(object? sender, RoutedEventArgs args) =>
        ViewModel.DismissSessionNotification();

    private async void PurchaseTariff(object? sender, RoutedEventArgs args)
    {
        if (sender is not Button { Tag: string tariffId })
        {
            return;
        }

        var tariff = ViewModel.FindPortalTariff(tariffId);
        if (tariff is null || !await ConfirmTariffPurchaseAsync(tariff.Name, tariff.DurationSummary, tariff.PriceSummary))
        {
            return;
        }

        await ViewModel.PurchasePortalTariffAsync(tariffId);
    }

    private async Task<bool> ConfirmTariffPurchaseAsync(string name, string duration, string price)
    {
        var dialog = new Window
        {
            Title = "Подтвердите покупку",
            Width = 410,
            Height = 220,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = new SolidColorBrush(Color.Parse("#0F1719")),
        };
        var cancel = new Button { Content = "Отмена", MinWidth = 100 };
        var confirm = new Button
        {
            Content = "Купить",
            MinWidth = 100,
            Background = new SolidColorBrush(Color.Parse("#B6F35A")),
            Foreground = new SolidColorBrush(Color.Parse("#11180C")),
        };
        cancel.Click += (_, _) => dialog.Close(false);
        confirm.Click += (_, _) => dialog.Close(true);
        dialog.Content = new Border
        {
            Padding = new Thickness(22),
            Child = new StackPanel
            {
                Spacing = 12,
                Children =
                {
                    new TextBlock
                    {
                        Text = $"Купить «{name}»?",
                        FontSize = 18,
                        FontWeight = FontWeight.SemiBold,
                        Foreground = new SolidColorBrush(Color.Parse("#EDF5EF")),
                    },
                    new TextBlock
                    {
                        Text = $"{duration} · {price}. Сумма будет списана с баланса.",
                        TextWrapping = TextWrapping.Wrap,
                        Foreground = new SolidColorBrush(Color.Parse("#B9C5C0")),
                    },
                    new StackPanel
                    {
                        Orientation = Orientation.Horizontal,
                        HorizontalAlignment = HorizontalAlignment.Right,
                        Spacing = 8,
                        Children = { cancel, confirm },
                    },
                },
            },
        };

        return await dialog.ShowDialog<bool>(this);
    }

    private void ClearTextBox(string name)
    {
        if (this.FindControl<TextBox>(name) is { } textBox)
        {
            textBox.Text = string.Empty;
        }
    }

    private void ApplyHostWindowMode() =>
        _clientHost.WindowAdapter?.ApplyWindowMode(
            ViewModel.IsAccessLocked || ViewModel.IsMaintenanceMode);

    private static string FormatRussianPhone(string value)
    {
        var digits = new string(value.Where(char.IsDigit).ToArray());
        if (digits.StartsWith('7') || digits.StartsWith('8'))
        {
            digits = digits[1..];
        }
        if (digits.Length > 10)
        {
            digits = digits[..10];
        }
        if (digits.Length == 0)
        {
            return "+7 (";
        }

        var result = $"+7 ({digits[0]}";
        if (digits.Length > 1)
        {
            result += digits[1..Math.Min(3, digits.Length)];
        }
        if (digits.Length >= 3)
        {
            result += ")";
        }
        if (digits.Length > 3)
        {
            result += $" {digits[3..Math.Min(6, digits.Length)]}";
        }
        if (digits.Length > 6)
        {
            result += $"-{digits[6..Math.Min(8, digits.Length)]}";
        }
        if (digits.Length > 8)
        {
            result += $"-{digits[8..Math.Min(10, digits.Length)]}";
        }
        return result;
    }
}
