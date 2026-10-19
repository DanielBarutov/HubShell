using System.Text.Json;
using System.Text.Json.Nodes;
using GameClub.Client.Infrastructure.Updates;
using Xunit;

namespace GameClub.Client.Tests;

public sealed class UpdateIpcProtocolTests
{
    [Theory]
    [InlineData("activeSession")]
    [InlineData("sessionId")]
    [InlineData("lastSequence")]
    [InlineData("ready")]
    [InlineData("protocolVersion")]
    public void MissingReadinessFieldsAreNotInterpretedAsAnIdleGui(string missing)
    {
        var valid = new UpdateIpcStatus("pc-1", "installation", "v2.4.0", false, 0, true, true);
        var bytes = JsonSerializer.SerializeToUtf8Bytes(valid, UpdateIpcProtocol.Json);
        Assert.Equal(valid, JsonSerializer.Deserialize<UpdateIpcStatus>(bytes, UpdateIpcProtocol.Json));
        var message = JsonNode.Parse(bytes)!.AsObject();
        message.Remove(missing);
        Assert.Throws<JsonException>(() =>
            JsonSerializer.Deserialize<UpdateIpcStatus>(message.ToJsonString(), UpdateIpcProtocol.Json));
    }
}
