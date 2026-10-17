using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using GameClub.Client.Domain;

namespace GameClub.Client.Avalonia;

public sealed record BonusPackagePurchaseDecision(bool UseBonus, BonusGameQuote Quote);

public sealed class BonusPackagePurchaseDialog : Window
{
    private readonly ToggleSwitch _toggle = new() { Content = "Оплатить бонусами", IsChecked = false };
    private readonly TextBlock _amounts = new() { TextWrapping = TextWrapping.Wrap, FontSize = 13 };
    private readonly TextBlock _status = new() { TextWrapping = TextWrapping.Wrap, FontSize = 12 };
    private readonly Button _confirm = new() { Content = "Купить", Classes = { "widget-primary" } };
    private BonusGameQuote? _quote;
    private int _request;

    public BonusPackagePurchaseDialog(string name, string duration, BonusGameQuote initial,
        Func<bool, Task<BonusGameQuote?>> getQuote)
    {
        Title = "Подтверждение покупки";
        Width = 390;
        SizeToContent = SizeToContent.Height;
        CanResize = false;
        SystemDecorations = SystemDecorations.None;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Background = new SolidColorBrush(Color.Parse("#020D12"));
        Foreground = new SolidColorBrush(Color.Parse("#EDF5EF"));
        var cancel = new Button { Content = "Отмена", Classes = { "widget-secondary" } };
        cancel.Click += (_, _) => Close(null);
        _confirm.Click += (_, _) => { if (_quote is { CanPay: true } quote) Close(new BonusPackagePurchaseDecision(_toggle.IsChecked == true, quote)); };
        _toggle.IsCheckedChanged += async (_, _) =>
        {
            var request = ++_request;
            _quote = null;
            _confirm.IsEnabled = false;
            _amounts.Text = "";
            _status.Text = "Получаем расчёт сервера…";
            var quote = await getQuote(_toggle.IsChecked == true);
            if (request != _request) return;
            if (quote is null) { _status.Text = "Нет подтверждённого расчёта. Проверьте соединение и переключите выбор повторно."; return; }
            ApplyQuote(quote);
        };
        KeyDown += (_, args) => { if (args.Key == Key.Escape) { Close(null); args.Handled = true; } };
        Opened += (_, _) => cancel.Focus();
        Closed += (_, _) => _request++;
        Content = new Border
        {
            BorderBrush = new SolidColorBrush(Color.Parse("#246176")), BorderThickness = new Thickness(1),
            CornerRadius = new CornerRadius(14), Padding = new Thickness(16),
            Child = new StackPanel { Spacing = 12, Children = {
                new TextBlock { Text = $"Купить «{name}»?", FontSize = 17, FontWeight = FontWeight.SemiBold, TextWrapping = TextWrapping.Wrap },
                new TextBlock { Text = duration }, _toggle, _amounts, _status,
                new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Spacing = 8, Children = { cancel, _confirm } },
            } },
        };
        ApplyQuote(initial);
    }

    private void ApplyQuote(BonusGameQuote quote)
    {
        _quote = quote;
        _confirm.IsEnabled = quote.CanPay;
        _amounts.Text = $"Цена после скидок: {Money(quote.PriceCents)}\nБонусами: {Money(quote.BonusCents)}\nС депозита: {Money(quote.MoneyCents)}\nНачисление: {Money(quote.EarnedBonusCents)}\nДоступно бонусов: {Money(quote.AvailableBonusCents)}\nРезерв для игры: {Money(quote.ReservedBonusCents)}";
        _status.Text = !quote.CanPay ? "Недостаточно средств с учётом допустимого долга."
            : _toggle.IsChecked == true && !quote.BonusAllowed ? "Бонусная оплата недоступна. Пакет будет оплачен с депозита."
            : "Начисление станет доступно после завершения сессии и погашения денежного долга.";
    }

    private static string Money(long cents) => $"{cents / 100m:N2} ₽";
}
