import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ScoreBreakdown, pct } from "@/components/ScoreBreakdown";
import { ApiError, api, getTokens, setTokens } from "@/lib/api";

afterEach(cleanup);

describe("ScoreBreakdown", () => {
  const score = { total: 0.734, semantic: 0.8, skills: 0.5, experience: 1, title: 0.4, raw_cosine: 0.4 };
  const skills = { matched_must: ["python"], missing_must: ["kafka"], matched_nice: ["docker"], missing_nice: [] };

  it("shows the total and every weighted component", () => {
    render(<ScoreBreakdown score={score} skills={skills} />);
    expect(screen.getByLabelText("match score").textContent).toBe("73%");
    for (const label of ["Semantic", "Skills", "Experience", "Title"]) expect(screen.getByText(new RegExp(label))).toBeTruthy();
  });

  it("flags missing must-have skills distinctly", () => {
    render(<ScoreBreakdown score={score} skills={skills} />);
    expect(screen.getByText(/kafka \(required\)/)).toBeTruthy();
    expect(screen.getByText(/✓ python/)).toBeTruthy();
  });

  it("formats percentages", () => { expect(pct(0.005)).toBe("1%"); expect(pct(1)).toBe("100%"); });
});

describe("api client", () => {
  const store: Record<string, string> = {};
  beforeEach(() => {
    for (const k of Object.keys(store)) delete store[k];
    vi.stubGlobal("localStorage", { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => (store[k] = v), removeItem: (k: string) => delete store[k] });
  });

  it("refreshes the access token once on 401 and retries", async () => {
    setTokens({ access_token: "old", refresh_token: "r1" });
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: any) => {
      calls.push(`${url} ${new Headers(init?.headers).get("Authorization") ?? ""}`);
      if (url.endsWith("/auth/refresh")) return new Response(JSON.stringify({ access_token: "new", refresh_token: "r2" }), { status: 200 });
      if (new Headers(init.headers).get("Authorization") === "Bearer old") return new Response("{}", { status: 401 });
      return new Response(JSON.stringify({ ok: 1 }), { status: 200 });
    }));
    expect(await api<{ ok: number }>("/auth/me")).toEqual({ ok: 1 });
    expect(getTokens()?.access_token).toBe("new");
    expect(calls).toHaveLength(3);
  });

  it("surfaces the API error detail and clears tokens when refresh fails", async () => {
    setTokens({ access_token: "old", refresh_token: "bad" });
    vi.stubGlobal("fetch", vi.fn(async (url: string) =>
      url.endsWith("/auth/refresh") ? new Response("{}", { status: 401 }) : new Response(JSON.stringify({ detail: "invalid or expired token" }), { status: 401 })));
    await expect(api("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(getTokens()).toBeNull();
  });
});
