"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, json, type Explain, type Job, type Ranked } from "@/lib/api";
import { Nav } from "@/components/Nav";
import { ScoreBreakdown, pct } from "@/components/ScoreBreakdown";
import { useAuth } from "@/lib/useAuth";

export default function JobCandidates() {
  const { id } = useParams<{ id: string }>();
  const { user, logout } = useAuth("RECRUITER");
  const [job, setJob] = useState<Job | null>(null);
  const [rows, setRows] = useState<Ranked[]>([]);
  const [scope, setScope] = useState<"all" | "applicants">("all");
  const [blind, setBlind] = useState(false);
  const [explain, setExplain] = useState<Explain | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setJob(await api<Job>(`/jobs/${id}`));
      setRows(await api<Ranked[]>(`/jobs/${id}/candidates?scope=${scope}&blind=${blind}&limit=25`));
    } catch (e: any) { setError(e.message); }
  }, [id, scope, blind]);
  useEffect(() => { if (user) load(); }, [user, load]);

  async function openExplain(cid: number | null) {
    if (cid == null) return;
    setExplain(await api<Explain>(`/jobs/${id}/candidates/${cid}/explain`));
  }
  async function setStatus(appId: number, status: string) {
    await api(`/jobs/${id}/applications/${appId}`, json({ status }, "PATCH"));
    await load();
  }

  if (!user) return <main><p className="muted">Loading…</p></main>;
  return (<>
    <Nav user={user} onLogout={logout} />
    <main>
      <p><Link href="/recruiter">← all jobs</Link></p>
      <h1>{job?.title ?? "Job"} <span className="muted">— ranked candidates</span></h1>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="card row">
        <span>
          <label style={{ display: "inline", marginRight: 8 }}>Pool</label>
          <select value={scope} onChange={(e) => setScope(e.target.value as any)} style={{ width: "auto" }}>
            <option value="all">All searchable candidates</option><option value="applicants">Applicants only</option>
          </select>
        </span>
        <label style={{ margin: 0 }}><input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} style={{ width: "auto" }} /> Blind review (hide names)</label>
      </div>

      {rows.map((c, i) => (
        <div className="card" key={`${i}-${c.candidate_id}`}>
          <div className="row">
            <div style={{ flex: 1, minWidth: 220 }}>
              <strong>#{i + 1} {c.name}</strong>
              <div className="muted">{c.headline || "—"} · {c.years_experience} yrs</div>
              {c.application_status && <div>Status: <strong>{c.application_status}</strong></div>}
              <p>
                <button className="ghost" disabled={blind} onClick={() => openExplain(c.candidate_id)}>Why this score?</button>{" "}
                {c.application_id && <>
                  <button onClick={() => setStatus(c.application_id!, "SHORTLISTED")}>Shortlist</button>{" "}
                  <button className="danger" onClick={() => setStatus(c.application_id!, "REJECTED")}>Reject</button>
                </>}
              </p>
            </div>
            <ScoreBreakdown score={c.score} skills={c.skills} />
          </div>
        </div>
      ))}
      {rows.length === 0 && !error && <p className="muted">No candidates to show.</p>}

      {explain && (
        <div className="card" role="dialog" aria-label="Score explanation">
          <div className="row"><h2 style={{ margin: 0 }}>{explain.candidate.name}: evidence</h2><button className="ghost" onClick={() => setExplain(null)}>Close</button></div>
          <p className="muted">Best resume sentence for each job requirement (semantic similarity shown).</p>
          {explain.evidence.map((e, i) => (
            <div key={i}><strong>{e.requirement}</strong><blockquote>{e.evidence} <em>({pct(e.similarity)})</em></blockquote></div>
          ))}
          {explain.candidate.skills.missing_must.length > 0 && <p className="error">Missing required skills: {explain.candidate.skills.missing_must.join(", ")}</p>}
        </div>
      )}
    </main>
  </>);
}
