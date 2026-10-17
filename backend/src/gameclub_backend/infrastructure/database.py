import contextlib
import contextvars
import typing

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

EngineProvider = typing.Callable[[], AsyncEngine | None]


@contextlib.asynccontextmanager
async def open_session(provider: EngineProvider) -> typing.AsyncIterator[AsyncSession]:
    ambient = _transaction.get()
    if ambient is not None and ambient[0] is provider():
        yield ambient[1]
        return
    engine = provider()
    if engine is None:
        raise RuntimeError("PostgreSQL engine is not configured")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


_transaction: contextvars.ContextVar[tuple[AsyncEngine, AsyncSession] | None] = (
    contextvars.ContextVar("gameclub_transaction", default=None)
)


@contextlib.asynccontextmanager
async def begin_session(session: AsyncSession) -> typing.AsyncIterator[None]:
    """Join an application transaction without committing a repository operation."""
    ambient = _transaction.get()
    if ambient is not None and ambient[1] is session:
        yield
        await session.flush()
    else:
        async with session.begin():
            yield


async def commit_session(session: AsyncSession) -> None:
    ambient = _transaction.get()
    if ambient is not None and ambient[1] is session:
        await session.flush()
    else:
        await session.commit()


@contextlib.asynccontextmanager
async def application_transaction(provider: EngineProvider) -> typing.AsyncIterator[AsyncSession]:
    """Give participating public repositories one PostgreSQL commit boundary."""
    engine = provider()
    if engine is None:
        raise RuntimeError("PostgreSQL engine is not configured")
    ambient = _transaction.get()
    if ambient is not None and ambient[0] is engine:
        yield ambient[1]
        return
    async with open_session(provider) as session:
        async with session.begin():
            token = _transaction.set((engine, session))
            try:
                yield session
            finally:
                _transaction.reset(token)
