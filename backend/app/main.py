from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_sessionmaker
from app.embeddings import get_embedder
from app.queueing import build_queue
from app.routers import admin, auth, candidates, jobs


def create_app(embedder=None, queue=None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.embedder = embedder or get_embedder(settings.embedder)
        app.state.queue = queue or build_queue(get_sessionmaker(), app.state.embedder)
        yield

    app = FastAPI(title="AI Job & Resume Matcher", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (auth.router, candidates.router, jobs.router, admin.router):
        app.include_router(r)

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok", "embedder": app.state.embedder.name}

    return app


app = create_app()
