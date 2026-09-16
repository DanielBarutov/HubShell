using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using GameClub.Client.Presentation;

namespace GameClub.Client.Avalonia;

public partial class AccountHistoryWindow : Window
{
    public AccountHistoryWindow()
    {
        InitializeComponent();
    }

    public AccountHistoryWindow(MainViewModel viewModel, bool useTransparentWindow)
        : this()
    {
        DataContext = viewModel;
        if (useTransparentWindow)
        {
            TransparencyLevelHint = [WindowTransparencyLevel.Transparent];
            Background = Brushes.Transparent;
            TransparencyBackgroundFallback = new SolidColorBrush(Color.Parse("#07090D"));
        }
    }

    private void CloseWindow(object? sender, RoutedEventArgs args) => Close();
}
