using Avalonia.Controls;
using GameClub.Client.Avalonia.Development;

namespace GameClub.Client.Avalonia;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContext = new DeveloperHostViewModel();
    }
}
