from typing import Protocol

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.embeddings import Embedder
from app.pipeline import process_resume


class JobQueue(Protocol):
    async def enqueue_resume(self, resume_id: int) -> None: ...


class InlineQueue:
    """Runs the job before the request returns. Deterministic for tests and Redis-less local dev."""

    def __init__(self, sm: async_sessionmaker[AsyncSession], embedder: Embedder):
        self.sm, self.embedder = sm, embedder

    async def enqueue_resume(self, resume_id: int) -> None:
        await process_resume(self.sm, self.embedder, resume_id)


class ArqQueue:
    """Pushes to Redis; the separate worker process (app.worker) does the parsing and embedding."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._pool = None

    async def enqueue_resume(self, resume_id: int) -> None:
        if self._pool is None:
            self._pool = await create_pool(RedisSettings.from_dsn(self.redis_url))
        # _job_id makes the enqueue idempotent for a given resume revision
        await self._pool.enqueue_job("parse_resume", resume_id)


def build_queue(sm: async_sessionmaker[AsyncSession], embedder: Embedder) -> JobQueue:
    s = get_settings()
    return ArqQueue(s.redis_url) if s.queue == "arq" else InlineQueue(sm, embedder)
