from enum import Enum

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.deps import candidate_only, current_user, get_embedder_dep, recruiter_only
from app.embeddings import Embedder
from app.matching import RankedCandidate, explain_evidence, rank_candidates_for_job
from app.models import Application, AppStatus, Job, Role, User
from app.pipeline import embed_job
from app.scoring import W_EXPERIENCE, W_SEMANTIC, W_SKILLS, W_TITLE
from app.schemas import (
    ApplicationOut,
    ApplicationStatusIn,
    EvidenceOut,
    ExplainOut,
    JobIn,
    JobOut,
    RankedCandidateOut,
    ScoreOut,
    SkillMatchOut,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class Scope(str, Enum):
    applicants = "applicants"
    all = "all"


async def _own_job(session: AsyncSession, job_id: int, user: User) -> Job:
    job = await session.get(Job, job_id)
    # 404 (not 403) for someone else's job: don't reveal that the id exists.
    if job is None or job.recruiter_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


def _ranked_out(r: RankedCandidate, blind: bool, app: Application | None) -> RankedCandidateOut:
    return RankedCandidateOut(
        candidate_id=None if blind else r.user.id,
        name="Candidate" if blind else r.user.full_name,
        headline=r.profile.headline,
        years_experience=r.profile.years_experience,
        score=ScoreOut(**r.breakdown.as_dict()),
        skills=SkillMatchOut(
            matched_must=r.skills.matched_must,
            missing_must=r.skills.missing_must,
            matched_nice=r.skills.matched_nice,
            missing_nice=r.skills.missing_nice,
        ),
        application_status=app.status if app else None,
        application_id=app.id if app else None,
    )


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobIn,
    user: User = Depends(recruiter_only),
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder_dep),
):
    job = Job(recruiter_id=user.id, **body.model_dump())
    await embed_job(job, embedder)
    session.add(job)
    await session.commit()
    return job


@router.get("", response_model=list[JobOut])
async def list_jobs(
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = sa.select(Job).where(Job.open.is_(True)).order_by(Job.id.desc()).limit(limit).offset(offset)
    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q}%"))
    return (await session.execute(stmt)).scalars().all()


@router.get("/mine", response_model=list[JobOut])
async def my_jobs(user: User = Depends(recruiter_only), session: AsyncSession = Depends(get_session)):
    rows = await session.execute(sa.select(Job).where(Job.recruiter_id == user.id).order_by(Job.id.desc()))
    return rows.scalars().all()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, _: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    job = await session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job


@router.put("/{job_id}", response_model=JobOut)
async def update_job(
    job_id: int,
    body: JobIn,
    user: User = Depends(recruiter_only),
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder_dep),
):
    job = await _own_job(session, job_id, user)
    for k, v in body.model_dump().items():
        setattr(job, k, v)
    await embed_job(job, embedder)
    await session.commit()
    return job


@router.post("/{job_id}/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def apply(job_id: int, user: User = Depends(candidate_only), session: AsyncSession = Depends(get_session)):
    job = await session.get(Job, job_id)
    if job is None or not job.open:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    application = Application(job_id=job_id, candidate_id=user.id)
    session.add(application)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "already applied")
    return application


@router.get("/{job_id}/candidates", response_model=list[RankedCandidateOut])
async def ranked_candidates(
    job_id: int,
    scope: Scope = Scope.all,
    limit: int = Query(20, ge=1, le=100),
    blind: bool = Query(False, description="hide names and ids so the ranking can be reviewed without identity"),
    user: User = Depends(recruiter_only),
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder_dep),
):
    job = await _own_job(session, job_id, user)
    apps = {a.candidate_id: a for a in (await session.execute(sa.select(Application).where(Application.job_id == job_id))).scalars()}
    only = set(apps) if scope == Scope.applicants else None
    if only is not None and not only:
        return []
    ranked = await rank_candidates_for_job(
        session, job, embedder, limit=limit, ann_k=get_settings().ann_candidates, only_candidate_ids=only
    )
    return [_ranked_out(r, blind, apps.get(r.user.id)) for r in ranked]


@router.get("/{job_id}/candidates/{candidate_id}/explain", response_model=ExplainOut)
async def explain(
    job_id: int,
    candidate_id: int,
    user: User = Depends(recruiter_only),
    session: AsyncSession = Depends(get_session),
    embedder: Embedder = Depends(get_embedder_dep),
):
    job = await _own_job(session, job_id, user)
    ranked = await rank_candidates_for_job(session, job, embedder, limit=1, ann_k=1, only_candidate_ids={candidate_id})
    if not ranked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "candidate has no processed resume")
    r = ranked[0]
    app = (
        await session.execute(sa.select(Application).where(Application.job_id == job_id, Application.candidate_id == candidate_id))
    ).scalar_one_or_none()
    return ExplainOut(
        candidate=_ranked_out(r, False, app),
        evidence=[EvidenceOut(**e) for e in explain_evidence(job, r.resume, embedder)],
        weights={"semantic": W_SEMANTIC, "skills": W_SKILLS, "experience": W_EXPERIENCE, "title": W_TITLE},
    )


@router.get("/{job_id}/applications", response_model=list[ApplicationOut])
async def applications(job_id: int, user: User = Depends(recruiter_only), session: AsyncSession = Depends(get_session)):
    await _own_job(session, job_id, user)
    rows = await session.execute(sa.select(Application).where(Application.job_id == job_id).order_by(Application.id))
    return rows.scalars().all()


@router.patch("/{job_id}/applications/{application_id}", response_model=ApplicationOut)
async def set_application_status(
    job_id: int,
    application_id: int,
    body: ApplicationStatusIn,
    user: User = Depends(recruiter_only),
    session: AsyncSession = Depends(get_session),
):
    await _own_job(session, job_id, user)
    application = await session.get(Application, application_id)
    if application is None or application.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    application.status = body.status
    await session.commit()
    return application
