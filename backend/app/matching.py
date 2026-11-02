"""Candidate generation (ANN) + reranking with the hybrid score + explanations."""

import re
from dataclasses import dataclass

import numpy as np
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings import Embedder, cosine_to_unit
from app.models import CandidateProfile, EmbeddingType, Job, Resume, ResumeChunk, ResumeStatus, User
from app.scoring import ScoreBreakdown, SkillMatch, combine, max_sim, skill_coverage, title_similarity

_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")


def is_postgres(session: AsyncSession) -> bool:
    return session.bind.dialect.name == "postgresql"


def _vec(v: np.ndarray):
    return sa.literal(v, type_=EmbeddingType())


# ---------------------------------------------------------------------------------------------
# Stage 1: candidate generation. On PostgreSQL this is an HNSW index scan (cosine ops);
# on SQLite (unit tests) it is an exact brute-force scan, so both paths return the same ids.
# ---------------------------------------------------------------------------------------------
async def candidate_resume_ids(session: AsyncSession, job_vec: np.ndarray, k: int) -> list[int]:
    if is_postgres(session):
        dist = ResumeChunk.embedding.op("<=>")(_vec(job_vec))
        q = (
            sa.select(ResumeChunk.resume_id)
            .join(Resume, Resume.id == ResumeChunk.resume_id)
            .where(Resume.status == ResumeStatus.DONE)
            .order_by(dist)
            .limit(k * 3)  # several chunks per resume: over-fetch, then dedupe
        )
        ids: list[int] = []
        for (rid,) in (await session.execute(q)).all():
            if rid not in ids:
                ids.append(rid)
        return ids[:k]
    rows = (
        await session.execute(
            sa.select(ResumeChunk.resume_id, ResumeChunk.embedding)
            .join(Resume, Resume.id == ResumeChunk.resume_id)
            .where(Resume.status == ResumeStatus.DONE)
        )
    ).all()
    best: dict[int, float] = {}
    for rid, emb in rows:
        s = float(emb @ job_vec)
        if s > best.get(rid, -2.0):
            best[rid] = s
    return [rid for rid, _ in sorted(best.items(), key=lambda kv: -kv[1])[:k]]


async def candidate_job_ids(session: AsyncSession, query_vec: np.ndarray, k: int) -> list[int]:
    base = sa.select(Job.id).where(Job.open.is_(True), Job.embedding.is_not(None))
    if is_postgres(session):
        q = base.order_by(Job.embedding.op("<=>")(_vec(query_vec))).limit(k)
        return [r for (r,) in (await session.execute(q)).all()]
    rows = (await session.execute(sa.select(Job.id, Job.embedding).where(Job.open.is_(True), Job.embedding.is_not(None)))).all()
    return [jid for jid, _ in sorted(rows, key=lambda r: -float(r[1] @ query_vec))[:k]]


# ---------------------------------------------------------------------------------------------
# Stage 2: exact hybrid score on the shortlisted pairs.
# ---------------------------------------------------------------------------------------------
def chunk_matrix(resume: Resume) -> np.ndarray:
    if not resume.chunks:
        return np.zeros((0, 384), dtype=np.float32)
    return np.stack([c.embedding for c in sorted(resume.chunks, key=lambda c: c.idx)])


def score_pair(job: Job, resume: Resume, profile: CandidateProfile, embedder: Embedder) -> tuple[ScoreBreakdown, SkillMatch]:
    cosine = max_sim(job.embedding, chunk_matrix(resume))
    skills = skill_coverage(profile.skills or [], job.must_have or [], job.nice_to_have or [])
    title = title_similarity(job.title_embedding, resume.title_embedding, embedder.calibration)
    bd = combine(
        cosine=cosine,
        calibration=embedder.calibration,
        skills=skills,
        candidate_years=profile.years_experience or 0.0,
        min_years=job.min_years or 0.0,
        title=title,
    )
    return bd, skills


@dataclass
class RankedCandidate:
    user: User
    profile: CandidateProfile
    resume: Resume
    breakdown: ScoreBreakdown
    skills: SkillMatch


@dataclass
class RankedJob:
    job: Job
    breakdown: ScoreBreakdown
    skills: SkillMatch


async def rank_candidates_for_job(
    session: AsyncSession, job: Job, embedder: Embedder, *, limit: int, ann_k: int, only_candidate_ids: set[int] | None = None
) -> list[RankedCandidate]:
    if only_candidate_ids is not None:  # ranking just the applicants: exact scoring, no ANN needed
        rows = (
            await session.execute(
                sa.select(Resume, CandidateProfile, User)
                .join(CandidateProfile, CandidateProfile.user_id == Resume.candidate_id)
                .join(User, User.id == Resume.candidate_id)
                .where(Resume.status == ResumeStatus.DONE, Resume.candidate_id.in_(only_candidate_ids))
            )
        ).all()
    else:
        ids = await candidate_resume_ids(session, job.embedding, ann_k)
        if not ids:
            return []
        rows = (
            await session.execute(
                sa.select(Resume, CandidateProfile, User)
                .join(CandidateProfile, CandidateProfile.user_id == Resume.candidate_id)
                .join(User, User.id == Resume.candidate_id)
                .where(Resume.id.in_(ids), CandidateProfile.searchable.is_(True))
            )
        ).all()
    ranked = []
    for resume, profile, user in rows:
        bd, sk = score_pair(job, resume, profile, embedder)
        ranked.append(RankedCandidate(user, profile, resume, bd, sk))
    ranked.sort(key=lambda r: (-r.breakdown.total, r.user.id))
    return ranked[:limit]


async def rank_jobs_for_candidate(
    session: AsyncSession, resume: Resume, profile: CandidateProfile, embedder: Embedder, *, limit: int, ann_k: int
) -> list[RankedJob]:
    mat = chunk_matrix(resume)
    if mat.shape[0] == 0:
        return []
    centroid = mat.mean(axis=0)
    centroid = centroid / max(float(np.linalg.norm(centroid)), 1e-9)
    ids = await candidate_job_ids(session, centroid.astype(np.float32), ann_k)
    if not ids:
        return []
    jobs = (await session.execute(sa.select(Job).where(Job.id.in_(ids)))).scalars().all()
    ranked = []
    for job in jobs:
        bd, sk = score_pair(job, resume, profile, embedder)
        ranked.append(RankedJob(job, bd, sk))
    ranked.sort(key=lambda r: (-r.breakdown.total, r.job.id))
    return ranked[:limit]


# ---------------------------------------------------------------------------------------------
# Explanation: which resume sentences best support each job requirement.
# ---------------------------------------------------------------------------------------------
def sentences(text: str, min_words: int = 4, limit: int = 60) -> list[str]:
    out = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip(" \t•-*")
        if len(s.split()) >= min_words:
            out.append(s)
    return out[:limit]


def explain_evidence(job: Job, resume: Resume, embedder: Embedder, top_n: int = 3) -> list[dict]:
    """For each job requirement sentence find the best-matching resume sentence; return the strongest pairs."""
    reqs = sentences(job.description, limit=12)
    resume_body = "\n".join(c.text for c in sorted(resume.chunks, key=lambda c: c.idx))
    res = sentences(resume_body)
    if not reqs or not res:
        return []
    rv, sv = embedder.embed(reqs), embedder.embed(res)
    sim = rv @ sv.T
    pairs = []
    for i, req in enumerate(reqs):
        j = int(np.argmax(sim[i]))
        pairs.append({"requirement": req, "evidence": res[j], "similarity": round(cosine_to_unit(float(sim[i, j]), embedder.calibration), 3)})
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs[:top_n]
