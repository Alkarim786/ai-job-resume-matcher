import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import require_role
from app.models import Application, Job, Resume, ResumeStatus, Role, User
from app.schemas import UserOut

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(Role.ADMIN))])


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)):
    async def count(stmt):
        return (await session.execute(stmt)).scalar_one()

    return {
        "users": {r.value: await count(sa.select(sa.func.count()).select_from(User).where(User.role == r)) for r in Role},
        "jobs": await count(sa.select(sa.func.count()).select_from(Job)),
        "applications": await count(sa.select(sa.func.count()).select_from(Application)),
        "resumes": {s.value: await count(sa.select(sa.func.count()).select_from(Resume).where(Resume.status == s)) for s in ResumeStatus},
    }


@router.get("/users", response_model=list[UserOut])
async def users(limit: int = 100, offset: int = 0, session: AsyncSession = Depends(get_session)):
    return (await session.execute(sa.select(User).order_by(User.id).limit(min(limit, 500)).offset(offset))).scalars().all()
