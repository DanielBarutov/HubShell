using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Threading;
using GameClub.Client.Avalonia.Hosting;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia;

public partial class MainWindow : Window
{
    private const double DeveloperAccessGateWidth = 1120;
    private const double DeveloperAccessGateHeight = 680;
    private const double DeveloperWidgetWidth = 390;
    private const double DeveloperWidgetHeight = 1000;
    private readonly IClientHost _clientHost;
    private AccountHistoryWindow? _accountHistoryWindow;
    private bool _normalizingPhone;

    public MainWindow()
        : this(AvaloniaClientHostFactory.Create())
    {
    }

    public MainWindow(IClientHost clientHost)
    {
        _clientHost = clientHost;
        InitializeComponent();
        Title = clientHost.WindowTitle;
        this.FindControl<TextBlock>("HostDisclaimer")!.Text = clientHost.HostDisclaimer;
        this.FindControl<Button>("HideToTrayButton")!.IsVisible = clientHost.WindowAdapter is not null;
        this.FindControl<Button>("OpenDesktopButton")!.IsVisible = clientHost.WindowAdapter is not null;
        if (clientHost.WindowAdapter?.UsesTransparentWindow == true)
        {
            TransparencyLevelHint = [WindowTransparencyLevel.Transparent];
            Background = Brushes.Transparent;
            TransparencyBackgroundFallback = new SolidColorBrush(Color.Parse("#07090D"));
        }
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
        _accountHistoryWindow?.Close();
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

    private void RecordKeyActivity(object? sender, KeyEventArgs args)
    {
        if (ViewModel.TrySuppressLockedSystemShortcut(
                altPressed: (args.KeyModifiers & KeyModifiers.Alt) != 0,
                tabPressed: args.Key == Key.Tab,
                windowsPressed: (args.KeyModifiers & KeyModifiers.Meta) != 0,
                rPressed: args.Key == Key.R))
        {
            args.Handled = true;
            ViewModel.TouchAccessActivity();
            return;
        }

        var openedManagerLogin = ViewModel.TryOpenManagerLoginShortcut(
            controlPressed: (args.KeyModifiers & KeyModifiers.Control) != 0,
            altPressed: (args.KeyModifiers & KeyModifiers.Alt) != 0,
            pPressed: args.Key == Key.P);
        if (openedManagerLogin)
        {
            args.Handled = true;
            Dispatcher.UIThread.Post(() => this.FindControl<TextBox>("ManagerPasswordBox")?.Focus());
        }

        ViewModel.TouchAccessActivity();
    }

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
        if (await ViewModel.SetPortalPasswordAsync())
        {
            ClearTextBox("PortalPasswordSetupBox");
            ClearTextBox("PortalPasswordSetupConfirmationBox");
        }
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

    private void OpenDesktop(object? sender, RoutedEventArgs args) =>
        _clientHost.WindowAdapter?.HideToTray();

    private async void LockClient(object? sender, RoutedEventArgs args) =>
        await ViewModel.LogoutAsync();

    private async void Logout(object? sender, RoutedEventArgs args)
    {
        if (!await ConfirmSessionExitAsync("Выйти из аккаунта?", "Выйти"))
        {
            return;
        }

        await ViewModel.LogoutAsync();
    }

    private void HideToTray(object? sender, RoutedEventArgs args) =>
        _clientHost.WindowAdapter?.HideToTray();

    private async void StopCurrentSession(object? sender, RoutedEventArgs args)
    {
        if (!await ConfirmSessionExitAsync("Завершить игровую сессию?", "Завершить"))
        {
            return;
        }

        await ViewModel.StopActiveSessionAsync();
    }

    private Task<bool> ConfirmSessionExitAsync(string title, string confirmationText) =>
        CreateConfirmationDialog(title,
            "Активная игровая сессия будет завершена. Неиспользованные минуты текущего пакета сгорят.",
            confirmationText).ShowDialog<bool>(this);

    private async void ActivateFirstPortalEntitlement(object? sender, RoutedEventArgs args) =>
        await ViewModel.ActivateFirstPortalEntitlementAsync();

    private void ToggleTransferPanel(object? sender, RoutedEventArgs args) =>
        ViewModel.ToggleTransferPanel();

    private async void CreateTransferOffer(object? sender, RoutedEventArgs args)
    {
        if (!await ConfirmTransferAsync())
        {
            return;
        }

        await ViewModel.CreateTransferOfferAsync();
    }

    private async void ConfirmTransfer(object? sender, RoutedEventArgs args) =>
        await ViewModel.ConfirmTransferAsync();

    private Task<bool> ConfirmTransferAsync() =>
        CreateConfirmationDialog("Пересесть на другой ПК?",
            "После подтверждения войдите в этот же аккаунт на новом ПК. Активная сессия и доступное время перенесутся автоматически. Если зоны несовместимы, активный пакет может быть сожжён по правилам клуба.",
            "Пересесть").ShowDialog<bool>(this);

    private void DismissSessionNotification(object? sender, RoutedEventArgs args) =>
        ViewModel.DismissSessionNotification();

    private void OpenAccountHistory(object? sender, RoutedEventArgs args)
    {
        if (_accountHistoryWindow is null)
        {
            _accountHistoryWindow = new AccountHistoryWindow(
                ViewModel,
                _clientHost.WindowAdapter?.UsesTransparentWindow == true)
            {
                Topmost = Topmost,
            };
            _accountHistoryWindow.Closed += (_, _) => _accountHistoryWindow = null;
            _accountHistoryWindow.Show(this);
            return;
        }

        _accountHistoryWindow.Activate();
    }

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

    private Task<bool> ConfirmTariffPurchaseAsync(string name, string duration, string price) =>
        CreateConfirmationDialog($"Купить «{name}»?",
            $"{duration} · {price}. Сумма будет списана с баланса.",
            "Купить").ShowDialog<bool>(this);

    private Window CreateConfirmationDialog(string title, string message, string confirmationText)
    {
        var dialog = new Window
        {
            Title = title,
            Width = 390,
            SizeToContent = SizeToContent.Height,
            CanResize = false,
            SystemDecorations = SystemDecorations.None,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Topmost = Topmost,
            Background = new SolidColorBrush(Color.Parse("#020D12")),
        };
        var cancel = new Button
        {
            Content = "Отмена", MinWidth = 110,
            HorizontalContentAlignment = HorizontalAlignment.Center,
            VerticalContentAlignment = VerticalAlignment.Center,
            Classes = { "widget-secondary" },
        };
        var confirm = new Button
        {
            Content = confirmationText, MinWidth = 110,
            HorizontalContentAlignment = HorizontalAlignment.Center,
            VerticalContentAlignment = VerticalAlignment.Center,
            Classes = { "widget-primary" },
        };
        cancel.Click += (_, _) => dialog.Close(false);
        confirm.Click += (_, _) => dialog.Close(true);
        dialog.KeyDown += (_, args) =>
        {
            if (args.Key == Key.Escape)
            {
                dialog.Close(false);
                args.Handled = true;
            }
        };
        dialog.Opened += (_, _) => cancel.Focus();
        dialog.Content = new Border
        {
            Background = new LinearGradientBrush
            {
                StartPoint = new RelativePoint(0, 0, RelativeUnit.Relative),
                EndPoint = new RelativePoint(1, 1, RelativeUnit.Relative),
                GradientStops =
                {
                    new GradientStop(Color.Parse("#020D12"), 0),
                    new GradientStop(Color.Parse("#061E2A"), 1),
                },
            },
            BorderBrush = new SolidColorBrush(Color.Parse("#246176")),
            BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(14),
            Padding = new Thickness(16),
            Child = new StackPanel
            {
                Spacing = 12,
                Children =
                {
                    new TextBlock
                    {
                        Text = title, FontSize = 17, FontWeight = FontWeight.SemiBold,
                        TextWrapping = TextWrapping.Wrap,
                        Foreground = new SolidColorBrush(Color.Parse("#EDF5EF")),
                    },
                    new TextBlock
                    {
                        Text = message, FontSize = 12, TextWrapping = TextWrapping.Wrap,
                        Foreground = new SolidColorBrush(Color.Parse("#A6C0C8")),
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
        return dialog;
    }

    private void ClearTextBox(string name)
    {
        if (this.FindControl<TextBox>(name) is { } textBox)
        {
            textBox.Text = string.Empty;
        }
    }

    private void ApplyHostWindowMode()
    {
        var mode = ViewModel.IsMaintenanceMode
            ? ClientWindowMode.Maintenance
            : ViewModel.IsAccessLocked
                ? ClientWindowMode.Locked
                : ClientWindowMode.User;
        if (_clientHost.WindowAdapter is not null)
        {
            _clientHost.WindowAdapter.ApplyWindowMode(mode);
            return;
        }

        WindowState = WindowState.Normal;
        var useAccessGateSize = mode is ClientWindowMode.Locked or ClientWindowMode.Maintenance;
        Width = useAccessGateSize ? DeveloperAccessGateWidth : DeveloperWidgetWidth;
        var widgetHeight = ViewModel.IsGuestWidgetVisible ? 700 : DeveloperWidgetHeight;
        var screen = Screens.ScreenFromWindow(this) ?? Screens.Primary;
        var availableHeight = screen is null
            ? widgetHeight
            : screen.WorkingArea.Height / screen.Scaling - 36;
        MinHeight = useAccessGateSize ? 520 : Math.Min(520, Math.Max(0, availableHeight));
        Height = useAccessGateSize ? DeveloperAccessGateHeight : Math.Clamp(availableHeight, MinHeight, widgetHeight);
    }

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
