import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.embeddings import Embedder
from app.models import Role, User
from app.queueing import JobQueue
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_embedder_dep(request: Request) -> Embedder:
    return request.app.state.embedder


def get_queue(request: Request) -> JobQueue:
    return request.app.state.queue


async def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), session: AsyncSession = Depends(get_session)
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    try:
        uid = decode_token(creds.credentials, "access")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return user


def require_role(*roles: Role):
    async def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {' or '.join(r.value for r in roles)}")
        return user

    return dep


candidate_only = require_role(Role.CANDIDATE)
recruiter_only = require_role(Role.RECRUITER)
