export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Role = "CANDIDATE" | "RECRUITER" | "ADMIN";
export interface Tokens { access_token: string; refresh_token: string }
export interface User { id: number; email: string; full_name: string; role: Role }
export interface Score { total: number; semantic: number; skills: number; experience: number; title: number; raw_cosine: number }
export interface SkillMatch { matched_must: string[]; missing_must: string[]; matched_nice: string[]; missing_nice: string[] }
export interface Job { id: number; title: string; company: string; description: string; must_have: string[]; nice_to_have: string[]; min_years: number }
export interface Recommended { job: Job; score: Score; skills: SkillMatch }
export interface Ranked {
  candidate_id: number | null; name: string; headline: string; years_experience: number;
  score: Score; skills: SkillMatch; application_status: string | null; application_id: number | null;
}
export interface Evidence { requirement: string; evidence: string; similarity: number }
export interface Explain { candidate: Ranked; evidence: Evidence[]; weights: Record<string, number> }
export interface Profile { headline: string; skills: string[]; years_experience: number; searchable: boolean }
export interface Resume { id: number; filename: string; status: "PENDING" | "PROCESSING" | "DONE" | "FAILED"; error: string | null; parsed: Record<string, any> }

const KEY = "matcher.tokens";

export function getTokens(): Tokens | null {
  try { return JSON.parse(localStorage.getItem(KEY) ?? "null"); } catch { return null; }
}
export function setTokens(t: Tokens | null) {
  try { t ? localStorage.setItem(KEY, JSON.stringify(t)) : localStorage.removeItem(KEY); } catch { /* storage unavailable */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function refresh(): Promise<boolean> {
  const t = getTokens();
  if (!t) return false;
  const r = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: t.refresh_token }),
  });
  if (!r.ok) { setTokens(null); return false; }
  setTokens(await r.json());
  return true;
}

/** Calls the API with the stored access token; on a 401 it refreshes once and retries. */
export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers);
  const t = getTokens();
  if (t) headers.set("Authorization", `Bearer ${t.access_token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const r = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (r.status === 401 && retry && t && (await refresh())) return api<T>(path, init, false);
  if (!r.ok) {
    let msg = r.statusText;
    try { const b = await r.json(); msg = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch { /* not json */ }
    throw new ApiError(r.status, msg);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const json = (body: unknown, method = "POST"): RequestInit => ({ method, body: JSON.stringify(body) });
