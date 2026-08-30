import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from dramatiq.middleware import AsyncIO

from gameclub_backend.config import Settings


def create_broker(settings: Settings) -> dramatiq.Broker:
    broker: dramatiq.Broker
    if settings.redis_url:
        broker = RedisBroker(url=settings.redis_url)
    else:
        broker = StubBroker()
    broker.add_middleware(AsyncIO())
    return broker


def configure_broker(settings: Settings) -> dramatiq.Broker:
    broker = create_broker(settings)
    dramatiq.set_broker(broker)
    return broker
