import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import current_user
from app.models import CandidateProfile, Role, User
from app.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Verified against a throwaway hash when the email is unknown, so login timing doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("not-a-real-password")


def _tokens(user_id: int) -> TokenOut:
    return TokenOut(access_token=create_access_token(user_id), refresh_token=create_refresh_token(user_id))


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)):
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name, role=body.role)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    if body.role == Role.CANDIDATE:
        session.add(CandidateProfile(user_id=user.id, headline="", skills=[], years_experience=0.0))
    await session.commit()
    return _tokens(user.id)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    return _tokens(user.id)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    try:
        uid = decode_token(body.refresh_token, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired refresh token")
    if await session.get(User, uid) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return _tokens(uid)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)):
    return user
