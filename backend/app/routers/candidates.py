import uuid
from pathlib import Path

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import candidate_only, get_embedder_dep, get_queue
from app.embeddings import Embedder
from app.matching import rank_jobs_for_candidate
from app.models import Application, CandidateProfile, Resume, ResumeChunk, ResumeStatus, User
from app.queueing import JobQueue
from app.schemas import ApplicationOut, ProfileIn, ProfileOut, RecommendedJob, ResumeOut, ScoreOut, SkillMatchOut, JobOut

router = APIRouter(prefix="/candidates/me", tags=["candidate"])


async def _profile(session: AsyncSession, user: User) -> CandidateProfile:
    profile = await session.get(CandidateProfile, user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no candidate profile")
    return profile


@router.post("/resume", response_model=ResumeOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(candidate_only),
    session: AsyncSession = Depends(get_session),
    queue: JobQueue = Depends(get_queue),
):
    """Accepts a PDF, stores it, and enqueues parsing. Poll GET /candidates/me/resume for status."""
    settings = get_settings()
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "file too large (max 5 MB)")
    if not data.startswith(b"%PDF-"):  # trust the bytes, not the client-supplied content type
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "only PDF files are accepted")
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / f"{uuid.uuid4().hex}.pdf"  # never use the client filename on disk
    path.write_bytes(data)

    resume = (await session.execute(sa.select(Resume).where(Resume.candidate_id == user.id))).scalar_one_or_none()
    if resume is None:
        resume = Resume(candidate_id=user.id, filename=(file.filename or "resume.pdf")[:255], path=str(path))
        session.add(resume)
    else:
        old = Path(resume.path)
        await session.execute(sa.delete(ResumeChunk).where(ResumeChunk.resume_id == resume.id))
        resume.filename, resume.path = (file.filename or "resume.pdf")[:255], str(path)
        resume.status, resume.error, resume.parsed, resume.text = ResumeStatus.PENDING, None, {}, ""
        old.unlink(missing_ok=True)
    await session.commit()
    await queue.enqueue_resume(resume.id)
    await session.refresh(resume)
    return resume


@router.get("/resume", response_model=ResumeOut)
async def get_resume(user: User = Depends(candidate_only), session: AsyncSession = Depends(get_session)):
    resume = (await session.execute(sa.select(Resume).where(Resume.candidate_id == user.id))).scalar_one_or_none()
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no resume uploaded")
    return resume


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user: User = Depends(candidate_only), session: AsyncSession = Depends(get_session)):
    return await _profile(session, user)


@router.put("/profile", response_model=ProfileOut)
async def update_profile(body: ProfileIn, user: User = Depends(candidate_only), session: AsyncSession = Depends(get_session)):
    profile = await _profile(session, user)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    await session.commit()
    return profile


@router.get("/recommendations", response_model=list[RecommendedJob])
async def recommendations(
    limit: int = 10,
    user: User = Depends(candidate_only),
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder_dep),
):
    profile = await _profile(session, user)
    resume = (await session.execute(sa.select(Resume).where(Resume.candidate_id == user.id))).scalar_one_or_none()
    if resume is None or resume.status != ResumeStatus.DONE:
        raise HTTPException(status.HTTP_409_CONFLICT, "resume not processed yet")
    ranked = await rank_jobs_for_candidate(
        session, resume, profile, embedder, limit=max(1, min(limit, 50)), ann_k=get_settings().ann_candidates
    )
    return [
        RecommendedJob(
            job=JobOut.model_validate(r.job),
            score=ScoreOut(**r.breakdown.as_dict()),
            skills=SkillMatchOut(
                matched_must=r.skills.matched_must,
                missing_must=r.skills.missing_must,
                matched_nice=r.skills.matched_nice,
                missing_nice=r.skills.missing_nice,
            ),
        )
        for r in ranked
    ]


@router.get("/applications", response_model=list[ApplicationOut])
async def my_applications(user: User = Depends(candidate_only), session: AsyncSession = Depends(get_session)):
    rows = await session.execute(sa.select(Application).where(Application.candidate_id == user.id).order_by(Application.id.desc()))
    return rows.scalars().all()
