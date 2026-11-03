# AI Job & Resume Matcher

Explainable resume ↔ job matching: PDF parsing, pgvector semantic search, and a hybrid score that tells a recruiter *why* a candidate ranks where they do.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![Postgres](https://img.shields.io/badge/PostgreSQL-pgvector-336791?logo=postgresql&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=nextdotjs&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
[![CI](https://github.com/Alkarim786/ai-job-resume-matcher/actions/workflows/ci.yml/badge.svg)](https://github.com/Alkarim786/ai-job-resume-matcher/actions/workflows/ci.yml)
## Problem

Keyword filters miss good candidates ("built REST services" vs "API development") and black-box ML rankers can't justify a decision. This project combines embeddings (meaning) with a transparent skill/experience/title model, and returns the evidence: matched skills, missing must-haves, and the resume sentence that best supports each job requirement.

## Architecture

```mermaid
flowchart LR
  UI[Next.js dashboards] -->|REST + JWT| API[FastAPI]
  API --> PG[(PostgreSQL + pgvector)]
  API -->|enqueue parse job| RQ[(Redis)]
  RQ --> W[arq worker: parse PDF, extract skills, embed chunks]
  W --> PG
  API -->|1. HNSW ANN shortlist 2. exact hybrid rerank 3. explain| PG
```

**Data flow.** A candidate uploads a PDF → the API validates magic bytes and size, stores it under a random name, and enqueues `parse_resume` on Redis (HTTP 202). The worker extracts text (pypdf), splits sections, extracts skills against a 104-entry taxonomy with aliases, computes years of experience from date ranges (overlaps counted once), chunks the resume and embeds each chunk into `vector(384)`. Matching is two-stage: an HNSW cosine scan over chunk vectors shortlists candidates, then every shortlisted pair is scored exactly:

`score = 0.5·semantic + 0.3·skills + 0.1·experience + 0.1·title`

- **semantic**: max-sim (best resume chunk vs the job embedding), linearly calibrated from the model's cosine range to 0..1
- **skills**: weighted coverage, must-have = 2, nice-to-have = 1
- **experience**: `min(1, years / min_years)`
- **title**: similarity of the job title to the candidate's headline/past titles

## Tech stack

| Choice | Why |
|---|---|
| FastAPI + async SQLAlchemy 2 | I/O-bound API; typed schemas; OpenAPI for free |
| PostgreSQL + pgvector (HNSW) | vectors next to relational data, one transaction, no second datastore |
| Redis + arq | async parse/embed off the request path, retries, small footprint |
| sentence-transformers `all-MiniLM-L6-v2` | 384-d, CPU-friendly; `hash` fallback embedder for offline/tests |
| pypdf | pure-Python text extraction |
| argon2 + PyJWT | memory-hard hashing; short access / long refresh tokens, typed so one can't be used as the other |
| Next.js 14 (App Router, TS) | recruiter and candidate dashboards |
| Alembic | versioned schema incl. extension and HNSW indexes |

## Features

- Roles CANDIDATE / RECRUITER / ADMIN, JWT access + refresh, role- and ownership-checked endpoints
- Async PDF parsing with status polling; failures (corrupt, image-only PDFs) are recorded on the resume, not raised
- Editable parsed profile (skills, years, headline, searchable flag)
- Job recommendations for candidates; ranked candidates for recruiters (whole pool or applicants only)
- Explanations: skill match/miss and best supporting resume sentence per requirement
- Apply → shortlist/reject pipeline
- Blind review (`?blind=true`) hides names and ids
- Seed data: 20 jobs, 30 synthetic resumes rendered as real PDFs and parsed by the real pipeline
- Admin API: stats and user list (no UI)

## Roadmap (not built)

- OCR for scanned PDFs (currently rejected with a clear error)
- Learning-to-rank from recruiter feedback; fairness metrics beyond blind mode
- Email notifications; refresh-token revocation list
- Per-requirement (job chunk × resume chunk) max-sim instead of one job vector

## Key engineering decisions

- **Two-stage retrieval.** ANN shortlists (`ann_candidates`=200), exact scoring reranks. Trade-off: a candidate with strong skills but weak embedding similarity can miss the shortlist. The `searchable` filter is applied after the ANN step (HNSW post-filtering), so heavy filtering would need over-fetching or iterative scans.
- **Chunked max-sim.** A resume is many topics; one averaged vector blurs them. Max over chunks keeps the best-matching evidence.
- **Calibration is fixed a priori** per embedder (MiniLM 0.10–0.60, hash 0.00–0.45) and never tuned on the eval set.
- **Ambiguous skills** ("Go", "R", "C", "Swift") only match inside the Skills section or list lines; `C++`/`C#` don't trigger `C`.
- **Same code on SQLite and Postgres.** A `TypeDecorator` stores vectors as JSON on SQLite; the full API suite runs on both, so the pgvector path is tested for real.
- **Security.** Server never trusts client content-type or filename; 404 (not 403) on other recruiters' jobs; constant-time-ish login (dummy hash for unknown emails); admin can't be self-registered.
- **Idempotent worker.** Reprocessing replaces chunks; failures stored on the row.

## Quick start

```bash
docker compose up --build        # db, redis, api (migrates + seeds), worker, web
# web   http://localhost:3000     api docs http://localhost:8000/docs
```
Demo logins (password `password123`): `candidate1@example.com`, `recruiter1@example.com`, `admin@example.com`.
The first build downloads PyTorch (CPU) and bakes MiniLM into the image, so it is slow and large; set `EMBEDDER=hash` to skip model use at runtime.

### Local dev
```bash
docker compose up -d db redis
cd backend && python -m venv ../.venv && ../.venv/Scripts/pip install -r requirements-dev.txt -r requirements-ml.txt   # (bin/ on Linux/macOS)
cp ../.env.example .env && alembic upgrade head && python -m app.seed.seed
uvicorn app.main:app --reload            # and in another shell: arq app.worker.WorkerSettings
cd ../frontend && npm install && npm run dev
```
Tools installed for this build on Windows 11: Python 3.13 venv, Node 24, Docker Desktop.

## API reference (excerpt)

| Method & path | Role | Notes |
|---|---|---|
| `POST /auth/register`, `/auth/login`, `/auth/refresh`, `GET /auth/me` | any | |
| `POST /candidates/me/resume` | candidate | multipart `file` (PDF ≤ 5 MB) → `202` |
| `GET /candidates/me/resume` | candidate | `status`: PENDING/PROCESSING/DONE/FAILED |
| `GET/PUT /candidates/me/profile` | candidate | edit skills/years/headline/searchable |
| `GET /candidates/me/recommendations?limit=10` | candidate | ranked jobs + score breakdown |
| `POST /jobs`, `PUT /jobs/{id}`, `GET /jobs/mine` | recruiter | skills normalised via taxonomy |
| `GET /jobs/{id}/candidates?scope=all\|applicants&blind=false&limit=20` | owner | ranked candidates |
| `GET /jobs/{id}/candidates/{cid}/explain` | owner | skills + evidence sentences + weights |
| `POST /jobs/{id}/apply` | candidate | 409 if already applied |
| `PATCH /jobs/{id}/applications/{aid}` | owner | `{"status":"SHORTLISTED"}` |
| `GET /admin/stats`, `/admin/users` | admin | |

```bash
curl -s localhost:8000/jobs/1/candidates?limit=1 -H "Authorization: Bearer $TOKEN"
# [{"candidate_id":12,"name":"…","years_experience":6.0,
#   "score":{"total":0.81,"semantic":0.77,"skills":0.83,"experience":1.0,"title":0.62,"raw_cosine":0.41},
#   "skills":{"matched_must":["python","kafka"],"missing_must":["grpc"],…}}]
```

## Testing

```bash
cd backend && pytest -q                                   # SQLite, hash embedder
TEST_DATABASE_URL=postgresql+asyncpg://matcher:matcher@localhost:5432/matcher alembic upgrade head && \
TEST_DATABASE_URL=… pytest -q                             # same suite on Postgres + pgvector HNSW
TEST_EMBEDDER=minilm pytest -q                            # real model
cd frontend && npm test && npm run build
```
Ran locally: 51 backend tests on SQLite; the 16 API tests on Postgres+pgvector (Docker); 5 frontend tests; Next.js build. CI runs SQLite, Postgres, MiniLM, frontend and Docker-build jobs.

## Evaluation (measured on this PC)

Hardware: AMD Ryzen 5 7520U (4C/8T), 15.2 GB RAM, Windows 11, CPU only.
**Caveat:** data is synthetic. Resumes/jobs are generated from 8 role-family templates (≈1/6 of resumes are "keyword-stuffed" with another family's skills), rendered to real PDFs and parsed end to end. Relevance labels come from the generator (2 = same family, 1 = adjacent, 0 = unrelated), not humans, and the templates are written by me, so absolute numbers are optimistic. Compare the *variants*, not the absolute values. Reproduce: `python -m eval.run_eval --embedder minilm --resumes 30 --jobs 20 --seed 7` (raw JSON in `backend/eval/results/`).

**30 resumes × 20 jobs (seed 7), NDCG@10 / strict P@5 (same-family only):**

| Ranking | hash NDCG@10 | hash P@5 | MiniLM NDCG@10 | MiniLM P@5 |
|---|---|---|---|---|
| random | 0.340 | 0.17 | 0.340 | 0.17 |
| skills only | 0.851 | 0.65 | 0.851 | 0.65 |
| semantic only | 0.787 | 0.62 | 0.792 | 0.57 |
| **hybrid** | **0.874** | **0.71** | **0.897** | **0.69** |

**300 resumes × 40 jobs (seed 11):**

| Ranking | hash NDCG@10 | MiniLM NDCG@10 | MiniLM P@5 |
|---|---|---|---|
| skills only | 0.911 | 0.911 | 0.915 |
| semantic only | 0.930 | 0.921 | 0.910 |
| **hybrid** | **0.991** | **0.994** | **1.000** |

Note: with MiniLM, semantic-only is *not* better than the lexical hash baseline on this templated data; the gain comes from combining signals. Real resumes are far noisier.

**Parsing:** skill extraction precision 0.944, recall 1.000 (F1 0.971) on generated PDFs; years-of-experience MAE 0.1 yr.

**Latency (CPU):** PDF parse ≈ 24–33 ms/resume; MiniLM embedding ≈ 340–420 ms/resume; exact scoring of 300 resumes for one job ≈ 34 ms (in-memory).

**Live stack (Docker, client on the host, 50 requests, 30 seeded resumes):**

| Endpoint | p50 | p95 |
|---|---|---|
| `GET /health` | 3.8 ms | 4.4 ms |
| Ranked candidates, top 20, whole pool (HNSW shortlist + exact rerank) | 63 ms | 78 ms |
| Job recommendations, top 10 | 35 ms | 48 ms |
| Explain one candidate (embeds ~12 requirement + ~20 resume sentences with MiniLM on CPU) | 352 ms | 1430 ms |
| Upload → `DONE` through Redis/arq worker (10 runs) | 716 ms | 1154 ms |

`EXPLAIN` on the Postgres container confirms the cosine ordering uses `ix_resume_chunks_embedding_hnsw` (planner forced with `enable_seqscan=off`, since 30 resumes is too small for it to choose the index unprompted). With only 30 resumes these numbers say nothing about large-scale ANN behaviour.

## Project structure

```
backend/app/        config, models, security, parsing, skills(+taxonomy json), embeddings, scoring, matching, pipeline, queueing, worker, routers/
backend/app/seed/   synthetic resume/job generator (PDF via reportlab) + seed script
backend/alembic/    migration 0001 (pgvector extension, HNSW indexes)
backend/eval/       run_eval.py (ranking), bench_api.py (latency), results/
backend/tests/      unit + API tests (SQLite or Postgres)
frontend/           Next.js app (login, candidate, recruiter, job detail), vitest tests
docker-compose.yml  db, redis, api, worker, web
```

## License
MIT © Karim (Alkarim786)
