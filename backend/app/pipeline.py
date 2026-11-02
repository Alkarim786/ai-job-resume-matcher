"""Background work: parse a stored resume PDF, extract fields, embed chunks. Also job embedding."""

import logging
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.embeddings import Embedder
from app.models import CandidateProfile, Job, Resume, ResumeChunk, ResumeStatus
from app.parsing import ResumeParseError, parse_resume_pdf

log = logging.getLogger(__name__)


def job_text(title: str, description: str, must: list[str], nice: list[str]) -> str:
    return f"{title}. {description} Required skills: {', '.join(must)}. Nice to have: {', '.join(nice)}."


async def embed_job(job: Job, embedder: Embedder) -> None:
    vecs = embedder.embed([job_text(job.title, job.description, job.must_have or [], job.nice_to_have or []), job.title])
    job.embedding, job.title_embedding = vecs[0], vecs[1]


async def process_resume(sm: async_sessionmaker[AsyncSession], embedder: Embedder, resume_id: int) -> None:
    """Idempotent: re-running replaces the chunks. Failures are recorded on the row, never raised to the queue."""
    async with sm() as session:
        resume = (await session.execute(sa.select(Resume).where(Resume.id == resume_id))).scalar_one_or_none()
        if resume is None:
            return
        resume.status, resume.error = ResumeStatus.PROCESSING, None
        await session.commit()
        try:
            parsed = parse_resume_pdf(Path(resume.path).read_bytes())
            chunk_vecs = embedder.embed(parsed.chunks)
            title_text = "; ".join(([parsed.headline] if parsed.headline else []) + parsed.titles[:3]) or parsed.headline or "candidate"
            title_vec = embedder.embed([title_text])[0]
            await session.execute(sa.delete(ResumeChunk).where(ResumeChunk.resume_id == resume_id))
            for i, (text, vec) in enumerate(zip(parsed.chunks, chunk_vecs)):
                session.add(ResumeChunk(resume_id=resume_id, idx=i, text=text, embedding=vec))
            resume.text, resume.parsed, resume.title_embedding = parsed.text, parsed.as_json(), title_vec
            profile = await session.get(CandidateProfile, resume.candidate_id)
            if profile is not None:
                # Parsed values seed the profile; the candidate can edit them afterwards.
                profile.skills = parsed.skills
                profile.years_experience = parsed.years_experience
                if not profile.headline:
                    profile.headline = parsed.headline
            resume.status = ResumeStatus.DONE
        except (ResumeParseError, OSError) as exc:
            await session.rollback()
            resume = await session.get(Resume, resume_id)
            resume.status, resume.error = ResumeStatus.FAILED, str(exc)[:500]
        except Exception as exc:  # unexpected: record, log, don't kill the worker
            log.exception("resume %s failed", resume_id)
            await session.rollback()
            resume = await session.get(Resume, resume_id)
            resume.status, resume.error = ResumeStatus.FAILED, f"internal error: {type(exc).__name__}"
        await session.commit()
