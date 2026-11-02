"""Seed demo data: 1 admin, 3 recruiters, 30 candidates (real PDFs, parsed by the real pipeline), 20 jobs, a few applications.

    python -m app.seed.seed            # idempotent: does nothing if users already exist
"""

import asyncio
import random
from pathlib import Path

import sqlalchemy as sa

from app.config import get_settings
from app.db import get_sessionmaker
from app.embeddings import get_embedder
from app.models import Application, CandidateProfile, Job, Resume, Role, User
from app.pipeline import embed_job, process_resume
from app.security import hash_password
from app.seed.generate import build_dataset, render_pdf

DEMO_PASSWORD = "password123"  # demo accounts only


async def seed() -> None:
    settings = get_settings()
    sm = get_sessionmaker()
    embedder = get_embedder(settings.embedder)
    async with sm() as session:
        if (await session.execute(sa.select(sa.func.count()).select_from(User))).scalar_one() > 0:
            print("database already has users; skipping seed")
            return
        pw = hash_password(DEMO_PASSWORD)
        admin = User(email="admin@example.com", password_hash=pw, full_name="Admin", role=Role.ADMIN)
        recruiters = [User(email=f"recruiter{i}@example.com", password_hash=pw, full_name=f"Recruiter {i}", role=Role.RECRUITER) for i in (1, 2, 3)]
        session.add_all([admin, *recruiters])
        await session.flush()

        resumes, jobs = build_dataset(30, 20, seed=7)
        for i, spec in enumerate(jobs):
            job = Job(
                recruiter_id=recruiters[i % 3].id,
                title=spec.title,
                company=spec.company,
                description=spec.description,
                must_have=spec.must_have,
                nice_to_have=spec.nice_to_have,
                min_years=spec.min_years,
            )
            await embed_job(job, embedder)
            session.add(job)

        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        candidates = []
        for i, spec in enumerate(resumes):
            user = User(email=f"candidate{i + 1}@example.com", password_hash=pw, full_name=spec.name, role=Role.CANDIDATE)
            session.add(user)
            await session.flush()
            session.add(CandidateProfile(user_id=user.id, headline="", skills=[], years_experience=0.0))
            path = upload_dir / f"seed-candidate-{i + 1}.pdf"
            path.write_bytes(render_pdf(spec))
            r = Resume(candidate_id=user.id, filename=f"{spec.name.replace(' ', '_')}_resume.pdf", path=str(path))
            session.add(r)
            candidates.append((user, r))
        await session.commit()
        job_ids = [j for (j,) in (await session.execute(sa.select(Job.id))).all()]
        rng = random.Random(1)
        for user, _ in candidates:
            for jid in rng.sample(job_ids, 2):
                session.add(Application(job_id=jid, candidate_id=user.id))
        await session.commit()
        resume_ids = [r.id for _, r in candidates]
    for rid in resume_ids:
        await process_resume(sm, embedder, rid)
    print(f"seeded: 1 admin, 3 recruiters, {len(resume_ids)} candidates, {len(job_ids)} jobs (password for all: {DEMO_PASSWORD})")


if __name__ == "__main__":
    asyncio.run(seed())
