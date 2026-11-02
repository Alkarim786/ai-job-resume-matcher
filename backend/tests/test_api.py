import sqlalchemy as sa

from app.config import get_settings
from app.models import Resume, ResumeChunk
from tests.conftest import job_payload, register, resume_pdf, upload


# ----------------------------------------------------------------------------- auth
async def test_register_login_refresh_me(client):
    r = await client.post("/auth/register", json={"email": "A@x.com", "password": "password123", "full_name": "A", "role": "CANDIDATE"})
    assert r.status_code == 201
    login = await client.post("/auth/login", json={"email": "a@x.com", "password": "password123"})  # email is case-insensitive
    assert login.status_code == 200
    tokens = login.json()
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.json()["email"] == "a@x.com" and me.json()["role"] == "CANDIDATE"
    new = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert new.status_code == 200 and new.json()["access_token"]


async def test_auth_failures(client):
    body = {"email": "a@x.com", "password": "password123", "full_name": "A", "role": "CANDIDATE"}
    await client.post("/auth/register", json=body)
    assert (await client.post("/auth/register", json=body)).status_code == 409
    assert (await client.post("/auth/login", json={"email": "a@x.com", "password": "wrong-password"})).status_code == 401
    assert (await client.post("/auth/login", json={"email": "nobody@x.com", "password": "password123"})).status_code == 401
    assert (await client.post("/auth/register", json={**body, "email": "b@x.com", "role": "ADMIN"})).status_code == 422
    assert (await client.post("/auth/register", json={**body, "email": "c@x.com", "password": "short"})).status_code == 422
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})).status_code == 401


async def test_token_types_are_not_interchangeable(client):
    tokens = (await client.post("/auth/register", json={"email": "a@x.com", "password": "password123", "full_name": "A", "role": "CANDIDATE"})).json()
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})).status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]})).status_code == 401


# ----------------------------------------------------------------------------- RBAC
async def test_role_based_access(client, admin_headers):
    cand = await register(client, "c@x.com", "CANDIDATE")
    rec = await register(client, "r@x.com", "RECRUITER")
    _, payload = job_payload("backend")
    assert (await client.post("/jobs", json=payload)).status_code == 401
    assert (await client.post("/jobs", json=payload, headers=cand)).status_code == 403
    job = (await client.post("/jobs", json=payload, headers=rec)).json()
    _, pdf = resume_pdf("backend")
    assert (await upload(client, rec, pdf)).status_code == 403
    assert (await client.get(f"/jobs/{job['id']}/candidates", headers=cand)).status_code == 403
    assert (await client.get("/admin/stats", headers=cand)).status_code == 403
    assert (await client.get("/admin/stats", headers=rec)).status_code == 403
    stats = await client.get("/admin/stats", headers=admin_headers)
    assert stats.status_code == 200 and stats.json()["jobs"] == 1 and stats.json()["users"]["CANDIDATE"] == 1


# ----------------------------------------------------------------------------- upload + async parse
async def test_upload_validation(client, monkeypatch):
    cand = await register(client, "c@x.com", "CANDIDATE")
    assert (await upload(client, cand, b"hello, not a pdf", "evil.pdf")).status_code == 415
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1000)
    _, pdf = resume_pdf("backend")
    assert (await upload(client, cand, pdf)).status_code == 413


async def test_corrupt_pdf_marks_resume_failed(client):
    cand = await register(client, "c@x.com", "CANDIDATE")
    r = await upload(client, cand, b"%PDF-1.4 truncated garbage")
    assert r.status_code == 202
    got = (await client.get("/candidates/me/resume", headers=cand)).json()
    assert got["status"] == "FAILED" and "cannot read PDF" in got["error"]
    assert (await client.get("/candidates/me/recommendations", headers=cand)).status_code == 409


async def test_upload_parses_resume_and_fills_profile(client):
    cand = await register(client, "c@x.com", "CANDIDATE")
    spec, pdf = resume_pdf("backend", seed=2)
    assert (await upload(client, cand, pdf)).status_code == 202
    resume = (await client.get("/candidates/me/resume", headers=cand)).json()
    assert resume["status"] == "DONE" and resume["parsed"]["chunk_count"] > 0
    profile = (await client.get("/candidates/me/profile", headers=cand)).json()
    assert set(profile["skills"]) >= set(spec.skills) - {"c", "r"} and profile["years_experience"] > 0


async def test_reupload_replaces_chunks(client, sm):
    cand = await register(client, "c@x.com", "CANDIDATE")
    await upload(client, cand, resume_pdf("backend", 1)[1])
    await upload(client, cand, resume_pdf("frontend", 2)[1])
    async with sm() as s:
        assert (await s.execute(sa.select(sa.func.count()).select_from(Resume))).scalar_one() == 1
        n_chunks = (await s.execute(sa.select(sa.func.count()).select_from(ResumeChunk))).scalar_one()
    parsed = (await client.get("/candidates/me/resume", headers=cand)).json()["parsed"]
    assert n_chunks == parsed["chunk_count"]


# ----------------------------------------------------------------------------- matching
async def _world(client):
    rec = await register(client, "rec@x.com", "RECRUITER")
    be_spec, be_job = job_payload("backend", 1)
    fe_spec, fe_job = job_payload("frontend", 1)
    be_id = (await client.post("/jobs", json=be_job, headers=rec)).json()["id"]
    fe_id = (await client.post("/jobs", json=fe_job, headers=rec)).json()["id"]
    be_c = await register(client, "be@x.com", "CANDIDATE", "Backend Person")
    fe_c = await register(client, "fe@x.com", "CANDIDATE", "Frontend Person")
    await upload(client, be_c, resume_pdf("backend", 5)[1])
    await upload(client, fe_c, resume_pdf("frontend", 6)[1])
    return rec, be_id, fe_id, be_c, fe_c


