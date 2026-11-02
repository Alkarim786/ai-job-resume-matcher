"use client";
import { useCallback, useEffect, useState } from "react";
import { api, json, type Profile, type Recommended, type Resume } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ScoreBreakdown } from "@/components/ScoreBreakdown";
import { useAuth } from "@/lib/useAuth";

export default function CandidateDashboard() {
  const { user, logout } = useAuth("CANDIDATE");
  const [resume, setResume] = useState<Resume | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [recs, setRecs] = useState<Recommended[]>([]);
  const [applied, setApplied] = useState<Set<number>>(new Set());
  const [skillsText, setSkillsText] = useState("");
  const [msg, setMsg] = useState("");

  const loadResume = useCallback(async () => {
    try { setResume(await api<Resume>("/candidates/me/resume")); } catch { setResume(null); }
  }, []);
  const loadRest = useCallback(async () => {
    const p = await api<Profile>("/candidates/me/profile");
    setProfile(p); setSkillsText(p.skills.join(", "));
    setRecs(await api<Recommended[]>("/candidates/me/recommendations?limit=10"));
    const apps = await api<{ job_id: number }[]>("/candidates/me/applications");
    setApplied(new Set(apps.map((a) => a.job_id)));
  }, []);

  useEffect(() => { if (user) loadResume(); }, [user, loadResume]);
  useEffect(() => {  // poll while the background worker parses the PDF
    if (!resume) return;
    if (resume.status === "PENDING" || resume.status === "PROCESSING") {
      const t = setTimeout(loadResume, 1500);
      return () => clearTimeout(t);
    }
    if (resume.status === "DONE") loadRest().catch((e) => setMsg(e.message));
  }, [resume, loadResume, loadRest]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setMsg("");
    const fd = new FormData(); fd.append("file", file);
    try { setResume(await api<Resume>("/candidates/me/resume", { method: "POST", body: fd })); }
    catch (err: any) { setMsg(err.message); }
  }
  async function saveProfile() {
    const skills = skillsText.split(",").map((s) => s.trim()).filter(Boolean);
    setProfile(await api<Profile>("/candidates/me/profile", json({ skills, years_experience: profile?.years_experience, headline: profile?.headline }, "PUT")));
    setRecs(await api<Recommended[]>("/candidates/me/recommendations?limit=10"));
    setMsg("Profile saved, matches refreshed.");
  }
  async function apply(jobId: number) {
    try { await api(`/jobs/${jobId}/apply`, { method: "POST" }); setApplied(new Set(applied).add(jobId)); }
    catch (err: any) { setMsg(err.message); }
  }

  if (!user) return <main><p className="muted">Loading…</p></main>;
  return (<>
    <Nav user={user} onLogout={logout} />
    <main>
      <h1>My resume</h1>
      <div className="card">
        <label htmlFor="pdf">Upload a PDF resume (max 5 MB)</label>
        <input id="pdf" type="file" accept="application/pdf" onChange={onUpload} />
        {resume && <p>
          {resume.filename}: <strong className={resume.status === "DONE" ? "ok" : resume.status === "FAILED" ? "error" : "muted"}>{resume.status}</strong>
          {resume.error && <span className="error"> — {resume.error}</span>}
        </p>}
        {msg && <p role="status">{msg}</p>}
      </div>

      {resume?.status === "DONE" && profile && (<>
        <h2>Parsed profile <span className="muted">(edit anything the parser got wrong)</span></h2>
        <div className="card">
          <div className="grid2">
            <div><label htmlFor="hl">Headline</label><input id="hl" value={profile.headline} onChange={(e) => setProfile({ ...profile, headline: e.target.value })} /></div>
            <div><label htmlFor="yrs">Years of experience</label><input id="yrs" type="number" min={0} step={0.5} value={profile.years_experience} onChange={(e) => setProfile({ ...profile, years_experience: Number(e.target.value) })} /></div>
          </div>
          <label htmlFor="sk">Skills (comma separated)</label>
          <textarea id="sk" rows={2} value={skillsText} onChange={(e) => setSkillsText(e.target.value)} />
          <p><button onClick={saveProfile}>Save &amp; re-match</button></p>
        </div>

        <h2>Recommended jobs</h2>
        {recs.length === 0 && <p className="muted">No open jobs yet.</p>}
        {recs.map((r) => (
          <div className="card" key={r.job.id}>
            <div className="row">
              <div style={{ flex: 1, minWidth: 240 }}>
                <strong>{r.job.title}</strong> <span className="muted">· {r.job.company} · {r.job.min_years}+ yrs</span>
                <p className="muted">{r.job.description.slice(0, 180)}…</p>
                <button disabled={applied.has(r.job.id)} onClick={() => apply(r.job.id)}>{applied.has(r.job.id) ? "Applied" : "Apply"}</button>
              </div>
              <ScoreBreakdown score={r.score} skills={r.skills} />
            </div>
          </div>
        ))}
      </>)}
    </main>
  </>);
}
