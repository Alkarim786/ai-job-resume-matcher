from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None, **kw):
    url = url or get_settings().database_url
    engine = create_async_engine(url, **kw)
    # No asyncpg codec registration: pgvector's SQLAlchemy type already sends/reads the text form,
    # and it must work on the very first (pre-extension) migration connection.
    return engine


_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(make_engine(), expire_on_commit=False)
    return _sessionmaker


def set_sessionmaker(sm: async_sessionmaker[AsyncSession] | None) -> None:
    global _sessionmaker
    _sessionmaker = sm


async def get_session():
    async with get_sessionmaker()() as session:
        yield session
