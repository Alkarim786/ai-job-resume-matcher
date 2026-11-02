# Notes for Karim: Project 23, AI Job & Resume Matcher

## Resume bullets (numbers are measured; data is synthetic, say so if asked)
- Built an explainable job/resume matching platform (FastAPI, PostgreSQL + pgvector HNSW, Redis/arq workers, Next.js) combining chunked MiniLM embeddings with a weighted skills/experience/title model; hybrid ranking reached NDCG@10 0.897 vs 0.792 semantic-only and 0.851 skills-only on a labelled synthetic set (0.994 vs 0.921 / 0.911 on 300 resumes).
- Designed an async PDF-parsing pipeline (section detection, 104-skill taxonomy with ambiguity handling, overlap-aware experience calculation) with skill extraction recall 1.00 / precision 0.94 and 0.1-year experience error; resumes become searchable ~0.7 s p50 after upload.
- Shipped two-stage retrieval (HNSW shortlist + exact rerank) serving ranked-candidate queries at 63 ms p50 / 78 ms p95, with role/ownership-enforced APIs, blind-review mode, and 72 automated tests run on both SQLite and real Postgres in CI.

## Likely interview questions
1. **Why a hybrid score instead of pure embeddings?** Embeddings capture paraphrase but blur hard constraints (a missing must-have skill). Skills are auditable. In my eval, hybrid beat both alone. Mention the weights (0.5/0.3/0.1/0.1) are a priori, not tuned.
2. **How does HNSW work and what are its trade-offs?** Layered proximity graph; approximate; tune `m`, `ef_construction`, `ef_search`; recall vs latency; build cost and memory. Post-filtering issue (searchable flag applied after ANN).
3. **Why chunk + max-sim?** A resume covers many topics; one mean vector dilutes. Max over chunks finds best evidence. Weakness: one lucky chunk can inflate a score.
4. **How do you make matching explainable and fair?** Score breakdown, matched/missing skills, best-evidence sentences; blind mode. Be honest that blind mode doesn't remove proxy bias (university, location) and I have no fairness metrics yet.
5. **Why queue the parsing? What if the worker fails?** PDF parsing + embedding is slow and CPU-bound; 202 + polling. Job is idempotent (replaces chunks), failures stored on the resume row, arq retries.
Also likely: JWT access vs refresh design, why 404 not 403, how you'd evaluate on real data.

## Understand before interviews
- `matching.py`: stage 1 (`candidate_resume_ids`) over-fetches `k*3` chunks because several chunks belong to one resume, dedupes, then stage 2 `score_pair` computes exact max-sim + skills + experience + title. SQLite path is brute force and returns the same ids.
- `models.EmbeddingType`: a `TypeDecorator` choosing `Vector(384)` on Postgres and JSON elsewhere. I do NOT register the asyncpg vector codec: pgvector's SQLAlchemy type already binds text form, and registering it caused a "could not convert string to float" error.
- `parsing.py`: sections come from heading aliases; wrapped bullets are re-joined (`_unwrap`); years = union of date ranges (a "2019-2021" range ends Dec 2021); "Present" uses today (injectable for tests).
- `skills.py`: aliases with `!` (Go, R, C, Rust, Swift, Express) only count in the Skills section or list-like lines, to avoid prose false positives.
- Calibration: cosine ranges differ per model, so `cosine_to_unit` rescales (MiniLM 0.10–0.60). Set a priori, never fitted to the eval.
- Honest limits: eval data and labels are generated from my own templates (optimistic); skills-only is a strong baseline there; explain latency p95 (1.4 s) is dominated by on-the-fly embedding; no OCR; no refresh-token revocation.
