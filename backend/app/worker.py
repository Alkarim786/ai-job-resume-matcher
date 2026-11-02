"""arq worker: `arq app.worker.WorkerSettings`."""

from arq.connections import RedisSettings

from app.config import get_settings
from app.db import get_sessionmaker
from app.embeddings import get_embedder
from app.pipeline import process_resume


async def startup(ctx: dict) -> None:
    s = get_settings()
    ctx["sm"] = get_sessionmaker()
    ctx["embedder"] = get_embedder(s.embedder)
    ctx["embedder"].embed(["warm up"])  # load model weights before the first job


async def parse_resume(ctx: dict, resume_id: int) -> None:
    await process_resume(ctx["sm"], ctx["embedder"], resume_id)


class WorkerSettings:
    functions = [parse_resume]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    max_tries = 3
