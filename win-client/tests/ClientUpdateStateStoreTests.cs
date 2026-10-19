using System.Text.Json;
using GameClub.Client.Infrastructure.Updates;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class ClientUpdateStateStoreTests
{
    [Fact]
    public void BlockSurvivesRestartAndIsClearedOnlyByAnExplicitCompletedWrite()
    {
        var root = Path.Combine(Path.GetTempPath(), "hubshell-update-state-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var blocked = new ClientUpdateJournal(Guid.NewGuid(), Guid.NewGuid(), "v2.4.0",
                new string('a', 64), "prepared", true);
            var first = new ClientUpdateStateStore(root);
            Assert.Null(first.Read());
            first.Write(blocked);
            Assert.Equal(blocked, new ClientUpdateStateStore(root).Read());
            first.Write(blocked with { Stage = "completed", Blocked = false });
            Assert.False(new ClientUpdateStateStore(root).Read()!.Blocked);
            Assert.False(File.Exists(Path.Combine(root, ".client-update.json.new")));
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    [Fact]
    public void IncompleteStageCannotBeReadWithAnOpenGate()
    {
        var root = Path.Combine(Path.GetTempPath(), "hubshell-update-state-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            var store = new ClientUpdateStateStore(root);
            store.Write(new ClientUpdateJournal(Guid.NewGuid(), Guid.NewGuid(), "v2.4.0",
                new string('a', 64), "prepared", false));
            Assert.Throws<InvalidDataException>(() => store.Read());
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    [Theory]
    [InlineData("{bad-json", typeof(JsonException))]
    [InlineData("{}", typeof(InvalidDataException))]
    public void CorruptJournalIsNeverReadAsAnUnblockedDefault(string text, Type expected)
    {
        var root = Path.Combine(Path.GetTempPath(), "hubshell-update-state-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            File.WriteAllText(Path.Combine(root, ".client-update.json"), text);
            var error = Record.Exception(() => new ClientUpdateStateStore(root).Read());
            Assert.IsType(expected, error);
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
