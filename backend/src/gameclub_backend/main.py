import asyncio
import signal

from gameclub_backend.config import get_settings
from gameclub_backend.infrastructure.resources import create_resources
from gameclub_backend.presentation.grpc.server import create_server


async def serve() -> None:
    settings = get_settings()
    resources = create_resources(settings)
    server = create_server(settings, resources)
    await server.start()
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    handled_signals: list[signal.Signals] = []
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, shutdown_event.set)
        except (NotImplementedError, RuntimeError):
            break
        handled_signals.append(signal_name)
    try:
        if handled_signals:
            await shutdown_event.wait()
        else:
            await server.wait_for_termination()
    finally:
        for signal_name in handled_signals:
            loop.remove_signal_handler(signal_name)
        await server.stop(grace=5)
        await resources.close()


if __name__ == "__main__":
    asyncio.run(serve())
