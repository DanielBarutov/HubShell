using Avalonia;
using Avalonia.Headless;
using GameClub.Client.Avalonia;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class AvaloniaHostSmokeTests
{
    [Fact]
    public void MainWindowCanBeCreatedOnTheHeadlessPlatform()
    {
        AppBuilder.Configure<App>()
            .UseHeadless(new AvaloniaHeadlessPlatformOptions())
            .SetupWithoutStarting();

        var app = new App();
        app.Initialize();

        var window = new MainWindow();

        Assert.Equal("HubShell client — Linux developer host", window.Title);
    }
}
