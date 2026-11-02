"""Pure scoring functions. final = 0.5*semantic + 0.3*skills + 0.1*experience + 0.1*title.

Everything here is deterministic and free of I/O so each component is unit-testable.
"""

from dataclasses import dataclass

import numpy as np

from app.embeddings import cosine_to_unit
from app.skills import canonical_skill

W_SEMANTIC, W_SKILLS, W_EXPERIENCE, W_TITLE = 0.5, 0.3, 0.1, 0.1
MUST_WEIGHT, NICE_WEIGHT = 2.0, 1.0


@dataclass
class SkillMatch:
    coverage: float
    matched_must: list[str]
    missing_must: list[str]
    matched_nice: list[str]
    missing_nice: list[str]


@dataclass
class ScoreBreakdown:
    total: float
    semantic: float
    skills: float
    experience: float
    title: float
    raw_cosine: float

    def as_dict(self) -> dict:
        return {k: round(v, 4) for k, v in self.__dict__.items()}


def normalize_skill_list(skills: list[str]) -> list[str]:
    out, seen = [], set()
    for s in skills:
        c = canonical_skill(s) or s.strip().lower()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def skill_coverage(candidate_skills: list[str], must: list[str], nice: list[str]) -> SkillMatch:
    """Weighted coverage: a matched must-have counts double a matched nice-to-have. No requirements -> neutral 0.5."""
    have = set(normalize_skill_list(candidate_skills))
    must_n, nice_n = normalize_skill_list(must), normalize_skill_list(nice)
    mm = [s for s in must_n if s in have]
    mn = [s for s in nice_n if s in have]
    denom = MUST_WEIGHT * len(must_n) + NICE_WEIGHT * len(nice_n)
    coverage = 0.5 if denom == 0 else (MUST_WEIGHT * len(mm) + NICE_WEIGHT * len(mn)) / denom
    return SkillMatch(
        coverage=coverage,
        matched_must=mm,
        missing_must=[s for s in must_n if s not in have],
        matched_nice=mn,
        missing_nice=[s for s in nice_n if s not in have],
    )


def experience_fit(candidate_years: float, min_years: float) -> float:
    """1.0 once the minimum is met; linear ramp below it. Seniority above the minimum is not rewarded here."""
    if min_years <= 0:
        return 1.0
    return float(min(1.0, max(0.0, candidate_years / min_years)))


def max_sim(query: np.ndarray, matrix: np.ndarray) -> float:
    """Max cosine of a unit query vector against unit rows (max-sim aggregation over resume chunks)."""
    if matrix.shape[0] == 0:
        return 0.0
    return float(np.max(matrix @ query))


def title_similarity(job_title_vec: np.ndarray | None, resume_title_vec: np.ndarray | None, calibration) -> float:
    if job_title_vec is None or resume_title_vec is None:
        return 0.0
    return cosine_to_unit(float(job_title_vec @ resume_title_vec), calibration)


def combine(
    *, cosine: float, calibration, skills: SkillMatch, candidate_years: float, min_years: float, title: float
) -> ScoreBreakdown:
    sem = cosine_to_unit(cosine, calibration)
    exp = experience_fit(candidate_years, min_years)
    total = W_SEMANTIC * sem + W_SKILLS * skills.coverage + W_EXPERIENCE * exp + W_TITLE * title
    return ScoreBreakdown(total=total, semantic=sem, skills=skills.coverage, experience=exp, title=title, raw_cosine=cosine)
