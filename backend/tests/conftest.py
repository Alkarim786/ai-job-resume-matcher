"""Test fixtures.

By default the suite runs on in-memory SQLite (vectors stored as JSON, exact scan instead of HNSW).
Set TEST_DATABASE_URL=postgresql+asyncpg://... (after `alembic upgrade head`) to run the SAME tests against
PostgreSQL + pgvector, which exercises the real vector column type and the HNSW ANN query path.
Set TEST_EMBEDDER=minilm to use the real sentence-transformers model instead of the hash embedder.
"""

import os
import random

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from app import models  # noqa: F401
from app.config import get_settings
from app.db import Base, make_engine, set_sessionmaker
from app.embeddings import get_embedder
from app.main import create_app
from app.models import Role, User
from app.queueing import InlineQueue
from app.security import hash_password
from app.seed.generate import FAMILIES, JobSpec, make_job, make_resume, render_pdf

PG_URL = os.getenv("TEST_DATABASE_URL")


@pytest_asyncio.fixture
async def sm():
    if PG_URL:
        engine = make_engine(PG_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            names = ", ".join(t.name for t in Base.metadata.sorted_tables)
            await conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    else:
        engine = make_engine("sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    set_sessionmaker(maker)
    yield maker
    set_sessionmaker(None)
    await engine.dispose()


@pytest.fixture
def embedder():
    return get_embedder(os.getenv("TEST_EMBEDDER", "hash"))


@pytest_asyncio.fixture
async def client(sm, embedder, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))
    app = create_app(embedder=embedder)
    app.state.embedder = embedder
    app.state.queue = InlineQueue(sm, embedder)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def register(client: AsyncClient, email: str, role: str, name: str = "Test User") -> dict:
    r = await client.post("/auth/register", json={"email": email, "password": "password123", "full_name": name, "role": role})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client, sm):
    async with sm() as s:
        s.add(User(email="admin@example.com", password_hash=hash_password("password123"), full_name="Admin", role=Role.ADMIN))
        await s.commit()
    r = await client.post("/auth/login", json={"email": "admin@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def resume_pdf(family: str, seed: int = 1, stuffed: bool = False):
    spec = make_resume(random.Random(seed), family, seed, stuffed)
    return spec, render_pdf(spec)


def job_payload(family: str, seed: int = 1) -> tuple[JobSpec, dict]:
    spec = make_job(random.Random(seed), family)
    payload = {
        "title": spec.title,
        "company": spec.company,
        "description": spec.description,
        "must_have": spec.must_have,
        "nice_to_have": spec.nice_to_have,
        "min_years": spec.min_years,
    }
    return spec, payload


async def upload(client: AsyncClient, headers: dict, pdf: bytes, name: str = "resume.pdf"):
    return await client.post("/candidates/me/resume", headers=headers, files={"file": (name, pdf, "application/pdf")})


__all__ = ["FAMILIES"]