async def test_recommendations_rank_matching_family_first(client):
    _, be_id, fe_id, be_c, fe_c = await _world(client)
    rec_be = (await client.get("/candidates/me/recommendations", headers=be_c)).json()
    rec_fe = (await client.get("/candidates/me/recommendations", headers=fe_c)).json()
    assert [r["job"]["id"] for r in rec_be][0] == be_id
    assert [r["job"]["id"] for r in rec_fe][0] == fe_id
    top = rec_be[0]
    assert 0 <= top["score"]["total"] <= 1 and set(top["score"]) >= {"semantic", "skills", "experience", "title"}


async def test_recruiter_sees_ranked_candidates_with_explanations(client):
    rec, be_id, _, be_c, fe_c = await _world(client)
    ranked = (await client.get(f"/jobs/{be_id}/candidates", headers=rec)).json()
    assert [c["name"] for c in ranked][0] == "Backend Person"
    assert ranked[0]["score"]["total"] > ranked[-1]["score"]["total"]
    cid = ranked[0]["candidate_id"]
    ex = (await client.get(f"/jobs/{be_id}/candidates/{cid}/explain", headers=rec)).json()
    assert ex["evidence"] and all({"requirement", "evidence", "similarity"} <= set(e) for e in ex["evidence"])
    assert ex["weights"] == {"semantic": 0.5, "skills": 0.3, "experience": 0.1, "title": 0.1}
    sk = ex["candidate"]["skills"]
    assert set(sk) == {"matched_must", "missing_must", "matched_nice", "missing_nice"}


async def test_profile_edit_changes_skill_score(client):
    rec, be_id, _, be_c, _ = await _world(client)
    before = (await client.get(f"/jobs/{be_id}/candidates", headers=rec)).json()[0]
    await client.put("/candidates/me/profile", json={"skills": []}, headers=be_c)
    after = (await client.get(f"/jobs/{be_id}/candidates", headers=rec)).json()
    mine = next(c for c in after if c["name"] == "Backend Person")
    assert mine["score"]["skills"] < before["score"]["skills"]
    assert mine["skills"]["matched_must"] == []


async def test_recruiters_cannot_see_each_others_jobs(client):
    rec, be_id, *_ = await _world(client)
    other = await register(client, "other@x.com", "RECRUITER")
    assert (await client.get(f"/jobs/{be_id}/candidates", headers=other)).status_code == 404
    assert (await client.get(f"/jobs/{be_id}/applications", headers=other)).status_code == 404
    assert (await client.get(f"/jobs/{be_id}/candidates/1/explain", headers=other)).status_code == 404
    _, payload = job_payload("backend", 3)
    assert (await client.put(f"/jobs/{be_id}", json=payload, headers=other)).status_code == 404
    assert [j["id"] for j in (await client.get("/jobs/mine", headers=other)).json()] == []


async def test_searchable_flag_and_applicant_scope(client):
    rec, be_id, _, be_c, fe_c = await _world(client)
    await client.put("/candidates/me/profile", json={"searchable": False}, headers=fe_c)
    names = [c["name"] for c in (await client.get(f"/jobs/{be_id}/candidates", headers=rec)).json()]
    assert "Frontend Person" not in names
    # applying is an explicit share: hidden candidates still appear in the applicants view
    assert (await client.post(f"/jobs/{be_id}/apply", headers=fe_c)).status_code == 201
    applicants = (await client.get(f"/jobs/{be_id}/candidates?scope=applicants", headers=rec)).json()
    assert [c["name"] for c in applicants] == ["Frontend Person"]
    assert applicants[0]["application_status"] == "APPLIED"


async def test_apply_and_shortlist_pipeline(client):
    rec, be_id, _, be_c, _ = await _world(client)
    assert (await client.post(f"/jobs/{be_id}/apply", headers=be_c)).status_code == 201
    assert (await client.post(f"/jobs/{be_id}/apply", headers=be_c)).status_code == 409
    app_id = (await client.get(f"/jobs/{be_id}/applications", headers=rec)).json()[0]["id"]
    r = await client.patch(f"/jobs/{be_id}/applications/{app_id}", json={"status": "SHORTLISTED"}, headers=rec)
    assert r.json()["status"] == "SHORTLISTED"
    mine = (await client.get("/candidates/me/applications", headers=be_c)).json()
    assert mine[0]["status"] == "SHORTLISTED"
    other = await register(client, "o@x.com", "RECRUITER")
    assert (await client.patch(f"/jobs/{be_id}/applications/{app_id}", json={"status": "REJECTED"}, headers=other)).status_code == 404
    assert (await client.patch(f"/jobs/{be_id}/applications/{app_id}", json={"status": "HIRED"}, headers=rec)).status_code == 422


async def test_blind_mode_hides_identity(client):
    rec, be_id, *_ = await _world(client)
    ranked = (await client.get(f"/jobs/{be_id}/candidates?blind=true", headers=rec)).json()
    assert ranked and all(c["name"] == "Candidate" and c["candidate_id"] is None for c in ranked)


async def test_job_validation(client):
    rec = await register(client, "rec@x.com", "RECRUITER")
    _, payload = job_payload("backend")
    assert (await client.post("/jobs", json={**payload, "description": "short"}, headers=rec)).status_code == 422
    assert (await client.post("/jobs", json={**payload, "min_years": -1}, headers=rec)).status_code == 422
    created = (await client.post("/jobs", json={**payload, "must_have": ["Postgres", "K8s"]}, headers=rec)).json()
    assert created["must_have"] == ["postgresql", "kubernetes"]
