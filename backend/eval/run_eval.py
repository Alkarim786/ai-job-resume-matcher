"""Offline ranking evaluation on synthetic, generator-labelled resume/job pairs.

    python -m eval.run_eval --embedder minilm --resumes 30 --jobs 20 --seed 7

Pipeline under test (end to end, no shortcuts): synthetic resume -> real PDF -> pypdf text -> section/skill/years
parsing -> chunk embeddings -> score. Relevance labels come from the generating role family
(2 = same family, 1 = adjacent family, 0 = unrelated); they are NOT human judgements.
"""

import argparse
import json
import math
import random
import statistics
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from app.embeddings import get_embedder
from app.parsing import parse_resume_pdf
from app.pipeline import job_text
from app.scoring import combine, max_sim, skill_coverage, title_similarity
from app.seed.generate import REFERENCE_DATE, build_dataset, relevance, render_pdf


def dcg(rels):
    return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at(ranked_rels, all_rels, k):
    ideal = dcg(sorted(all_rels, reverse=True)[:k])
    return dcg(ranked_rels[:k]) / ideal if ideal > 0 else 0.0


def precision_at(ranked_rels, k, threshold=2):
    return sum(1 for r in ranked_rels[:k] if r >= threshold) / k


def reciprocal_rank(ranked_rels, threshold=2):
    for i, r in enumerate(ranked_rels):
        if r >= threshold:
            return 1 / (i + 1)
    return 0.0


def run(embedder_name: str, n_resumes: int, n_jobs: int, seed: int) -> dict:
    embedder = get_embedder(embedder_name)
    embedder.embed(["warm up"])
    resumes, jobs = build_dataset(n_resumes, n_jobs, seed=seed)

    t0 = time.perf_counter()
    pdfs = [render_pdf(r) for r in resumes]
    t_render = time.perf_counter() - t0

    parsed, parse_ms, embed_ms = [], [], []
    for pdf in pdfs:
        t = time.perf_counter()
        p = parse_resume_pdf(pdf, today=REFERENCE_DATE)
        parse_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        chunks = embedder.embed(p.chunks)
        title = embedder.embed(["; ".join(([p.headline] if p.headline else []) + p.titles[:3])])[0]
        embed_ms.append((time.perf_counter() - t) * 1000)
        parsed.append((p, chunks, title))

    job_vecs = embedder.embed([job_text(j.title, j.description, j.must_have, j.nice_to_have) for j in jobs])
    job_title_vecs = embedder.embed([j.title for j in jobs])

    variants = {"random": [], "skills_only": [], "semantic_only": [], "hybrid": []}
    rng = random.Random(0)
    score_ms = []
    for ji, job in enumerate(jobs):
        rels = [relevance(r.family, job.family) for r in resumes]
        t = time.perf_counter()
        sem, skl, hyb = [], [], []
        for p, chunks, title in parsed:
            cos = max_sim(job_vecs[ji], chunks)
            sk = skill_coverage(p.skills, job.must_have, job.nice_to_have)
            tsim = title_similarity(job_title_vecs[ji], title, embedder.calibration)
            bd = combine(cosine=cos, calibration=embedder.calibration, skills=sk, candidate_years=p.years_experience, min_years=job.min_years, title=tsim)
            sem.append(cos)
            skl.append(sk.coverage)
            hyb.append(bd.total)
        score_ms.append((time.perf_counter() - t) * 1000)
        scores = {"random": [rng.random() for _ in resumes], "skills_only": skl, "semantic_only": sem, "hybrid": hyb}
        for name, s in scores.items():
            order = sorted(range(len(resumes)), key=lambda i: (-s[i], i))
            ranked = [rels[i] for i in order]
            variants[name].append(
                {"ndcg10": ndcg_at(ranked, rels, 10), "p5": precision_at(ranked, 5), "mrr": reciprocal_rank(ranked)}
            )

    metrics = {name: {m: round(statistics.mean(x[m] for x in rows), 4) for m in ("ndcg10", "p5", "mrr")} for name, rows in variants.items()}

    tp = fp = fn = 0
    err = []
    for spec, (p, _, _) in zip(resumes, parsed):
        got, truth = set(p.skills), set(spec.skills)
        tp, fp, fn = tp + len(got & truth), fp + len(got - truth), fn + len(truth - got)
        err.append(abs(p.years_experience - spec.years))
    skill_p, skill_r = tp / (tp + fp), tp / (tp + fn)

    return {
        "embedder": embedder_name,
        "n_resumes": n_resumes,
        "n_jobs": n_jobs,
        "seed": seed,
        "ranking": metrics,
        "skill_extraction": {"precision": round(skill_p, 4), "recall": round(skill_r, 4), "f1": round(2 * skill_p * skill_r / (skill_p + skill_r), 4)},
        "years_mae": round(statistics.mean(err), 3),
        "latency_ms": {
            "pdf_parse_per_resume_mean": round(statistics.mean(parse_ms), 2),
            "embed_per_resume_mean": round(statistics.mean(embed_ms), 2),
            "score_all_resumes_per_job_mean": round(statistics.mean(score_ms), 3),
        },
        "pdf_render_s": round(t_render, 2),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default="hash")
    ap.add_argument("--resumes", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    result = run(a.embedder, a.resumes, a.jobs, a.seed)
    result["finished_at"] = datetime.now().isoformat(timespec="seconds")
    text = json.dumps(result, indent=2)
    print(text)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text)
