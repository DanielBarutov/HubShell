using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Data;

namespace GameClub.Client.Presentation;

/// <summary>
/// WinUI-only view adapter for the portable boolean state in <see cref="MainViewModel"/>.
/// Avalonia binds the same state directly through its IsVisible property.
/// </summary>
public sealed class WinUiBooleanToVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, string language) =>
        value is true ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, string language) =>
        value is Visibility.Visible;
}
