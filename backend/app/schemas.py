from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AppStatus, ResumeStatus, Role
from app.scoring import normalize_skill_list


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: Role

    @field_validator("role")
    @classmethod
    def no_self_service_admin(cls, v: Role) -> Role:
        if v == Role.ADMIN:
            raise ValueError("admin accounts cannot be self-registered")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    email: EmailStr
    full_name: str
    role: Role


class ProfileIn(BaseModel):
    headline: str | None = Field(default=None, max_length=255)
    skills: list[str] | None = None
    years_experience: float | None = Field(default=None, ge=0, le=60)
    searchable: bool | None = None

    @field_validator("skills")
    @classmethod
    def _norm(cls, v):
        return None if v is None else normalize_skill_list(v)[:60]


class ProfileOut(ORM):
    headline: str
    skills: list[str]
    years_experience: float
    searchable: bool


class ResumeOut(ORM):
    id: int
    filename: str
    status: ResumeStatus
    error: str | None
    parsed: dict
    created_at: datetime


class JobIn(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    company: str = Field(default="", max_length=255)
    description: str = Field(min_length=20, max_length=20000)
    must_have: list[str] = Field(default_factory=list, max_length=30)
    nice_to_have: list[str] = Field(default_factory=list, max_length=30)
    min_years: float = Field(default=0, ge=0, le=40)

    @field_validator("must_have", "nice_to_have")
    @classmethod
    def _norm(cls, v):
        return normalize_skill_list(v)


class JobOut(ORM):
    id: int
    recruiter_id: int
    title: str
    company: str
    description: str
    must_have: list[str]
    nice_to_have: list[str]
    min_years: float
    open: bool
    created_at: datetime


class ScoreOut(BaseModel):
    total: float
    semantic: float
    skills: float
    experience: float
    title: float
    raw_cosine: float


class SkillMatchOut(BaseModel):
    matched_must: list[str]
    missing_must: list[str]
    matched_nice: list[str]
    missing_nice: list[str]


class RecommendedJob(BaseModel):
    job: JobOut
    score: ScoreOut
    skills: SkillMatchOut


class RankedCandidateOut(BaseModel):
    candidate_id: int | None
    name: str
    headline: str
    years_experience: float
    score: ScoreOut
    skills: SkillMatchOut
    application_status: AppStatus | None = None
    application_id: int | None = None


class EvidenceOut(BaseModel):
    requirement: str
    evidence: str
    similarity: float


class ExplainOut(BaseModel):
    candidate: RankedCandidateOut
    evidence: list[EvidenceOut]
    weights: dict[str, float]


class ApplicationStatusIn(BaseModel):
    status: AppStatus


class ApplicationOut(ORM):
    id: int
    job_id: int
    candidate_id: int
    status: AppStatus
    created_at: datetime
