from gameclub.v2 import events_pb2
from gameclub_backend.modules.eventing_v2.presentation.client_facts_http import (
    V2ClientFactIngress,
)


async def test_v2_client_fact_ingress_publishes_unchanged_protobuf_and_partition_key() -> None:
    """Ingress передаёт в Kafka исходный envelope и стабильный ключ сессии."""

    broker = RecordingBroker()
    ingress = V2ClientFactIngress(broker)  # type: ignore[arg-type]
    envelope = events_pb2.EventEnvelope(
        event_id="event-1",
        operation_id="operation-1",
        client_id="client-1",
        session_id="session-1",
        device_id="device-1",
        producer_id="workstation:device-1",
        payload_json='{"amount_cents":60}',
    )

    await ingress.publish(envelope)

    assert broker.started is True
    assert broker.payload == envelope.SerializeToString()
    assert broker.topic == "v2.client-events"
    assert broker.key == b"client-1:session-1"
    await ingress.close()
    assert broker.stopped is True


class RecordingBroker:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.payload: bytes | None = None
        self.topic: str | None = None
        self.key: bytes | None = None

    async def start(self) -> None:
        self.started = True

    async def publish(
        self,
        payload: bytes,
        *,
        topic: str,
        key: bytes,
        correlation_id: str,
        headers: dict[str, str],
    ) -> None:
        del correlation_id, headers
        self.payload = payload
        self.topic = topic
        self.key = key

    async def stop(self) -> None:
        self.stopped = True
