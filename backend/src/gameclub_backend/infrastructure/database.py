import contextlib
import typing

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

EngineProvider = typing.Callable[[], AsyncEngine | None]


@contextlib.asynccontextmanager
async def open_session(provider: EngineProvider) -> typing.AsyncIterator[AsyncSession]:
    engine = provider()
    if engine is None:
        raise RuntimeError("PostgreSQL engine is not configured")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
