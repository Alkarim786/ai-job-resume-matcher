import numpy as np
import pytest

from app.embeddings import HashEmbedder, cosine_to_unit
from app.scoring import (
    W_EXPERIENCE,
    W_SEMANTIC,
    W_SKILLS,
    W_TITLE,
    combine,
    experience_fit,
    max_sim,
    normalize_skill_list,
    skill_coverage,
)


def test_weights_sum_to_one():
    assert W_SEMANTIC + W_SKILLS + W_EXPERIENCE + W_TITLE == pytest.approx(1.0)


def test_skill_coverage_weights_must_haves_double():
    # must: a, b (weight 2 each) ; nice: c (weight 1). Have a and c -> (2 + 1) / 5
    m = skill_coverage(["python", "docker"], must=["python", "kafka"], nice=["docker"])
    assert m.coverage == pytest.approx((2 + 1) / (2 * 2 + 1))
    assert m.matched_must == ["python"] and m.missing_must == ["kafka"]
    assert m.matched_nice == ["docker"] and m.missing_nice == []


def test_skill_coverage_uses_aliases_and_case():
    m = skill_coverage(["Postgres", "K8s"], must=["PostgreSQL", "kubernetes"], nice=[])
    assert m.coverage == 1.0
    assert m.missing_must == []


def test_skill_coverage_no_requirements_is_neutral():
    assert skill_coverage(["python"], [], []).coverage == 0.5


def test_missing_must_have_hurts_more_than_missing_nice():
    miss_must = skill_coverage(["b"], must=["a", "b"], nice=["c", "d"]).coverage
    miss_nice = skill_coverage(["a", "b", "c"], must=["a", "b"], nice=["c", "d"]).coverage
    assert miss_nice > miss_must


@pytest.mark.parametrize("have,need,expected", [(5, 3, 1.0), (3, 3, 1.0), (1.5, 3, 0.5), (0, 3, 0.0), (2, 0, 1.0)])
def test_experience_fit(have, need, expected):
    assert experience_fit(have, need) == pytest.approx(expected)


def test_max_sim_takes_best_chunk():
    q = np.array([1.0, 0.0], dtype=np.float32)
    chunks = np.array([[0.0, 1.0], [0.8, 0.6], [1.0, 0.0]], dtype=np.float32)
    assert max_sim(q, chunks) == pytest.approx(1.0)
    assert max_sim(q, np.zeros((0, 2), dtype=np.float32)) == 0.0


def test_cosine_to_unit_clamps():
    assert cosine_to_unit(-0.3, (0.1, 0.6)) == 0.0
    assert cosine_to_unit(0.9, (0.1, 0.6)) == 1.0
    assert cosine_to_unit(0.35, (0.1, 0.6)) == pytest.approx(0.5)


def test_combine_perfect_and_zero():
    perfect = skill_coverage(["a"], ["a"], [])
    bd = combine(cosine=1.0, calibration=(0.0, 0.5), skills=perfect, candidate_years=5, min_years=3, title=1.0)
    assert bd.total == pytest.approx(1.0)
    none = skill_coverage([], ["a"], [])
    bd0 = combine(cosine=0.0, calibration=(0.0, 0.5), skills=none, candidate_years=0, min_years=3, title=0.0)
    assert bd0.total == pytest.approx(0.0)


def test_normalize_skill_list_dedupes():
    assert normalize_skill_list(["Postgres", "postgresql", "  K8s "]) == ["postgresql", "kubernetes"]


def test_hash_embedder_is_unit_norm_and_deterministic():
    e = HashEmbedder()
    v = e.embed(["python fastapi postgres", "python fastapi postgres", "completely different words here"])
    assert v.shape == (3, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
    assert np.allclose(v[0], v[1])
    assert float(v[0] @ v[1]) > float(v[0] @ v[2])
