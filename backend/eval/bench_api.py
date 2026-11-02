"""Latency of the live stack (run after `docker compose up`):  python -m eval.bench_api --base http://localhost:8000

Measures request latency for the matching endpoints and the end-to-end time for an upload to reach DONE through
the Redis/arq worker. Client and server share one machine and traffic crosses Docker Desktop's port forwarding.
"""

import argparse
import json
import statistics
import time

import httpx

from app.seed.generate import make_resume, render_pdf
import random


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def timed(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        r = fn()
        assert r.status_code == 200, r.text
        out.append((time.perf_counter() - t) * 1000)
    return {"n": n, "p50_ms": round(pct(out, 50), 1), "p95_ms": round(pct(out, 95), 1), "mean_ms": round(statistics.mean(out), 1)}


def login(c, email):
    r = c.post("/auth/login", json={"email": email, "password": "password123"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    with httpx.Client(base_url=a.base, timeout=60) as c:
        rec, cand = login(c, "recruiter1@example.com"), login(c, "candidate1@example.com")
        job_id = c.get("/jobs/mine", headers=rec).json()[0]["id"]
        results = {
            "health": timed(lambda: c.get("/health"), a.n),
            "ranked_candidates_top20_all_pool": timed(lambda: c.get(f"/jobs/{job_id}/candidates?limit=20", headers=rec), a.n),
            "job_recommendations_top10": timed(lambda: c.get("/candidates/me/recommendations?limit=10", headers=cand), a.n),
        }
        cid = c.get(f"/jobs/{job_id}/candidates?limit=1", headers=rec).json()[0]["candidate_id"]
        results["explain_one_candidate"] = timed(lambda: c.get(f"/jobs/{job_id}/candidates/{cid}/explain", headers=rec), a.n)

        pdf = render_pdf(make_resume(random.Random(99), "ml", 99))
        e2e = []
        for _ in range(10):
            t = time.perf_counter()
            r = c.post("/candidates/me/resume", headers=cand, files={"file": ("r.pdf", pdf, "application/pdf")})
            assert r.status_code == 202
            while c.get("/candidates/me/resume", headers=cand).json()["status"] != "DONE":
                time.sleep(0.05)
            e2e.append((time.perf_counter() - t) * 1000)
        results["upload_to_done_via_worker"] = {"n": 10, "p50_ms": round(pct(e2e, 50), 1), "p95_ms": round(pct(e2e, 95), 1), "mean_ms": round(statistics.mean(e2e), 1)}
    text = json.dumps(results, indent=2)
    print(text)
    if a.out:
        open(a.out, "w").write(text)
