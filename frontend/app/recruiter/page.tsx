"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, json, type Job } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { useAuth } from "@/lib/useAuth";

const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export default function RecruiterDashboard() {
  const { user, logout } = useAuth("RECRUITER");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [form, setForm] = useState({ title: "", company: "", description: "", must: "", nice: "", min_years: "2" });
  const [error, setError] = useState("");
  const load = useCallback(async () => setJobs(await api<Job[]>("/jobs/mine")), []);
  useEffect(() => { if (user) load(); }, [user, load]);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setError("");
    try {
      await api("/jobs", json({ title: form.title, company: form.company, description: form.description, must_have: csv(form.must), nice_to_have: csv(form.nice), min_years: Number(form.min_years) }));
      setForm({ title: "", company: "", description: "", must: "", nice: "", min_years: "2" });
      await load();
    } catch (err: any) { setError(err.message); }
  }
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  if (!user) return <main><p className="muted">Loading…</p></main>;
  return (<>
    <Nav user={user} onLogout={logout} />
    <main>
      <h1>My jobs</h1>
      {jobs.map((j) => (
        <div className="card row" key={j.id}>
          <div><strong>{j.title}</strong> <span className="muted">· {j.company} · {j.min_years}+ yrs · must: {j.must_have.join(", ") || "—"}</span></div>
          <Link className="btn" href={`/recruiter/jobs/${j.id}`}>Ranked candidates</Link>
        </div>
      ))}
      {jobs.length === 0 && <p className="muted">No jobs yet — post one below.</p>}

      <h2>Post a job</h2>
      <form className="card" onSubmit={create}>
        <div className="grid2">
          <div><label htmlFor="t">Title</label><input id="t" required value={form.title} onChange={set("title")} /></div>
          <div><label htmlFor="c">Company</label><input id="c" value={form.company} onChange={set("company")} /></div>
        </div>
        <label htmlFor="d">Description (one requirement per sentence works best)</label>
        <textarea id="d" required minLength={20} rows={5} value={form.description} onChange={set("description")} />
        <div className="grid2">
          <div><label htmlFor="m">Must-have skills (comma separated)</label><input id="m" value={form.must} onChange={set("must")} placeholder="python, postgres, kafka" /></div>
          <div><label htmlFor="n">Nice-to-have skills</label><input id="n" value={form.nice} onChange={set("nice")} placeholder="docker, aws" /></div>
        </div>
        <label htmlFor="y">Minimum years</label><input id="y" type="number" min={0} step={0.5} value={form.min_years} onChange={set("min_years")} style={{ maxWidth: 120 }} />
        {error && <p className="error" role="alert">{error}</p>}
        <p><button>Post job</button></p>
      </form>
    </main>
  </>);
}
